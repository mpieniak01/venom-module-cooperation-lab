#!/usr/bin/env python3
"""Plan or explicitly execute tiny public-synthetic experiments on local Venom.

Default is pure planning. --execute alone is still limited to two short runs.
No model download, arbitrary URL, engine selection or runtime-policy mutation.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from venom_module_cooperation_lab.errors import LabError  # noqa: E402
from venom_module_cooperation_lab.experiments import (  # noqa: E402
    DATASET_VERSION,
    MODEL_IDS,
    RUBRICS,
    aggregate,
    build_plan,
    evaluate_export,
)

BASE = "http://127.0.0.1:8800/api/v1/cooperation-lab"
MAX_BYTES = 4 * 1024**2
SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
TERMINAL = {"completed", "failed", "cancelled", "interrupted"}


class AmbiguousRequest(LabError):
    def __init__(self) -> None:
        super().__init__("local_transport_unavailable")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        raise LabError("local_redirect_rejected")


class LocalClient:
    def __init__(self, *, clock=time.monotonic, sleep=time.sleep) -> None:
        self.clock, self.sleep = clock, sleep
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), NoRedirect()
        )

    def request(
        self,
        method: str,
        path: str,
        payload: Any = None,
        headers: dict[str, str] | None = None,
        timeout: float = 5,
    ) -> Any:
        # This method is internal; caller paths are constants plus validated IDs.
        if not path.startswith("/") or ".." in path or "?" in path or "#" in path:
            raise LabError("invalid_local_path")
        body = (
            None if payload is None else json.dumps(payload, allow_nan=False).encode()
        )
        request = urllib.request.Request(
            BASE + path,
            data=body,
            method=method,
            headers={"Content-Type": "application/json", **(headers or {})},
        )
        try:
            with self.opener.open(request, timeout=timeout) as response:
                raw = response.read(MAX_BYTES + 1)
                if len(raw) > MAX_BYTES:
                    raise LabError("local_response_too_large")
                if response.status == 204:
                    return None
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            code = "local_api_rejected"
            try:
                document = json.loads(exc.read(8192))
                detail = document.get("detail", document)
                candidate = (
                    detail
                    if isinstance(detail, str)
                    else detail.get("reason_code", detail.get("code"))
                )
                if isinstance(candidate, str) and re.fullmatch(
                    r"[a-z0-9_]{1,80}", candidate
                ):
                    code = candidate
            except (ValueError, TypeError, AttributeError):
                pass
            raise LabError(code, exc.code) from None
        except (urllib.error.URLError, OSError) as exc:
            raise AmbiguousRequest() from exc
        except (ValueError, RecursionError) as exc:
            raise LabError("invalid_local_response") from exc

    def preflight(self, cases: list[dict[str, Any]]) -> None:
        capabilities = self.request("GET", "/capabilities")
        if not isinstance(capabilities, dict) or capabilities.get("ready") is not True:
            raise LabError("laboratory_not_ready")
        models = capabilities.get("models", [])
        scenarios = capabilities.get("scenarios", [])
        qualified = {
            model.get("model_id")
            for model in models
            if isinstance(model, dict) and model.get("qualified") is True
        }
        versions = {
            scenario.get("scenario_id"): str(scenario.get("version"))
            for scenario in scenarios
            if isinstance(scenario, dict)
        }
        for case in cases:
            if case["model_id"] not in qualified:
                raise LabError("model_not_qualified")
            if versions.get(case["scenario_id"]) != next(
                rubric.version
                for rubric in RUBRICS
                if rubric.scenario_id == case["scenario_id"]
            ):
                raise LabError("unsupported_experiment_version")
            if case["mode"] not in capabilities.get("modes", []):
                raise LabError("experiment_mode_unavailable")

    def _start(self, case: dict[str, Any], key: str) -> dict[str, Any]:
        # Recover a lost HTTP response using the exact same key/body, never a new
        # generation disguised as retry. Failure after both attempts aborts batch.
        for attempt in range(2):
            try:
                result = self.request("POST", "/runs", case, {"Idempotency-Key": key})
                row = result.get("run") if isinstance(result, dict) else None
                if (
                    not isinstance(row, dict)
                    or not isinstance(row.get("id"), str)
                    or not SAFE_ID.fullmatch(row["id"])
                ):
                    raise LabError("invalid_created_run")
                return row
            except AmbiguousRequest:
                if attempt == 1:
                    raise
        raise LabError("start_unconfirmed")

    def _wait(self, run_id: str, deadline: float) -> dict[str, Any]:
        while self.clock() < deadline:
            result = self.request(
                "GET",
                "/runs/" + run_id,
                timeout=min(5, max(0.1, deadline - self.clock())),
            )
            row = result.get("run") if isinstance(result, dict) else None
            if not isinstance(row, dict) or row.get("id") != run_id:
                raise LabError("invalid_run_snapshot")
            if row.get("status") in TERMINAL:
                return row
            self.sleep(0.2)
        raise LabError("acceptance_deadline")

    def _cancel_and_wait(self, run_id: str) -> None:
        self.request("POST", "/runs/" + run_id + "/cancel")
        self._wait(run_id, self.clock() + 20)

    def execute_case(
        self,
        case: dict[str, Any],
        key: str,
        *,
        timeout_s: float = 180,
        delete_after: bool = False,
        on_created: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        row = self._start(case, key)
        run_id = row["id"]
        try:
            if on_created is not None:
                on_created(run_id)
            self._wait(run_id, self.clock() + timeout_s)
        except BaseException:
            # Cancels only this known run; no runtime/engine/global STOP calls.
            self._cancel_and_wait(run_id)
            raise
        report = self._confirmed_export(run_id, case)
        if delete_after:
            self.request("DELETE", "/runs/" + run_id)
        return report

    def _read_export(
        self, run_id: str, case: dict[str, Any], timeout: float
    ) -> dict[str, Any]:
        document = self.request("GET", "/runs/" + run_id + "/export", timeout=timeout)
        if (
            not isinstance(document, dict)
            or not isinstance(document.get("run"), dict)
            or document["run"].get("id") != run_id
        ):
            raise LabError("invalid_run_export")
        config = document.get("run", {}).get("config", {})
        model = config.get("model", {})
        if (
            model.get("model_id") != case["model_id"]
            or any(
                config.get(name) != case[name]
                for name in ("scenario_id", "mode", "seed")
            )
            or any(
                config.get("budgets", {}).get(name) != case[name]
                for name in ("max_turns", "max_new_tokens")
            )
        ):
            raise LabError("experiment_identity_mismatch")
        return evaluate_export(document)

    def _confirmed_export(self, run_id: str, case: dict[str, Any]) -> dict[str, Any]:
        # A failed terminal record may precede its real close/join by a few
        # seconds. Only fetch the same export; never retry generation or release.
        deadline = self.clock() + 20
        report = self._read_export(run_id, case, 5)
        for _ in range(20):
            if report["quiescent"] is True:
                return report
            if (
                report["technical_status"] not in {"failed", "cancelled", "interrupted"}
                or report["end_quiescent"] is not False
                or self.clock() >= deadline
            ):
                break
            self.sleep(min(1, deadline - self.clock()))
            remaining = deadline - self.clock()
            if remaining <= 0:
                break
            report = self._read_export(run_id, case, min(5, remaining))
        raise LabError("acceptance_quiescence_unconfirmed")


def save_private(directory: Path, name: str, document: Any) -> None:
    payload = json.dumps(
        document, indent=2, ensure_ascii=False, allow_nan=False
    ).encode()
    if len(payload) > MAX_BYTES:
        raise LabError("acceptance_report_too_large")
    descriptor = os.open(directory / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)


def save_started(directory: Path, index: int, key: str, run_id: str) -> None:
    save_private(
        directory,
        f"started-{index + 1:02d}.json",
        {"run_id": run_id, "idempotency_key": key},
    )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "--execute",
        action="store_true",
        help="Explicitly start bounded runs on the existing local host",
    )
    result.add_argument(
        "--matrix",
        action="store_true",
        help="Plan all 30 cases; execution also requires --max-runs 30",
    )
    result.add_argument("--model", action="append", choices=MODEL_IDS)
    result.add_argument("--max-runs", type=int, choices=range(1, 31), default=2)
    result.add_argument("--turns", type=int, choices=(2, 4), default=4)
    result.add_argument("--tokens", type=int, choices=range(1, 33), default=32)
    result.add_argument("--seed", type=int, default=17)
    result.add_argument("--timeout", type=int, choices=range(10, 181), default=180)
    result.add_argument("--output-dir", type=Path)
    result.add_argument(
        "--delete-after",
        action="store_true",
        help="Delete only completed records owned by this invocation's unique keys",
    )
    result.add_argument(
        "--evaluate",
        type=Path,
        help="Evaluate one bounded local export without network or inference",
    )
    return result


def main(argv: list[str] | None = None, *, client: LocalClient | None = None) -> int:
    args = parser().parse_args(argv)
    if args.evaluate:
        if args.execute or args.evaluate.stat().st_size > MAX_BYTES:
            raise LabError("invalid_evaluation_request")
        result = evaluate_export(json.loads(args.evaluate.read_text()))
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    cases = build_plan(
        matrix=args.matrix,
        max_turns=args.turns,
        max_new_tokens=args.tokens,
        seed=args.seed,
        model_ids=args.model or MODEL_IDS,
    )
    plan = {
        "schema_version": 1,
        "dataset_version": DATASET_VERSION,
        "public_synthetic_only": True,
        "execute": args.execute,
        "cases": cases,
        "default_no_inference": True,
    }
    if not args.execute:
        print(json.dumps(plan, indent=2))
        return 0
    if len(cases) > args.max_runs or args.output_dir is None:
        raise LabError("acceptance_execution_limit")
    target = args.output_dir / ("acceptance-" + uuid4().hex)
    target.mkdir(parents=True, mode=0o700)
    keys = [uuid4().hex for _ in cases]
    save_private(
        target,
        "plan.json",
        {
            **plan,
            "idempotency_keys": keys,
            "created_utc": datetime.now(UTC).isoformat(),
        },
    )
    connection = client or LocalClient()
    connection.preflight(cases)
    reports = []
    for index, (case, key) in enumerate(zip(cases, keys, strict=True)):
        report = connection.execute_case(
            case,
            key,
            timeout_s=args.timeout,
            delete_after=args.delete_after,
            on_created=partial(save_started, target, index, key),
        )
        save_private(target, f"run-{index + 1:02d}.json", report)
        reports.append(report)
    summary = aggregate(reports)
    save_private(target, "summary.json", summary)
    print(
        json.dumps(
            {
                "result": "recorded",
                "runs": len(reports),
                "output_directory": str(target),
                "quality_gain_claim": False,
            }
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (LabError, OSError, ValueError, RecursionError) as error:
        code = error.code if isinstance(error, LabError) else "acceptance_input_failed"
        print(json.dumps({"result": "failed", "code": code}), file=sys.stderr)
        raise SystemExit(1) from None
