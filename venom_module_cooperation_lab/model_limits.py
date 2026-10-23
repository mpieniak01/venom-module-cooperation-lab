"""Local output ceilings; not native context lengths or quality guarantees.

RWKV/Ollama retain the extended 1024-token adapter range. The costly HF
experiments retain the exercised 256-token range instead of assuming that
an unqualified 1024-token generation fits their decision deadline.
"""

from typing import Any

MAX_REQUESTED_TOKENS = 2**31 - 1


def output_token_limit(model: dict[str, Any]) -> int:
    if model.get("architecture") in {"hrm_text", "huginn_raven"}:
        return 256
    if model.get("architecture") == "rwkv7" or (
        model.get("provider") == "ollama"
        and str(model.get("runtime", "")).startswith("ollama==")
    ):
        return 1024
    return 256


def applied_output_tokens(requested: int, model: dict[str, Any]) -> int:
    return min(requested, output_token_limit(model))
