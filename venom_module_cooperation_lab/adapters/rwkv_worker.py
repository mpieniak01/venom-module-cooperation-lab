"""Worker-only Torch/RWKV imports; fixed local artefacts, bounded JSON IPC."""

from __future__ import annotations

import contextlib
import ctypes
import hashlib
import json
import os
import resource
import signal
import sys
import time
from pathlib import Path
from typing import Any

from .component import activate_overlay
from .rwkv_tokenizer import SafeRwkvTokenizer

MAX_WIRE_BYTES = 65536


def worker_main(
    connection: Any, cancel: Any, config: dict[str, Any], parent_pid: int
) -> None:
    """Linux parent-death SIGKILL prevents an orphan keeping model resources."""
    if sys.platform != "linux" or ctypes.CDLL(None).prctl(1, signal.SIGKILL) != 0:
        connection.send_bytes(b'{"error":"unsupported_parent_lifecycle"}')
        return
    if os.getppid() != parent_pid:
        return
    try:
        with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink):
            _run_worker(connection, cancel, config)
    except BaseException as exc:
        code = (
            "out_of_memory"
            if "OutOfMemory" in type(exc).__name__
            else "worker_initialization_failed"
        )
        try:
            connection.send_bytes(json.dumps({"error": code}).encode())
        except (EOFError, OSError):
            pass
    finally:
        connection.close()


def _run_worker(connection: Any, cancel: Any, config: dict[str, Any]) -> None:
    # Only the isolated child modifies these third-party runtime globals.
    os.environ.update(
        RWKV_V7_ON="1",
        RWKV_CUDA_ON="0",
        RWKV_JIT_ON="1",
        TORCH_FORCE_WEIGHTS_ONLY_LOAD="1",
        PYTHONDONTWRITEBYTECODE="1",
    )
    os.environ.pop("RWKV_DE_VERSION", None)
    os.environ.pop("RWKV_DML_ON", None)
    overlay_versions = activate_overlay(Path(config["runtime_root"]))
    import torch
    from rwkv.model import RWKV

    use_cuda = config["strategy"].startswith("cuda")
    if use_cuda and not torch.cuda.is_available():
        connection.send_bytes(b'{"error":"cuda_unavailable"}')
        return
    torch.set_num_threads(2)
    started = time.monotonic()
    model_path = str(config["model_path"])
    model = RWKV(model=model_path.removesuffix(".pth"), strategy=config["strategy"])
    tokenizer = SafeRwkvTokenizer(
        Path(config["runtime_root"]) / "rwkv" / "rwkv_vocab_v20230424.txt"
    )
    if use_cuda:
        torch.cuda.synchronize()
        torch.cuda.reset_peak_memory_stats()
    states: dict[str, dict[str, Any]] = {
        name: {"tensors": None, "tokens": 0} for name in ("A", "B")
    }
    receipt = {
        "state": "ready",
        "load_s": time.monotonic() - started,
        "runtime": "rwkv",
        "runtime_version": "0.8.32",
        **overlay_versions,
        "torch_version": torch.__version__,
        "strategy": config["strategy"],
        "custom_cuda_kernel": False,
        "peak_ram_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
        "model_parameters": sum(t.numel() for t in model.z.values()),
        "precision": str(model.z["head.weight"].dtype),
        "device": str(model.z["head.weight"].device),
    }
    connection.send_bytes(json.dumps(receipt).encode())
    while True:
        try:
            command = json.loads(connection.recv_bytes(MAX_WIRE_BYTES))
        except (EOFError, OSError):
            return
        name = command.get("command")
        if name == "close":
            if use_cuda:
                torch.cuda.synchronize()
            return
        try:
            if name == "generate":
                result = _generate(
                    model, tokenizer, states, cancel, command, torch, use_cuda
                )
            elif name == "reset":
                selected = (
                    (command["participant"],)
                    if command.get("participant")
                    else ("A", "B")
                )
                for participant in selected:
                    states[participant] = {"tensors": None, "tokens": 0}
                result = {"state": "reset"}
            elif name == "state":
                result = _state_snapshot(states)
            else:
                result = {"error": "unsupported_command"}
        except Exception as exc:
            code = (
                "out_of_memory"
                if "OutOfMemory" in type(exc).__name__
                else "generation_failed"
            )
            states = {
                participant: {"tensors": None, "tokens": 0}
                for participant in ("A", "B")
            }
            result = {"error": code}
        if use_cuda:
            torch.cuda.synchronize()
        result["request_id"] = command.get("request_id")
        connection.send_bytes(json.dumps(result, allow_nan=False).encode())


def _state_snapshot(states: dict[str, dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {"participants": {}}
    all_pointers: list[set[int]] = []
    for name, value in states.items():
        tensors = value["tensors"] or []
        digest = hashlib.sha256()
        for tensor in tensors:
            digest.update(tensor.detach().float().cpu().numpy().tobytes())
        pointers = {tensor.data_ptr() for tensor in tensors}
        all_pointers.append(pointers)
        result["participants"][name] = {
            "tokens": value["tokens"],
            "tensor_count": len(tensors),
            "state_bytes": sum(t.numel() * t.element_size() for t in tensors),
            "fingerprint": digest.hexdigest() if tensors else None,
        }
    result["shared_state_storage"] = bool(all_pointers[0] & all_pointers[1])
    return result


def _generate(
    model: Any,
    tokenizer: SafeRwkvTokenizer,
    states: dict[str, dict[str, Any]],
    cancel: Any,
    command: dict[str, Any],
    torch: Any,
    use_cuda: bool,
) -> dict[str, Any]:
    participant = command["participant"]
    previous = states[participant]
    params = command["parameters"]
    prompt_tokens = tokenizer.encode(command["prompt"])
    if (
        previous["tokens"] + len(prompt_tokens) + params["max_new_tokens"]
        > params["max_context_tokens"]
    ):
        return {"error": "context_budget_exceeded"}
    if cancel.is_set():
        return {
            "text": "",
            "stop_reason": "cancelled",
            "input_tokens": 0,
            "output_tokens": 0,
            "quiescent": True,
        }
    torch.manual_seed(params["seed"])
    working = (
        None
        if previous["tensors"] is None
        else [tensor.clone() for tensor in previous["tensors"]]
    )
    started = time.monotonic()
    deadline = started + command["timeout_s"]
    consumed, output = 0, []
    occurrence: dict[int, float] = {}
    ttft = None
    reason = "length"
    logits = None
    while consumed < len(prompt_tokens):
        if cancel.is_set() or time.monotonic() >= deadline:
            reason = "cancelled" if cancel.is_set() else "deadline"
            break
        chunk = prompt_tokens[consumed : consumed + 16]
        logits, working = model.forward(chunk, working)
        consumed += len(chunk)
    if consumed == len(prompt_tokens):
        for _ in range(params["max_new_tokens"]):
            if cancel.is_set() or time.monotonic() >= deadline:
                reason = "cancelled" if cancel.is_set() else "deadline"
                break
            assert logits is not None
            logits = logits.float()
            if not bool(torch.isfinite(logits).all()):
                return {"error": "nonfinite_logits"}
            for token, frequency in occurrence.items():
                logits[token] -= 2.0 + frequency * 0.1
            if params["temperature"] == 0 or params["top_p"] == 0:
                token = int(torch.argmax(logits).item())
            else:
                probabilities = torch.softmax(logits, dim=-1)
                sorted_probabilities, indices = torch.sort(
                    probabilities, descending=True
                )
                cumulative = torch.cumsum(sorted_probabilities, dim=-1)
                keep = cumulative - sorted_probabilities < params["top_p"]
                selected = torch.where(keep, sorted_probabilities, 0.0)
                selected = selected ** (1.0 / params["temperature"])
                token = int(indices[torch.multinomial(selected, 1)].item())
            if token == 0:
                reason = "eos"
                break
            output.append(token)
            logits, working = model.forward([token], working)
            for item in occurrence:
                occurrence[item] *= 0.99
            occurrence[token] = occurrence.get(token, 0.0) + 1
            if use_cuda:
                torch.cuda.synchronize()
            if ttft is None:
                ttft = time.monotonic() - started
            if "\n\n" in tokenizer.decode(output):
                reason = "stop_sequence"
                break
    if use_cuda:
        torch.cuda.synchronize()
    if reason not in {"cancelled", "deadline"}:
        states[participant] = {
            "tensors": working,
            "tokens": previous["tokens"] + consumed + len(output),
        }
    return {
        "text": tokenizer.decode(output).split("\n\n", 1)[0].strip(),
        "stop_reason": reason,
        "input_tokens": consumed,
        "output_tokens": len(output),
        "ttft_s": ttft,
        "generation_s": time.monotonic() - started,
        "quiescent": True,
        "effective_parameters": {
            **params,
            "alpha_presence": 2.0,
            "alpha_frequency": 0.1,
            "alpha_decay": 0.99,
            "prefill_chunk_tokens": 16,
        },
        "peak_vram_bytes": torch.cuda.max_memory_allocated() if use_cuda else 0,
        "peak_ram_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
    }
