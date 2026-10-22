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
from dataclasses import dataclass, field
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
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception as exc:
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


def _load_worker(
    connection: Any, config: dict[str, Any]
) -> tuple[Any, SafeRwkvTokenizer, Any, bool] | None:
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
        return None
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
    return model, tokenizer, torch, use_cuda


def _empty_states() -> dict[str, dict[str, Any]]:
    return {name: {"tensors": None, "tokens": 0} for name in ("A", "B")}


def _command_result(
    model: Any,
    tokenizer: SafeRwkvTokenizer,
    states: dict[str, dict[str, Any]],
    cancel: Any,
    command: dict[str, Any],
    torch: Any,
    use_cuda: bool,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    try:
        name = command.get("command")
        if name == "generate":
            return _generate(
                model, tokenizer, states, cancel, command, torch, use_cuda
            ), states
        if name == "reset":
            selected = (
                (command["participant"],) if command.get("participant") else ("A", "B")
            )
            for participant in selected:
                states[participant] = {"tensors": None, "tokens": 0}
            return {"state": "reset"}, states
        if name == "state":
            return _state_snapshot(states), states
        return {"error": "unsupported_command"}, states
    except Exception as exc:
        code = (
            "out_of_memory"
            if "OutOfMemory" in type(exc).__name__
            else "generation_failed"
        )
        return {"error": code}, _empty_states()


def _run_worker(connection: Any, cancel: Any, config: dict[str, Any]) -> None:
    loaded = _load_worker(connection, config)
    if loaded is None:
        return
    model, tokenizer, torch, use_cuda = loaded
    states = _empty_states()
    while True:
        try:
            command = json.loads(connection.recv_bytes(MAX_WIRE_BYTES))
        except (EOFError, OSError):
            return
        if command.get("command") == "close":
            if use_cuda:
                torch.cuda.synchronize()
            return
        result, states = _command_result(
            model, tokenizer, states, cancel, command, torch, use_cuda
        )
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


@dataclass
class _Generation:
    started: float
    deadline: float
    working: Any
    logits: Any = None
    consumed: int = 0
    output: list[int] = field(default_factory=list)
    ttft: float | None = None
    reason: str = "length"


def _stop_reason(cancel: Any, deadline: float) -> str | None:
    if cancel.is_set() or time.monotonic() >= deadline:
        return "cancelled" if cancel.is_set() else "deadline"
    return None


def _prefill(
    model: Any, tokens: list[int], generation: _Generation, cancel: Any
) -> None:
    while generation.consumed < len(tokens):
        stopped = _stop_reason(cancel, generation.deadline)
        if stopped:
            generation.reason = stopped
            break
        chunk = tokens[generation.consumed : generation.consumed + 16]
        generation.logits, generation.working = model.forward(chunk, generation.working)
        generation.consumed += len(chunk)


def _sample_token(
    logits: Any,
    occurrence: dict[int, float],
    params: dict[str, Any],
    torch: Any,
    allowed_tokens: list[int] | None = None,
) -> int | None:
    logits = logits.float()
    if not bool(torch.isfinite(logits).all()):
        return None
    if params.get("profile", "chat") != "structured":
        for token, frequency in occurrence.items():
            logits[token] -= 2.0 + frequency * 0.1
    if allowed_tokens is not None:
        return max(sorted(allowed_tokens), key=lambda t: float(logits[t].item()))
    v2 = params.get("session_protocol") == "game-eval-v2"
    if params["temperature"] == 0 or (params["top_p"] == 0 and not v2):
        return int(torch.argmax(logits).item())
    # Keep v1's qualified sampler intact; v2 applies temperature before nucleus
    # selection, matching the HF evaluation worker. top_p=0 disables nucleus.
    scores = logits / params["temperature"] if v2 else logits
    probabilities = torch.softmax(scores, dim=-1)
    sorted_probabilities, indices = torch.sort(probabilities, descending=True)
    if v2 and not 0 < params["top_p"] < 1:
        selected = sorted_probabilities
    else:
        cumulative = torch.cumsum(sorted_probabilities, dim=-1)
        keep = cumulative - sorted_probabilities < params["top_p"]
        selected = torch.where(keep, sorted_probabilities, 0.0)
    if not v2:
        selected = selected ** (1.0 / params["temperature"])
    return int(indices[torch.multinomial(selected, 1)].item())


def _record_occurrence(occurrence: dict[int, float], token: int) -> None:
    for item in occurrence:
        occurrence[item] *= 0.99
    occurrence[token] = occurrence.get(token, 0.0) + 1


def _decode_steps(
    model: Any,
    tokenizer: SafeRwkvTokenizer,
    generation: _Generation,
    cancel: Any,
    params: dict[str, Any],
    torch: Any,
    use_cuda: bool,
) -> bool:
    occurrence: dict[int, float] = {}
    choices = [tokenizer.encode(value) for value in params.get("allowed_outputs", ())]
    for _ in range(params["max_new_tokens"]):
        stopped = _stop_reason(cancel, generation.deadline)
        if stopped:
            generation.reason = stopped
            break
        assert generation.logits is not None
        allowed = None
        if choices:
            prefix = generation.output
            allowed = sorted(
                {
                    candidate[len(prefix)]
                    for candidate in choices
                    if candidate[: len(prefix)] == prefix
                    and len(candidate) > len(prefix)
                }
            )
            if not allowed:
                return False
        token = _sample_token(generation.logits, occurrence, params, torch, allowed)
        if token is None:
            return False
        if token == 0:
            generation.reason = "eos"
            break
        generation.output.append(token)
        generation.logits, generation.working = model.forward(
            [token], generation.working
        )
        _record_occurrence(occurrence, token)
        if use_cuda:
            torch.cuda.synchronize()
        if generation.ttft is None:
            generation.ttft = time.monotonic() - generation.started
        if choices and generation.output in choices:
            generation.reason = "allowed_output"
            break
        if "\n\n" in tokenizer.decode(generation.output):
            generation.reason = "stop_sequence"
            break
    return True


def _generation_receipt(
    generation: _Generation,
    tokenizer: SafeRwkvTokenizer,
    params: dict[str, Any],
    torch: Any,
    use_cuda: bool,
) -> dict[str, Any]:
    return {
        "text": tokenizer.decode(generation.output).split("\n\n", 1)[0].strip(),
        "raw_text": tokenizer.decode(generation.output),
        "stop_reason": generation.reason,
        "input_tokens": generation.consumed,
        "output_tokens": len(generation.output),
        "ttft_s": generation.ttft,
        "generation_s": time.monotonic() - generation.started,
        "quiescent": True,
        "effective_parameters": {
            **params,
            "num_steps": None,
            "num_steps_requested": params.get("num_steps", 8),
            "num_steps_applied": None,
            "sampling_profile": "temperature_then_nucleus_v2"
            if params.get("session_protocol") == "game-eval-v2"
            else "rwkv_chat_v1",
            "alpha_presence": 0.0 if params.get("profile") == "structured" else 2.0,
            "alpha_frequency": 0.0 if params.get("profile") == "structured" else 0.1,
            "alpha_decay": 0.99,
            "prefill_chunk_tokens": 16,
            "decoding_constraint": "allowed_outputs"
            if params.get("allowed_outputs")
            else "none",
        },
        "peak_vram_bytes": torch.cuda.max_memory_allocated() if use_cuda else 0,
        "peak_ram_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
    }


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
    if params.get("num_steps", 8) != 8:
        return {"error": "unsupported_compute_steps"}
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
    generation = _Generation(started, started + command["timeout_s"], working)
    _prefill(model, prompt_tokens, generation, cancel)
    if generation.consumed == len(prompt_tokens) and not _decode_steps(
        model, tokenizer, generation, cancel, params, torch, use_cuda
    ):
        return {"error": "nonfinite_logits"}
    if use_cuda:
        torch.cuda.synchronize()
    if generation.reason not in {"cancelled", "deadline"}:
        states[participant] = {
            "tensors": generation.working,
            "tokens": previous["tokens"] + generation.consumed + len(generation.output),
        }
    return _generation_receipt(generation, tokenizer, params, torch, use_cuda)
