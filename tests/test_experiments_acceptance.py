from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_experiments import exported, late_cleanup_export

from venom_module_cooperation_lab.errors import LabError
from venom_module_cooperation_lab.experiments import MODEL_IDS, MODES, build_plan

SPEC = importlib.util.spec_from_file_location(
    "run_acceptance", Path(__file__).parents[1] / "scripts" / "run_acceptance.py"
)
acceptance = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(acceptance)


class Clock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value

    def sleep(self, duration):
        self.value += duration


class FakeClient(acceptance.LocalClient):
    def __init__(self):
        self.timer = Clock()
        super().__init__(clock=self.timer, sleep=self.timer.sleep)
        self.calls = []
        self.retries = 0
        self.active = False
        self.cancelled = False
        self.quiet = True
        self.ready = True
        self.qualified = True
        self.case = None

    def request(self, method, path, payload=None, headers=None, timeout=5):
        self.calls.append((method, path, payload, headers))
        if path == "/capabilities":
            return {
                "ready": self.ready,
                "models": [
                    {"model_id": model, "qualified": self.qualified}
                    for model in MODEL_IDS
                ],
                "modes": list(MODES),
                "scenarios": [
                    {"scenario_id": scenario, "version": "1"}
                    for scenario in ("split_facts", "organization", "correction")
                ],
            }
        if method == "POST" and path == "/runs":
            self.case = payload
            if self.retries:
                self.retries -= 1
                raise acceptance.AmbiguousRequest()
            return {"run": {"id": "run1", "status": "queued"}, "created": True}
        if method == "POST" and path.endswith("/cancel"):
            self.cancelled = True
            return {"run": {"id": "run1", "status": "cancelling"}}
        if method == "GET" and path.endswith("/export"):
            document = exported(
                model_id=self.case["model_id"],
                seed=self.case["seed"],
                answers=("R", "RK"),
            )
            document["events"][-1]["payload"]["quiescent"] = self.quiet
            return document
        if method == "GET":
            return {
                "run": {
                    "id": "run1",
                    "status": "cancelled"
                    if self.cancelled
                    else "running"
                    if self.active
                    else "completed",
                }
            }
        return None


def test_cli_default_and_matrix_are_pure_plan(capsys):
    client = FakeClient()
    assert acceptance.main([], client=client) == 0
    assert len(json.loads(capsys.readouterr().out)["cases"]) == 2
    assert acceptance.main(["--matrix"], client=client) == 0
    assert len(json.loads(capsys.readouterr().out)["cases"]) == 30
    assert client.calls == []


def test_explicit_execution_requires_output_and_bounded_case_count(tmp_path):
    with pytest.raises(LabError, match="acceptance_execution_limit"):
        acceptance.main(["--execute"])
    with pytest.raises(LabError, match="acceptance_execution_limit"):
        acceptance.main(["--execute", "--matrix", "--output-dir", str(tmp_path)])


def test_one_real_api_flow_fixture_no_inference_and_private_output(tmp_path, capsys):
    client = FakeClient()
    assert (
        acceptance.main(
            ["--execute", "--model", MODEL_IDS[0], "--output-dir", str(tmp_path)],
            client=client,
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    target = Path(result["output_directory"])
    assert (target.stat().st_mode & 0o777) == 0o700
    summary = target / "summary.json"
    assert (summary.stat().st_mode & 0o777) == 0o600
    assert json.loads(summary.read_text())["quality_gain_claim"] is False
    assert not list(target.glob("*export*"))
    assert json.loads((target / "started-01.json").read_text())["run_id"] == "run1"
    assert all("11434" not in call[1] for call in client.calls)


def test_start_retry_reuses_body_and_key_and_never_loads_directly():
    client = FakeClient()
    client.retries = 1
    case = build_plan()[0]
    assert client.execute_case(case, "samekey")["task_success"] is True
    creates = [call for call in client.calls if call[:2] == ("POST", "/runs")]
    assert len(creates) == 2 and creates[0][2:] == creates[1][2:]
    client.retries = 2
    with pytest.raises(acceptance.AmbiguousRequest):
        client.execute_case(case, "samekey2")


def test_preflight_blocks_unqualified_or_unavailable_models():
    client = FakeClient()
    client.ready = False
    with pytest.raises(LabError, match="laboratory_not_ready"):
        client.preflight(build_plan())
    client.ready, client.qualified = True, False
    with pytest.raises(LabError, match="model_not_qualified"):
        client.preflight(build_plan())
    assert not [call for call in client.calls if call[0] == "POST"]


def test_deadline_cancels_only_known_run_and_waits_for_confirmation():
    client = FakeClient()
    client.active = True
    with pytest.raises(LabError, match="acceptance_deadline"):
        client.execute_case(build_plan()[0], "owned", timeout_s=1)
    assert client.cancelled
    assert [call[1] for call in client.calls if call[0] == "POST"] == [
        "/runs",
        "/runs/run1/cancel",
    ]


def test_no_quiescence_means_no_delete_and_no_next_case():
    client = FakeClient()
    client.quiet = False
    with pytest.raises(LabError, match="acceptance_quiescence_unconfirmed"):
        client.execute_case(build_plan()[0], "owned", delete_after=True)
    assert not [call for call in client.calls if call[0] == "DELETE"]
    client.quiet = True
    client.execute_case(build_plan()[0], "owned2", delete_after=True)
    assert ("DELETE", "/runs/run1") in [call[:2] for call in client.calls]


def test_bounded_offline_evaluation_never_contacts_api(tmp_path, capsys):
    source = tmp_path / "export.json"
    source.write_text(json.dumps(exported()))
    client = FakeClient()
    assert acceptance.main(["--evaluate", str(source)], client=client) == 0
    assert json.loads(capsys.readouterr().out)["task_success"] is True
    assert client.calls == []
    with pytest.raises(LabError, match="invalid_evaluation_request"):
        acceptance.main(["--evaluate", str(source), "--execute"])


def test_local_transport_fixed_url_size_and_redirect(tmp_path):
    client = acceptance.LocalClient()
    seen = []

    class Response(io.BytesIO):
        status = 200

    def open_request(request, *, timeout):
        seen.append(request.full_url)
        return Response(b'{"ready":true}')

    client.opener = SimpleNamespace(open=open_request)
    assert client.request("GET", "/capabilities") == {"ready": True}
    assert seen == ["http://127.0.0.1:8800/api/v1/cooperation-lab/capabilities"]
    with pytest.raises(LabError, match="invalid_local_path"):
        client.request("GET", "//../other")
    client.opener = SimpleNamespace(
        open=lambda *args, **kw: Response(b"x" * (4 * 1024**2 + 1))
    )
    with pytest.raises(LabError, match="local_response_too_large"):
        client.request("GET", "/runs")
    with pytest.raises(LabError, match="local_redirect_rejected"):
        acceptance.NoRedirect().redirect_request(
            None, None, 302, "moved", {}, "http://remote"
        )


def test_reports_never_overwrite_existing_file(tmp_path):
    acceptance.save_private(tmp_path, "report.json", {"a": 1})
    with pytest.raises(FileExistsError):
        acceptance.save_private(tmp_path, "report.json", {"a": 2})
    assert json.loads((tmp_path / "report.json").read_text()) == {"a": 1}


def test_failure_to_persist_started_id_cancels_only_created_run():
    client = FakeClient()

    def fail(_run_id):
        raise OSError("local report disk full")

    with pytest.raises(OSError):
        client.execute_case(build_plan()[0], "owned", on_created=fail)
    assert client.cancelled


class LateCleanupClient(FakeClient):
    def __init__(self, ready_after):
        super().__init__()
        self.ready_after = ready_after
        self.export_reads = 0

    def request(self, method, path, payload=None, headers=None, timeout=5):
        result = super().request(method, path, payload, headers, timeout)
        if method == "GET" and path.endswith("/export"):
            self.export_reads += 1
            document = late_cleanup_export()
            # Keep the exact CLI requested immutable seed/model identity.
            document["run"]["config"] = exported(
                model_id=self.case["model_id"], seed=self.case["seed"]
            )["run"]["config"]
            if self.ready_after is None or self.export_reads < self.ready_after:
                document["events"].pop()
                document["run"]["last_seq"] -= 1
            return document
        if method == "GET" and path == "/runs/run1":
            return {"run": {"id": "run1", "status": "failed"}}
        return result


def test_cli_refetches_only_same_export_for_late_cleanup_and_keeps_failed_status():
    client = LateCleanupClient(3)
    result = client.execute_case(build_plan()[0], "owned")
    assert client.export_reads == 3
    assert client.timer.value == 2
    assert result["quiescent"] is True
    assert result["technical_status"] == "failed"
    assert result["task_success"] is None
    assert [call[1] for call in client.calls if call[0] == "POST"] == ["/runs"]


def test_persistent_quarantine_stops_within_twenty_seconds_without_new_generation():
    client = LateCleanupClient(None)
    with pytest.raises(LabError, match="acceptance_quiescence_unconfirmed"):
        client.execute_case(build_plan()[0], "owned", delete_after=True)
    assert client.timer.value == 20
    assert client.export_reads <= 20
    assert [call[1] for call in client.calls if call[0] == "POST"] == ["/runs"]
    assert not [call for call in client.calls if call[0] == "DELETE"]


def test_refetch_never_accepts_another_runs_cleanup_evidence():
    class WrongRun(LateCleanupClient):
        def request(self, method, path, payload=None, headers=None, timeout=5):
            result = super().request(method, path, payload, headers, timeout)
            if method == "GET" and path.endswith("/export"):
                result["run"]["id"] = "another-run"
            return result

    client = WrongRun(1)
    with pytest.raises(LabError, match="invalid_run_export"):
        client.execute_case(build_plan()[0], "owned")
    assert client.export_reads == 1
