"""Versioned synthetic rubric, independent of model consensus and runner truth.

Evaluates exported evidence only. This module never loads a model, mutates a run,
or treats proposal/accept as proof of executed work or learning.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from .errors import LabError

DATASET_VERSION = "cooperation-synthetic-v1"
RUBRIC_VERSION = "strict-final-and-delivery-v1"
MODES = ("single", "self_correction", "no_contact", "dialog", "dialog_encouraged")
MODEL_IDS = ("rwkv7-g1d-0.4b", "qwen3-4b-control")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
TERMINAL = {"completed", "failed", "cancelled", "interrupted"}


@dataclass(frozen=True)
class Rubric:
    scenario_id: str
    version: str
    goal: str
    private_a: str
    private_b: str
    expected: str


# Deliberately independent of scenarios.py and its expected field. Changing a
# scenario requires a new dataset/rubric version, never a post-hoc score patch.
RUBRICS = (
    Rubric(
        "split_facts",
        "1",
        "Find the two-letter code.",
        "The first letter is R.",
        "The second letter is K.",
        "RK",
    ),
    Rubric(
        "organization",
        "1",
        "Find the sum of the two private numbers.",
        "Your private number is 17.",
        "Your private number is 25.",
        "42",
    ),
    Rubric(
        "correction",
        "1",
        "A proposed sum is 41. Verify or correct it using both private numbers.",
        "Your private number is 17.",
        "Your private number is 25.",
        "42",
    ),
)


def build_plan(
    *,
    matrix: bool = False,
    max_turns: int = 4,
    max_new_tokens: int = 32,
    seed: int = 17,
    model_ids: Iterable[str] = MODEL_IDS,
) -> list[dict[str, Any]]:
    if (
        max_turns not in {2, 4}
        or type(max_turns) is not int
        or type(max_new_tokens) is not int
        or not 1 <= max_new_tokens <= 32
        or type(seed) is not int
        or not 0 <= seed < 2**31
    ):
        raise LabError("invalid_experiment_budget", 422)
    models = tuple(model_ids)
    if (
        not models
        or len(models) > 2
        or len(set(models)) != len(models)
        or any(model not in MODEL_IDS for model in models)
    ):
        raise LabError("model_not_allowed", 422)
    scenarios = RUBRICS if matrix else RUBRICS[:1]
    modes = MODES if matrix else ("dialog_encouraged",)
    return [
        {
            "model_id": model,
            "scenario_id": rubric.scenario_id,
            "mode": mode,
            "seed": seed,
            "max_turns": max_turns,
            "max_new_tokens": max_new_tokens,
            "temperature": 0.0,
            "top_p": 0.0,
        }
        for model in models
        for rubric in scenarios
        for mode in modes
    ]


def _integer(value: Any) -> bool:
    return type(value) is int and value >= 0


def _finite(value: Any) -> bool:
    return type(value) in (int, float) and 0 <= value <= 10**15 and math.isfinite(value)


def _answer(content: str, rubric: Rubric) -> tuple[str | None, str]:
    value = content.strip()
    if value.startswith("{"):
        try:
            structured = json.loads(value)
        except (ValueError, RecursionError):
            return None, "ambiguous_format"
        if (
            not isinstance(structured, dict)
            or set(structured) != {"answer"}
            or type(structured["answer"]) not in (str, int)
        ):
            return None, "ambiguous_format"
        value = str(structured["answer"]).strip()
    # An explicit, unique final marker permits preceding discussion. Multiple
    # contradictory markers remain unscorable rather than selecting the best.
    finals = re.findall(r"(?im)^final(?: answer)?\s*:\s*([^\n]+)$", value)
    if len(finals) > 1:
        return None, "ambiguous_format"
    if finals:
        if not re.fullmatch(
            r"(?i)final(?: answer)?\s*:\s*[^\n]+", value.splitlines()[-1]
        ):
            return None, "ambiguous_format"
        value = finals[0].strip()
    if rubric.scenario_id == "split_facts":
        match = re.fullmatch(
            r"(?i)(?:(?:the )?(?:code|answer)(?: is)?\s*[:=]?\s+)?([a-z]{2})[.]?", value
        )
        candidate = match[1].upper() if match else None
    else:
        match = re.fullmatch(
            r"(?i)(?:(?:the )?(?:sum|answer|result)(?: is)?"
            r"\s*[:=]?\s+)?(-?\d{1,4})[.]?",
            value,
        )
        arithmetic = re.fullmatch(
            r"(?:17\s*\+\s*25|25\s*\+\s*17)\s*=\s*(-?\d{1,4})[.]?", value
        )
        selected = match or arithmetic
        candidate = selected[1] if selected else None
    if candidate is None:
        return None, "ambiguous_format"
    return candidate, "correct" if candidate == rubric.expected else "incorrect"


def _validated_export(document: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if (
        not isinstance(document, dict)
        or type(document.get("schema_version")) is not int
        or document.get("schema_version") != 1
        or not isinstance(document.get("run"), dict)
        or not isinstance(document.get("events"), list)
        or len(document["events"]) > 4096
    ):
        raise LabError("invalid_experiment_export", 422)
    run = document["run"]
    if not isinstance(run.get("status"), str) or run["status"] not in (
        "created",
        "queued",
        "preparing",
        "running",
        "cancelling",
        "completed",
        "failed",
        "cancelled",
        "interrupted",
    ):
        raise LabError("invalid_experiment_status", 422)
    if (
        not isinstance(run.get("id"), str)
        or not _IDENTIFIER.fullmatch(run["id"])
        or not isinstance(run.get("config"), dict)
    ):
        raise LabError("invalid_experiment_export", 422)
    result: dict[int, dict[str, Any]] = {}
    for event in document["events"]:
        if (
            not isinstance(event, dict)
            or event.get("run_id") != run["id"]
            or not _integer(event.get("seq"))
            or event["seq"] < 1
            or not _finite(event.get("timestamp"))
            or not isinstance(event.get("payload"), dict)
            or not isinstance(event.get("kind"), str)
        ):
            raise LabError("invalid_experiment_event", 422)
        if event["seq"] in result and result[event["seq"]] != event:
            raise LabError("conflicting_experiment_event", 422)
        result[event["seq"]] = event
    events = [result[key] for key in sorted(result)]
    if any(event["seq"] != index for index, event in enumerate(events, start=1)):
        raise LabError("incomplete_experiment_events", 422)
    if not _integer(run.get("last_seq")) or run["last_seq"] != (
        events[-1]["seq"] if events else 0
    ):
        raise LabError("incomplete_experiment_events", 422)
    return run, events


def _messages(
    events: list[dict[str, Any]], mode: str, run_id: str
) -> list[dict[str, Any]]:
    messages = []
    seen = set()
    for event in events:
        if event["kind"] != "message":
            continue
        message = event["payload"]
        if (
            message.get("run_id") != run_id
            or message.get("sequence") != event["seq"]
            or message.get("sender") not in ("A", "B")
            or message.get("recipient") not in ("A", "B", "all")
            or not isinstance(message.get("message_id"), str)
            or not _IDENTIFIER.fullmatch(message["message_id"])
            or message["message_id"] in seen
            or not isinstance(message.get("content"), str)
            or len(message["content"].encode()) > 16384
            or not isinstance(message.get("delivered_to"), list)
        ):
            raise LabError("invalid_experiment_message", 422)
        if message["recipient"] == message["sender"]:
            raise LabError("invalid_experiment_delivery", 422)
        delivered = message["delivered_to"]
        if (
            len(delivered) > 2
            or not all(isinstance(recipient, str) for recipient in delivered)
            or len(set(delivered)) != len(delivered)
            or any(
                recipient not in {"A", "B"} or recipient == message["sender"]
                for recipient in delivered
            )
            or (mode in {"single", "self_correction", "no_contact"} and delivered)
            or (
                mode in {"dialog", "dialog_encouraged"}
                and delivered != ["B" if message["sender"] == "A" else "A"]
            )
        ):
            raise LabError("invalid_experiment_delivery", 422)
        if message.get("in_reply_to") is not None and (
            not isinstance(message["in_reply_to"], str)
            or message["in_reply_to"] not in seen
        ):
            raise LabError("invalid_experiment_reply", 422)
        seen.add(message["message_id"])
        messages.append({**message, "event_seq": event["seq"]})
    return messages


def _turn_evidence(
    events: list[dict[str, Any]], messages: list[dict[str, Any]]
) -> bool:
    starts = [
        event
        for event in events
        if event["kind"] == "turn" and event["payload"].get("status") == "generating"
    ]
    usage = [event for event in events if event["kind"] == "usage"]
    if (
        not messages
        or len(messages) > 8
        or len(starts) != len(messages)
        or len(usage) != len(messages)
    ):
        return False
    seen = set()
    last_message_seq = 0
    for message in messages:
        turn_id = message.get("turn_id")
        if (
            not isinstance(turn_id, str)
            or not _IDENTIFIER.fullmatch(turn_id)
            or turn_id in seen
        ):
            return False
        seen.add(turn_id)
        begin = [
            event for event in starts if event["payload"].get("turn_id") == turn_id
        ]
        cost = [event for event in usage if event["payload"].get("turn_id") == turn_id]
        if (
            len(begin) != 1
            or len(cost) != 1
            or begin[0]["payload"].get("participant_id") != message["sender"]
            or begin[0]["seq"] <= last_message_seq
            or not begin[0]["seq"] < cost[0]["seq"] < message["event_seq"]
        ):
            return False
        last_message_seq = message["event_seq"]
    return True


def _deliveries(
    messages: list[dict[str, Any]], events: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    delivered = []
    for source in messages:
        for recipient in source["delivered_to"]:
            turn = next(
                (
                    event
                    for event in events
                    if event["seq"] > source["event_seq"]
                    and event["kind"] == "turn"
                    and event["payload"].get("participant_id") == recipient
                    and event["payload"].get("status") == "generating"
                ),
                None,
            )
            response = next(
                (
                    message
                    for message in messages
                    if message["event_seq"] > (turn["seq"] if turn else 2**31)
                    and message["sender"] == recipient
                    and turn is not None
                    and message.get("turn_id") == turn["payload"].get("turn_id")
                    and any(
                        event["kind"] == "usage"
                        and event["payload"].get("turn_id") == message.get("turn_id")
                        and turn["seq"] < event["seq"] < message["event_seq"]
                        for event in events
                    )
                    and message.get("in_reply_to") == source["message_id"]
                ),
                None,
            )
            delivered.append(
                {
                    "message_id": source["message_id"],
                    "source_seq": source["event_seq"],
                    "sender": source["sender"],
                    "recipient": recipient,
                    "recipient_turn_seq": turn["seq"] if turn else None,
                    "reply_seq": response["event_seq"] if response else None,
                    "reply_source": response.get("reply_source") if response else None,
                    "host_context_consumed": response is not None,
                    "response_observed": response is not None,
                    "explicit_acceptance": bool(
                        response
                        and source.get("kind") == "proposal"
                        and response.get("kind") == "accept"
                        and response.get("reply_source") == "model"
                    ),
                }
            )
    return delivered


def _usage(events: list[dict[str, Any]]) -> dict[str, Any]:
    usage = [event["payload"] for event in events if event["kind"] == "usage"]
    if len(usage) > 8:
        raise LabError("invalid_experiment_usage", 422)
    result: dict[str, Any] = {
        "turns": len(usage),
        "per_turn": [],
        "truncation_count": 0,
        "unknown_stop_reason_count": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "charged_input_tokens": 0,
        "charged_output_tokens": 0,
        "generation_s": 0.0,
        "ttft_s": [],
    }
    for item in usage:
        for actual, charged in (
            ("input_tokens", "charged_input_tokens"),
            ("output_tokens", "charged_output_tokens"),
        ):
            maximum = 2048 if actual == "input_tokens" else 256
            if (
                not _integer(item.get(charged))
                or item[charged] > maximum
                or (
                    item.get(actual) is not None
                    and (not _integer(item[actual]) or item[actual] > item[charged])
                )
            ):
                raise LabError("invalid_experiment_usage", 422)
            result[charged] += item[charged]
            if item.get(actual) is None or result[actual] is None:
                result[actual] = None
            else:
                result[actual] += item[actual]
        duration, ttft = item.get("generation_s"), item.get("ttft_s")
        if (
            duration is not None
            and not _finite(duration)
            or ttft is not None
            and not _finite(ttft)
        ):
            raise LabError("invalid_experiment_usage", 422)
        result["generation_s"] = (
            None
            if duration is None or result["generation_s"] is None
            else result["generation_s"] + duration
        )
        result["ttft_s"].append(ttft)
        reason = item.get("stop_reason")
        safe_reason = (
            reason
            if isinstance(reason, str) and re.fullmatch(r"[a-z0-9_]{1,64}", reason)
            else None
        )
        truncated = (
            True
            if safe_reason in {"length", "max_tokens", "max_new_tokens", "token_limit"}
            else False
            if safe_reason in {"stop", "eos", "stop_sequence", "cancelled", "deadline"}
            else None
        )
        result["truncation_count"] += truncated is True
        result["unknown_stop_reason_count"] += truncated is None
        parameters = item.get("effective_parameters")
        allowed = {
            "max_new_tokens",
            "max_context_tokens",
            "temperature",
            "top_p",
            "seed",
            "alpha_presence",
            "alpha_frequency",
            "alpha_decay",
            "prefill_chunk_tokens",
            "context_mode",
            "think",
            "keep_alive",
            "input_bound_method",
        }
        effective = (
            {
                key: value
                for key, value in parameters.items()
                if key in allowed
                and (
                    type(value) is bool
                    or _finite(value)
                    or isinstance(value, str)
                    and len(value) <= 80
                )
            }
            if isinstance(parameters, dict)
            else {}
        )
        turn_id = item.get("turn_id")
        result["per_turn"].append(
            {
                "turn_id": turn_id
                if isinstance(turn_id, str) and _IDENTIFIER.fullmatch(turn_id)
                else None,
                "stop_reason": safe_reason,
                "truncated": truncated,
                "effective_parameters": effective,
                **{
                    name: item.get(name)
                    for name in (
                        "input_tokens",
                        "output_tokens",
                        "charged_input_tokens",
                        "charged_output_tokens",
                        "ttft_s",
                        "generation_s",
                    )
                },
            }
        )
    if not usage:
        result["input_tokens"], result["output_tokens"], result["generation_s"] = (
            None,
            None,
            None,
        )
    return result


def _partition(config: dict[str, Any], rubric: Rubric) -> bool | None:
    prompts = config.get("prompts")
    if (
        not isinstance(prompts, list)
        or len(prompts) != 2
        or not all(
            isinstance(prompt, str) and "\nPrivate information: " in prompt
            for prompt in prompts
        )
    ):
        return None
    private = [prompt.rsplit("\nPrivate information: ", 1)[1] for prompt in prompts]
    if config["mode"] in {"single", "self_correction"}:
        return all(
            rubric.private_a in value and rubric.private_b in value for value in private
        )
    return (
        rubric.private_a in private[0]
        and rubric.private_b not in private[0]
        and rubric.private_b in private[1]
        and rubric.private_a not in private[1]
    )


def _quiescence_evidence(
    run: dict[str, Any], events: list[dict[str, Any]]
) -> tuple[bool | None, str, int | None, bool | None]:
    ends = [event for event in events if event["kind"] == "end"]
    if not ends:
        return None, "unconfirmed", None, None
    end = ends[-1]
    value = end["payload"].get("quiescent")
    original = value if type(value) is bool else None
    if end["payload"].get("status") != run.get("status"):
        return None, "unconfirmed", None, original
    if original is True:
        return True, "end", end["seq"], original
    last = events[-1]
    if (
        original is False
        and run.get("status") in {"failed", "cancelled", "interrupted"}
        and last["seq"] > end["seq"]
        and last["kind"] == "run"
        and last["payload"].get("status") == run["status"]
        and last["payload"].get("quiescent") is True
        and last["payload"].get("cleanup_late") is True
    ):
        return True, "cleanup_late", last["seq"], original
    return original, "unconfirmed", None, original


def evaluate_export(document: Any) -> dict[str, Any]:
    run, events = _validated_export(document)
    config = run["config"]
    rubric = next(
        (
            item
            for item in RUBRICS
            if item.scenario_id == config.get("scenario_id")
            and item.version == str(config.get("scenario_version"))
        ),
        None,
    )
    if rubric is None or config.get("mode") not in MODES:
        raise LabError("unsupported_experiment_version", 422)
    messages = _messages(events, config["mode"], run["id"])
    participants: dict[str, Any] = {}
    for name in ("A", "B"):
        final = next(
            (message for message in reversed(messages) if message["sender"] == name),
            None,
        )
        answer, outcome = (
            _answer(final["content"], rubric) if final else (None, "no_answer")
        )
        participants[name] = {
            "answer": answer,
            "outcome": outcome,
            "message_seq": final["event_seq"] if final else None,
            "declared_complete": bool(final and final.get("kind") == "complete"),
        }
    last = messages[-1] if messages else None
    candidate, outcome = (
        _answer(last["content"], rubric) if last else (None, "no_answer")
    )
    turns_verified = _turn_evidence(events, messages)
    delivery = _deliveries(messages, events)
    ends = [event["payload"] for event in events if event["kind"] == "end"]
    quiescent, proof_kind, proof_seq, end_quiescent = _quiescence_evidence(run, events)
    receipts = [
        event["payload"]["runtime_receipt"]
        for event in events
        if isinstance(event["payload"].get("runtime_receipt"), dict)
    ]
    receipt = receipts[-1] if receipts else {}
    model = config.get("model") if isinstance(config.get("model"), dict) else {}
    clean_model = {
        key: model.get(key)
        if isinstance(model.get(key), str) and len(model[key]) <= 256
        else None
        for key in (
            "model_id",
            "digest",
            "revision",
            "runtime",
            "quantization",
            "template_hash",
            "tokenizer_hash",
        )
    }
    config_hash = config.get("config_hash")
    hash_valid = False
    if isinstance(config_hash, str) and re.fullmatch(r"[a-f0-9]{64}", config_hash):
        canonical = {
            key: value for key, value in config.items() if key != "config_hash"
        }
        try:
            hash_valid = (
                hashlib.sha256(
                    json.dumps(
                        canonical, sort_keys=True, ensure_ascii=False, allow_nan=False
                    ).encode()
                ).hexdigest()
                == config_hash
            )
        except (ValueError, TypeError, RecursionError):
            pass
    partition = _partition(config, rubric)
    terminal_match = bool(ends and ends[-1].get("status") == run.get("status"))
    verified = (
        turns_verified
        and terminal_match
        and quiescent is True
        and partition is True
        and hash_valid
        and config.get("scenario_goal") == rubric.goal
        and run.get("status") == "completed"
    )
    success = (
        outcome == "correct"
        if verified and outcome in {"correct", "incorrect"}
        else None
    )
    return {
        "schema_version": 1,
        "dataset_version": DATASET_VERSION,
        "rubric_version": RUBRIC_VERSION,
        "run_id": run["id"],
        "technical_status": run.get("status"),
        "quiescent": quiescent,
        "end_quiescent": end_quiescent,
        "quiescence_evidence": proof_kind,
        "quiescence_evidence_seq": proof_seq,
        "scenario_id": rubric.scenario_id,
        "scenario_version": rubric.version,
        "mode": config["mode"],
        "seed": config.get("seed"),
        "model": clean_model,
        "config_hash": config_hash if hash_valid else None,
        "config_hash_valid": hash_valid,
        "budgets": {
            key: value
            for key, value in config.get("budgets", {}).items()
            if key
            in {
                "max_turns",
                "max_new_tokens",
                "max_context_tokens",
                "total_input_tokens",
                "total_output_tokens",
                "processing_steps",
                "wall_seconds",
            }
            and _integer(value)
        }
        if isinstance(config.get("budgets"), dict)
        else {},
        "information": "privileged_full_information"
        if config["mode"] in {"single", "self_correction"}
        else "partitioned",
        "input_partition_verified": partition,
        "turn_evidence_verified": turns_verified,
        "scoring_reason": outcome
        if verified
        else (
            "run_not_completed"
            if run.get("status") != "completed"
            else "terminal_evidence_unconfirmed"
            if not terminal_match or quiescent is not True
            else "turn_evidence_unconfirmed"
            if not turns_verified
            else "input_partition_unverified"
        ),
        "technical_completion_confirmed": run.get("status") == "completed"
        and terminal_match
        and quiescent is True,
        "final_answer": candidate,
        "task_outcome": outcome if success is not None else "unscorable",
        "task_success": success,
        "participants": participants,
        "communication_observed": turns_verified
        and any(item["response_observed"] for item in delivery),
        "peer_deliveries": delivery,
        "organization": {
            "proposals_declared": sum(
                message.get("kind") == "proposal" for message in messages
            ),
            "acceptances_declared": sum(
                message.get("kind") == "accept" for message in messages
            ),
            "explicit_acceptance_links": sum(
                item["explicit_acceptance"] for item in delivery
            ),
            "commitment_execution": "unscorable",
            "note": (
                "Declarations and context responses do not prove execution, "
                "learning or causal improvement."
            ),
        },
        "usage": _usage(events),
        "runtime": {
            key: receipt.get(key)
            if (isinstance(receipt.get(key), str) and len(receipt[key]) <= 256)
            or type(receipt.get(key)) is bool
            or _finite(receipt.get(key))
            else None
            for key in (
                "load_s",
                "device",
                "precision",
                "strategy",
                "runtime",
                "runtime_version",
                "torch_version",
                "certifi_version",
                "filelock_version",
                "quantization",
                "weights_loaded",
            )
        },
        "wall_s": events[-1]["timestamp"] - events[0]["timestamp"] if events else None,
        "quality_gain_claim": False,
    }


def _totals(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "runs": len(records),
        "correct": sum(record.get("task_success") is True for record in records),
        "incorrect": sum(record.get("task_success") is False for record in records),
        "unscorable": sum(record.get("task_success") is None for record in records),
        "communication_observed": sum(
            record.get("communication_observed") is True for record in records
        ),
        "technical_failed": sum(
            record.get("technical_status") == "failed" for record in records
        ),
        "late_cleanup_confirmed": sum(
            record.get("quiescence_evidence") == "cleanup_late" for record in records
        ),
        "truncation_count": sum(
            record["usage"]["truncation_count"] for record in records
        ),
    }
    for name in (
        "input_tokens",
        "output_tokens",
        "generation_s",
        "charged_input_tokens",
        "charged_output_tokens",
    ):
        values = [record["usage"][name] for record in records]
        result[name] = (
            sum(values) if all(value is not None for value in values) else None
        )
    return result


def aggregate(results: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    records = list(results)
    if len(records) > 30:
        raise LabError("experiment_matrix_too_large", 422)
    modes = {
        mode: _totals([record for record in records if record.get("mode") == mode])
        for mode in MODES
    }
    groups = [
        {
            "model_id": model,
            "mode": mode,
            **_totals(
                [
                    record
                    for record in records
                    if record.get("model", {}).get("model_id") == model
                    and record.get("mode") == mode
                ]
            ),
        }
        for model in MODEL_IDS
        for mode in MODES
        if any(
            record.get("model", {}).get("model_id") == model
            and record.get("mode") == mode
            for record in records
        )
    ]
    configurations = {
        (
            record.get("model", {}).get("model_id"),
            record.get("scenario_id"),
            record.get("scenario_version"),
            record.get("seed"),
            json.dumps(record.get("budgets"), sort_keys=True),
        )
        for record in records
    }
    return {
        "schema_version": 1,
        "dataset_version": DATASET_VERSION,
        "rubric_version": RUBRIC_VERSION,
        "runs": len(records),
        "by_mode": modes,
        "by_model_mode": groups,
        "comparison_groups": len(configurations),
        "quality_gain_claim": False,
        "limitations": [
            "Tiny single-seed tasks provide feasibility evidence, not a ranking.",
            "Single/self_correction have full info; no_contact is partitioned.",
            "Compare actual/charged costs; dialogue alone is not learning.",
            "Ambiguous formatting remains unknown; no best-of-answer extraction.",
        ],
    }
