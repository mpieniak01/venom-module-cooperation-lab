"""Exercise metadata drift and coverage failure modes in disposable repositories."""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

HELPER = Path(__file__).resolve().parents[1] / "scripts/test_metadata.py"
spec = importlib.util.spec_from_file_location("lab_test_metadata", HELPER)
assert spec is not None and spec.loader is not None
metadata = importlib.util.module_from_spec(spec)
spec.loader.exec_module(metadata)


def write(root, name, body):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    return path


def git(root, *args):
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout


@pytest.fixture
def repository(tmp_path):
    git(tmp_path, "init", "--initial-branch=main")
    git(tmp_path, "config", "user.name", "Test")
    git(tmp_path, "config", "user.email", "test@example.invalid")
    write(tmp_path, metadata.PACKAGE + "/existing.py", "value = 1\n")
    write(tmp_path, "tests/test_base.py", "def test_base():\n    pass\n")
    write(
        tmp_path, "sonar-project.properties", "sonar.sources=" + metadata.PACKAGE + "\n"
    )
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "fixture")
    git(tmp_path, "update-ref", "refs/remotes/origin/main", "HEAD")
    return tmp_path


def xml(root, files):
    body = "<coverage><packages><package><classes>"
    for path, lines in files.items():
        body += '<class filename="' + path + '"><lines>'
        body += "".join(
            f'<line number="{line}" hits="{hits}" />' for line, hits in lines.items()
        )
        body += "</lines></class>"
    return write(
        root,
        "test-results/coverage.xml",
        body + "</classes></package></packages></coverage>",
    )


def test_catalog_and_groups_detect_missing_extra_and_changed_files(repository):
    root = repository
    with pytest.raises(ValueError, match="catalog_out_of_sync"):
        metadata.sync_catalog(root, check=True)
    metadata.sync_catalog(root, check=False)
    metadata.sync_catalog(root, check=True)
    metadata.sync_groups(root, check=False)
    metadata.sync_groups(root, check=True)
    catalog = json.loads((root / metadata.CATALOG).read_text())
    assert catalog["tests"][0]["primary_lane"] == "new-code"
    assert catalog["tests"][0]["allowed_lanes"] == ["new-code", "ci-lite", "release"]
    assert sorted(p.name for p in (root / "config/pytest-groups").iterdir()) == [
        "ci-lite.txt",
        "release.txt",
        "sonar-new-code.txt",
    ]
    group = root / "config/pytest-groups/sonar-new-code.txt"
    group.write_text("tests/test_missing.py\n")
    with pytest.raises(ValueError, match="groups_out_of_sync"):
        metadata.sync_groups(root, check=True)
    write(root, "tests/test_new.py", "def test_new():\n    pass\n")
    with pytest.raises(ValueError, match="catalog_out_of_sync"):
        metadata.sync_groups(root, check=False)
    metadata.sync_catalog(root, check=False)
    metadata.sync_groups(root, check=False)
    assert "tests/test_new.py" in group.read_text()


@pytest.mark.parametrize(
    "name", ["tests/test_benchmark_game.py", "tests/integration/test_game.py"]
)
def test_required_lane_rejects_slow_name_patterns(repository, name):
    write(repository, name, "pass\n")
    with pytest.raises(ValueError, match="slow_name"):
        metadata.sync_catalog(repository, check=False)


def test_catalog_rejects_external_symlink(repository):
    (repository / "tests/test_external.py").symlink_to(
        repository / "tests/test_base.py"
    )
    with pytest.raises(ValueError, match="symlink_test_file"):
        metadata.sync_catalog(repository, check=False)


def test_changed_lines_include_commits_index_worktree_and_untracked(repository):
    root = repository
    path = metadata.PACKAGE + "/existing.py"
    write(root, path, "value = 2\n")
    git(root, "add", path)
    git(root, "commit", "-m", "new code")
    write(root, path, "value = 2\nother = 3\n")
    git(root, "add", path)
    write(root, path, "value = 2\nother = 4\n")
    new = metadata.PACKAGE + "/new.py"
    write(root, new, "def answer():\n    return 42\n")
    base, changes = metadata.changed_lines(root, "origin/main")
    assert len(base) == 40
    assert changes[path] == {1, 2}
    assert changes[new] == {1, 2}
    with pytest.raises(ValueError, match="git_diff_base_unavailable"):
        metadata.changed_lines(root, "missing")


def test_actual_coverage_counts_only_executable_changed_lines(repository):
    root = repository
    path = metadata.PACKAGE + "/existing.py"
    write(root, path, "value = 2\n# comment\nother = 3\n")
    coverage = xml(root, {"existing.py": {1: 1, 3: 0}})
    metadata.write_provenance(root, coverage)
    report = metadata.coverage_report(
        root, root / "absent-host", coverage, "origin/main"
    )
    assert report["covered"] == 1 and report["total"] == 2
    assert report["rate_percent"] == 50 and not report["pass"]
    assert report["files"][0]["uncovered_lines"] == [3]
    assert report["required_percent"] == 80


def test_missing_file_coverage_fails_instead_of_false_hundred_percent(repository):
    root = repository
    write(root, metadata.PACKAGE + "/new.py", "def answer():\n    return 42\n")
    coverage = xml(root, {"existing.py": {1: 1}})
    metadata.write_provenance(root, coverage)
    report = metadata.coverage_report(
        root, root / "absent-host", coverage, "origin/main"
    )
    assert not report["pass"]
    assert report["missing_coverage_files"] == [metadata.PACKAGE + "/new.py"]
    assert report["rate_percent"] is None


def test_coverage_provenance_binds_xml_source_and_test_contents(repository):
    root = repository
    path = metadata.PACKAGE + "/existing.py"
    write(root, path, "value = 2\n")
    coverage = xml(root, {"existing.py": {1: 1}})
    with pytest.raises(ValueError, match="provenance_missing"):
        metadata.coverage_report(root, root, coverage, "origin/main")
    metadata.write_provenance(root, coverage)
    assert metadata.coverage_report(root, root, coverage, "origin/main")["pass"]
    write(root, "tests/test_base.py", "def test_changed():\n    pass\n")
    with pytest.raises(ValueError, match="coverage_stale"):
        metadata.coverage_report(root, root, coverage, "origin/main")
    metadata.write_provenance(root, coverage)
    coverage.write_text(coverage.read_text().replace('hits="1"', 'hits="0"'))
    with pytest.raises(ValueError, match="coverage_stale"):
        metadata.coverage_report(root, root, coverage, "origin/main")
    with pytest.raises(ValueError, match="coverage_xml_missing"):
        metadata.write_provenance(root, root / "absent.xml")


def test_host_policy_cannot_be_lowered_and_can_be_strengthened(repository):
    root = repository
    write(root, "host/make/tests.mk", "NEW_CODE_CHANGED_LINES_MIN ?= 85\n")
    assert metadata.minimum_threshold(root / "host") == 85
    with pytest.raises(ValueError, match="cannot_be_lowered"):
        metadata.coverage_report(
            root, root / "host", root / "unused", "origin/main", 80
        )
    result = metadata.coverage_report(
        root, root / "host", root / "unused", "origin/main", 90
    )
    assert result["pass"] and result["status"] == "not_applicable"
    assert result["rate_percent"] is None and result["required_percent"] == 90


def test_documentation_only_and_exclusions_are_explicit(repository):
    root = repository
    write(root, metadata.PACKAGE + "/notes.py", '"""A module docstring."""\n')
    coverage = xml(root, {"existing.py": {1: 1}})
    metadata.write_provenance(root, coverage)
    report = metadata.coverage_report(root, root, coverage, "origin/main")
    assert report["pass"] and report["status"] == "no_executable_changes"
    write(root, "sonar-project.properties", "sonar.coverage.exclusions=**/notes.py\n")
    report = metadata.coverage_report(root, root, coverage, "origin/main")
    assert report["status"] == "not_applicable"


def test_cli_failures_return_nonzero_and_reports_are_durable(repository, capsys):
    root = repository
    assert metadata.main(["catalog-check", "--root", str(root)]) == 1
    assert "out_of_sync" in capsys.readouterr().err
    for command in ("catalog-sync", "catalog-check", "groups-sync", "groups-check"):
        assert metadata.main([command, "--root", str(root)]) == 0
    assert metadata.main(["coverage", "--root", str(root), "--host", str(root)]) == 0
    report = json.loads((root / "test-results/changed-lines-coverage.json").read_text())
    assert report["status"] == "not_applicable"
    write(root, metadata.PACKAGE + "/existing.py", "value = 2\n")
    assert metadata.main(["coverage", "--root", str(root), "--host", str(root)]) == 1
    coverage = xml(root, {"existing.py": {1: 0}})
    assert metadata.main(["coverage-stamp", "--root", str(root)]) == 0
    assert metadata.main(["coverage", "--root", str(root), "--host", str(root)]) == 1
    assert not metadata.coverage_hits(root, coverage)[
        metadata.PACKAGE + "/existing.py"
    ][1]
