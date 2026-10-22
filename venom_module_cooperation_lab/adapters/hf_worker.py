"""Worker-only Torch/HF imports; verified local artefacts, no network."""

from __future__ import annotations

import contextlib
import ctypes
import importlib
import json
import os
import sys
import tempfile
import time
import traceback
from typing import Any


def prompt_text(
    model_id: str, messages: list[dict[str, str]], tokenizer: Any, structured: bool
) -> tuple[str, str]:
    if model_id == "huginn-0125":
        return tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        ), "native_chat"
    condition = (
        "<|object_ref_start|>" if structured else "<|quad_end|><|object_ref_end|>"
    )
    # HRM is PrefixLM, not an assistant-tuned chat model; make the task explicit.
    task = "\n".join(m["role"].title() + ": " + m["content"] for m in messages)
    if structured:
        task = (
            "Examples of short direct answers:\n"
            "Question: What is 2 + 2? Answer: 4\n"
            "Question: What is the capital of France? Answer: Paris\n"
            "Task:\n" + task
        )
    return (
        "<|im_start|>" + condition + task + "<|im_end|>",
        "direct" if structured else "synth,cot",
    )


def load_models(config: dict[str, Any]) -> tuple[Any, Any, Any]:
    torch: Any = importlib.import_module("torch")
    transformers: Any = importlib.import_module("transformers")

    if not torch.cuda.is_available():
        raise RuntimeError("cuda_unavailable")
    if (
        torch.cuda.mem_get_info()[0]
        < (4 if config["model_id"] == "hrm-text-1b" else 9) * 1024**3
    ):
        raise RuntimeError("insufficient_gpu_memory")
    if (
        torch.__version__.split("+")[0] != "2.13.0"
        or transformers.__version__ != "5.17.0"
    ):
        raise RuntimeError("runtime_identity_changed")
    torch.cuda.reset_peak_memory_stats()
    root = config["root"]
    tokenizer = transformers.AutoTokenizer.from_pretrained(root, local_files_only=True)
    factory: Any = transformers.AutoModelForCausalLM
    if config["model_id"] == "huginn-0125":
        dynamic: Any = importlib.import_module("transformers.dynamic_module_utils")
        factory = dynamic.get_class_from_dynamic_module(
            "raven_modeling_minimal.RavenForCausalLM", root, local_files_only=True
        )
        # Upstream 4.44 lists targets; Transformers 5 requires target -> source.
        # This is scoped to the pinned Huginn class in this disposable worker.
        factory._tied_weights_keys = {"lm_head.weight": "transformer.wte.weight"}
    model: Any = factory.from_pretrained(
        root,
        dtype=torch.bfloat16,
        trust_remote_code=config["model_id"] == "huginn-0125",
        local_files_only=True,
        attn_implementation="sdpa",
        low_cpu_mem_usage=True,
    )
    model = model.to("cuda").eval()
    torch.cuda.synchronize()
    return model, tokenizer, torch


def generate(
    model: Any,
    tokenizer: Any,
    torch: Any,
    config: dict[str, Any],
    command: dict[str, Any],
    cancel: Any,
) -> dict[str, Any]:
    params = command["parameters"]
    messages = json.loads(command["prompt"])
    text, condition = prompt_text(
        config["model_id"], messages, tokenizer, params["profile"] == "structured"
    )
    tokens = tokenizer.encode(text, add_special_tokens=False)
    if len(tokens) + params["max_new_tokens"] > params["max_context_tokens"]:
        raise RuntimeError("context_budget_exceeded")
    started = time.monotonic()
    deadline = started + command["timeout_s"]
    torch.manual_seed(params["seed"])
    output: list[int] = []
    cache = None
    ttft = None
    reason = "length"
    choices = [
        tokenizer.encode(v, add_special_tokens=False)
        for v in params.get("allowed_outputs", [])
    ]
    eos = tokenizer.eos_token_id
    with torch.inference_mode():
        for step in range(params["max_new_tokens"]):
            if cancel.is_set() or time.monotonic() >= deadline:
                reason = "cancelled" if cancel.is_set() else "deadline"
                break
            hrm = config["model_id"] == "hrm-text-1b"
            current = (
                tokens if step == 0 else ([output[-1]] if hrm else tokens + output)
            )
            ids = torch.tensor([current], device="cuda", dtype=torch.long)
            kwargs = {"input_ids": ids, "use_cache": hrm}
            if hrm:
                kwargs.update(
                    token_type_ids=torch.ones_like(ids)
                    if step == 0
                    else torch.zeros_like(ids),
                    past_key_values=cache,
                )
            else:
                kwargs["num_steps"] = 8
            result = model(**kwargs)
            cache = result.past_key_values if hrm else None
            logits = result.logits[0, -1].float()
            if not bool(torch.isfinite(logits).all()):
                raise RuntimeError("nonfinite_logits")
            if choices:
                allowed = sorted(
                    {
                        v[len(output)]
                        for v in choices
                        if v[: len(output)] == output and len(v) > len(output)
                    }
                )
                if not allowed:
                    raise RuntimeError("invalid_output_constraint")
                token = max(allowed, key=lambda t: float(logits[t].item()))
            elif params["temperature"] == 0:
                token = int(torch.argmax(logits).item())
            else:
                scores = logits / params["temperature"]
                probabilities = torch.softmax(scores, dim=-1)
                if 0 < params["top_p"] < 1:
                    values, indices = torch.sort(probabilities, descending=True)
                    keep = torch.cumsum(values, dim=-1) - values < params["top_p"]
                    values = torch.where(keep, values, 0.0)
                    token = int(indices[torch.multinomial(values, 1)].item())
                else:
                    token = int(torch.multinomial(probabilities, 1).item())
            if token == eos:
                reason = "eos"
                break
            output.append(token)
            torch.cuda.synchronize()
            if ttft is None:
                ttft = time.monotonic() - started
            if choices and output in choices:
                reason = "allowed_output"
                break
            if config["model_id"] == "huginn-0125" and token in {65505, 65508}:
                reason = "stop_sequence"
                break
    torch.cuda.synchronize()
    raw = tokenizer.decode(output, skip_special_tokens=False)
    visible = tokenizer.decode(output, skip_special_tokens=True).strip()
    return {
        "text": visible,
        "raw_text": raw,
        "stop_reason": reason,
        "input_tokens": len(tokens),
        "output_tokens": len(output),
        "ttft_s": ttft,
        "generation_s": time.monotonic() - started,
        "peak_vram_bytes": torch.cuda.max_memory_allocated(),
        "quiescent": True,
        "effective_parameters": {
            **params,
            "context_mode": "replay",
            "condition": condition,
            "num_steps": 8 if config["model_id"] == "huginn-0125" else None,
            "cache": "prefixlm" if config["model_id"] == "hrm-text-1b" else "disabled",
            "decoding_constraint": "allowed_outputs" if choices else "none",
        },
    }


def worker_main(
    connection: Any, cancel: Any, config: dict[str, Any], parent_pid: int
) -> None:
    if (
        sys.platform != "linux"
        or ctypes.CDLL(None).prctl(1, 9) != 0
        or os.getppid() != parent_pid
    ):
        connection.send_bytes(b'{"error":"unsupported_parent_lifecycle"}')
        return
    with tempfile.TemporaryDirectory(prefix="venom-lab-hf-code-") as cache:
        os.environ.update(
            HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_MODULES_CACHE=cache
        )
        try:
            started = time.monotonic()
            with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink):
                model, tokenizer, torch = load_models(config)
            connection.send_bytes(
                json.dumps(
                    {
                        "state": "ready",
                        "load_s": time.monotonic() - started,
                        "runtime": "hf_lab",
                        "torch_version": torch.__version__,
                        "precision": "bfloat16",
                        "device": "cuda:0",
                        "peak_vram_bytes": torch.cuda.max_memory_allocated(),
                    }
                ).encode()
            )
            while True:
                command = json.loads(connection.recv_bytes(65536))
                if command.get("command") == "close":
                    break
                try:
                    if command["command"] == "generate":
                        result = generate(
                            model, tokenizer, torch, config, command, cancel
                        )
                    elif command["command"] in {"reset", "state"}:
                        result = {"state": "ready", "quiescent": True}
                    else:
                        raise RuntimeError("unsupported_command")
                except Exception as exc:
                    traceback.print_exc()
                    result = {"error": error_code(exc)}
                result["request_id"] = command.get("request_id")
                connection.send_bytes(json.dumps(result, allow_nan=False).encode())
        except (EOFError, OSError):
            pass
        except Exception as exc:
            traceback.print_exc()
            connection.send_bytes(json.dumps({"error": error_code(exc)}).encode())
        finally:
            connection.close()


def error_code(exc: Exception) -> str:
    allowed = {
        "runtime_identity_changed",
        "cuda_unavailable",
        "insufficient_gpu_memory",
        "context_budget_exceeded",
        "nonfinite_logits",
        "invalid_output_constraint",
        "unsupported_command",
    }
    if str(exc) in allowed:
        return str(exc)
    if "OutOfMemory" in type(exc).__name__:
        return "out_of_memory"
    return "hf_worker_failed"
