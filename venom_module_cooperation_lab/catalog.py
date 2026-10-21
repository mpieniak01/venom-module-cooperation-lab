"""Read-only bridge to the host catalog and pinned local Ollama identities."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
import urllib.request
from collections.abc import Awaitable, Callable
from typing import Any

from .adapters.base import Lease, ModelAdapter, ModelSpec
from .adapters.ollama import NoRedirect, OllamaAdapter
from .adapters.registry import OLLAMA_SPEC, RWKV_SPEC, create_adapter
from .errors import LabError


async def host_local_catalog() -> list[dict[str, Any]]:
    # Reuse Chat's existing local classification, without the full options
    # endpoint's auto-heal, cloud discovery or global runtime mutations.
    from venom_core.api.routes import system_llm as host

    manager = host.system_deps.get_model_manager()
    if manager is None:
        raise LabError("catalog_unavailable", 503)
    local = await manager.list_local_models()
    grouped, _audit = await host._local_models_by_runtime(manager, local_models=local)
    status = await host._runtime_server_status_snapshot()
    return host._local_runtime_targets(
        local_models=grouped,
        server_status=status,
        active_runtime=host.get_active_llm_runtime(),
    )


def ollama_metadata() -> dict[str, Any]:
    deadline = time.monotonic() + 8
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def read(path: str, body: dict[str, Any] | None = None) -> Any:
        request = urllib.request.Request(
            "http://127.0.0.1:11434" + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json"},
        )
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise LabError("catalog_unavailable")
        with opener.open(request, timeout=min(2, remaining)) as response:
            raw = response.read(262145)
        if len(raw) > 262144:
            raise LabError("runtime_response_too_large")
        return json.loads(raw)

    version = read("/api/version")["version"]
    models = []
    for entry in read("/api/tags")["models"][:100]:
        name = entry.get("name")
        if not isinstance(name, str) or len(name) > 256:
            continue
        show = read("/api/show", {"model": name})
        models.append({**entry, "show": show})
    return {"version": version, "models": models}


class ModelCatalog:
    def __init__(
        self,
        loader: Callable[[], Awaitable[list[dict[str, Any]]]] = host_local_catalog,
        metadata: Callable[[], dict[str, Any]] = ollama_metadata,
    ) -> None:
        self.loader, self.metadata = loader, metadata
        self._specs = {s.model_id: s for s in (RWKV_SPEC, OLLAMA_SPEC)}
        self._available = {RWKV_SPEC.model_id}
        self._details: dict[str, dict[str, Any]] = {}
        self.engines: list[dict[str, Any]] = []
        self.unsupported: list[dict[str, Any]] = []
        self.error: str | None = None
        self._updated = 0.0
        self._lock = asyncio.Lock()

    def specs(self) -> list[ModelSpec]:
        return list(self._specs.values())

    def available(self, model_id: str) -> bool:
        return model_id in self._available

    def candidate(self, model_id: str) -> ModelSpec:
        spec = self._specs.get(model_id)
        if spec is None or spec.provider != "ollama" or not self.available(model_id):
            raise LabError("model_unavailable", 409)
        return spec

    def adapter(self, model_id: str, lease: Lease) -> ModelAdapter:
        if lease is None or not callable(getattr(lease, "operation", None)):
            raise LabError("runtime_lease_required")
        if model_id == RWKV_SPEC.model_id:
            return create_adapter(model_id, lease)
        return OllamaAdapter(self.candidate(model_id), lease)

    async def refresh(self, *, force: bool = False) -> None:
        async with self._lock:
            if not force and self._updated and time.monotonic() - self._updated < 30:
                return
            try:
                runtimes = await asyncio.wait_for(self.loader(), timeout=8)
                has_ollama = any(
                    r.get("runtime_id") == "ollama" and r.get("status") == "online"
                    for r in runtimes
                )
                metadata = (
                    await asyncio.wait_for(asyncio.to_thread(self.metadata), timeout=12)
                    if has_ollama
                    else {"models": [], "version": ""}
                )
                self._apply(runtimes, metadata)
                self.error = None
            except Exception:
                self._available = {RWKV_SPEC.model_id}
                self.error = "catalog_unavailable"
            self._updated = time.monotonic()

    def _apply(self, runtimes: list[dict[str, Any]], metadata: dict[str, Any]) -> None:
        self.engines = [
            {
                "engine_id": "local_component",
                "name": "RWKV",
                "status": "available",
                "supported": True,
            }
        ]
        self.unsupported = []
        self._available = {RWKV_SPEC.model_id}
        self._details = {}
        # Historical identities remain visible, even if the live catalog changed.
        self._specs = {s.model_id: s for s in (RWKV_SPEC, OLLAMA_SPEC)}
        for runtime in runtimes:
            engine = runtime.get("runtime_id")
            if engine not in {"ollama", "vllm", "multi_runtime", "onnx"}:
                continue
            status = str(runtime.get("status", "unknown"))
            self.engines.append(
                {
                    "engine_id": engine,
                    "name": engine,
                    "status": status,
                    "supported": engine == "ollama",
                }
            )
            rows = runtime.get("models", [])
            if engine == "ollama":
                if status == "online":
                    self._ollama(rows, metadata, True)
            else:
                for model in rows[:100]:
                    name = model.get("name")
                    if not isinstance(name, str) or not name or len(name) > 256:
                        continue
                    identifier = hashlib.sha256(
                        (engine + ":" + name).encode()
                    ).hexdigest()
                    self.unsupported.append(
                        {
                            "model_id": "unsupported-" + identifier,
                            "display_name": name,
                            "engine_id": engine,
                            "qualified": False,
                            "can_qualify": False,
                            "availability_reason": "adapter_not_supported",
                        }
                    )

    def _ollama(
        self, rows: list[dict[str, Any]], metadata: dict[str, Any], online: bool
    ) -> None:
        allowed = {
            m.get("name")
            for m in rows
            if isinstance(m, dict) and m.get("chat_compatible") is not False
        }
        version = metadata.get("version", "")
        if not isinstance(version, str) or not re.fullmatch(
            r"[0-9]+\.[0-9]+\.[0-9]+", version
        ):
            raise LabError("catalog_unavailable")
        seen = set()
        for entry in sorted(
            metadata.get("models", []), key=lambda row: str(row.get("name", ""))
        ):
            name, digest = entry.get("name"), entry.get("digest")
            if (
                name not in allowed
                or not isinstance(digest, str)
                or not re.fullmatch(r"[a-f0-9]{64}", digest)
                or digest in seen
            ):
                continue
            show = entry.get("show", {})
            template = show.get("template")
            if (
                "completion" not in show.get("capabilities", [])
                or not isinstance(template, str)
                or not template
            ):
                continue
            seen.add(digest)
            template_hash = hashlib.sha256(template.encode()).hexdigest()
            identity = hashlib.sha256(
                (digest + template_hash + version).encode()
            ).hexdigest()
            details = show.get("details", {})
            spec = ModelSpec(
                model_id="ollama-" + identity,
                architecture=str(details.get("family", "unknown")),
                provider="ollama",
                artifact=name,
                revision=digest,
                digest=digest,
                tokenizer_hash="bundled-in-gguf-covered-by-model-digest",
                template_hash=template_hash,
                runtime="ollama==" + version,
                quantization=str(details.get("quantization_level", "unknown")),
            )
            if (
                name == OLLAMA_SPEC.artifact
                and digest == OLLAMA_SPEC.digest
                and template_hash == OLLAMA_SPEC.template_hash
                and spec.runtime == OLLAMA_SPEC.runtime
            ):
                spec = OLLAMA_SPEC
            self._specs[spec.model_id] = spec
            self._details[spec.model_id] = {
                "display_name": name,
                "engine_id": "ollama",
                "size_bytes": entry.get("size"),
            }
            if online:
                self._available.add(spec.model_id)

    def public_models(self, models: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result = []
        for model in models:
            identifier = model["model_id"]
            available = self.available(identifier)
            result.append(
                {
                    **model,
                    "display_name": model["artifact"],
                    "engine_id": model["provider"],
                    **self._details.get(identifier, {}),
                    "qualified": model["qualified"] and available,
                    "can_run": available
                    and (model["provider"] == "ollama" or model["qualified"]),
                    "can_qualify": available
                    and model["provider"] == "ollama"
                    and not model["qualified"],
                    "availability_reason": (
                        "available_unchecked"
                        if model["provider"] == "ollama" and not model["qualified"]
                        else model["availability_reason"]
                    )
                    if available
                    else "model_unavailable",
                }
            )
        return result + self.unsupported
