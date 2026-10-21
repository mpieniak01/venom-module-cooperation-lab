"""Provisioner safety tests use tiny in-memory artefacts, never the network."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location(
    "provision_rwkv", Path(__file__).parents[1] / "scripts" / "provision_rwkv.py"
)
provision = importlib.util.module_from_spec(spec)
spec.loader.exec_module(provision)


def test_download_is_atomic_and_preserves_existing_data(tmp_path, monkeypatch):
    target = tmp_path / "model.pth"
    payload = b"tiny model"
    digest = hashlib.sha256(payload).hexdigest()
    monkeypatch.setattr(
        provision.urllib.request, "urlopen", lambda *args, **kw: io.BytesIO(payload)
    )
    provision.download("https://fixture.invalid/model", target, digest, len(payload))
    assert target.read_bytes() == payload
    provision.download("https://fixture.invalid/model", target, digest, len(payload))
    target.write_bytes(b"other")
    with pytest.raises(RuntimeError, match="existing_artifact_mismatch"):
        provision.download(
            "https://fixture.invalid/model", target, digest, len(payload)
        )
    assert target.read_bytes() == b"other"


@pytest.mark.parametrize(
    "size,digest,reason",
    [(1, "bad", "artifact_size_exceeded"), (99, "bad", "artifact_hash_mismatch")],
)
def test_bad_download_leaves_no_partial_file(
    tmp_path, monkeypatch, size, digest, reason
):
    target = tmp_path / "model.pth"
    monkeypatch.setattr(
        provision.urllib.request, "urlopen", lambda *args, **kw: io.BytesIO(b"invalid")
    )
    with pytest.raises(RuntimeError, match=reason):
        provision.download("https://fixture.invalid/model", target, digest, size)
    assert not target.exists()
    assert not target.with_suffix(".pth.partial").exists()


def test_preexisting_partial_is_never_deleted(tmp_path, monkeypatch):
    target = tmp_path / "model.pth"
    partial = target.with_suffix(".pth.partial")
    partial.write_bytes(b"belongs to previous operator action")
    with pytest.raises(FileExistsError):
        provision.download("https://fixture.invalid/model", target, "bad", 1)
    assert partial.read_bytes() == b"belongs to previous operator action"


def test_physical_storage_and_absolute_paths_are_required(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="absolute_paths_required"):
        provision.provision(Path("relative"), tmp_path, tmp_path)
    monkeypatch.setattr(shutil, "disk_usage", lambda _: SimpleNamespace(free=1))
    with pytest.raises(RuntimeError, match="insufficient_backing_volume_space"):
        provision.provision(tmp_path, tmp_path, tmp_path)


def test_runtime_wheel_must_match_pin(tmp_path, monkeypatch):
    monkeypatch.setattr(
        shutil, "disk_usage", lambda _: SimpleNamespace(free=10 * 1024**3)
    )
    monkeypatch.setattr(provision, "download", lambda *args: None)
    monkeypatch.setattr(
        provision.urllib.request,
        "urlopen",
        lambda *args, **kw: io.BytesIO(b"untrusted wheel"),
    )
    with pytest.raises(RuntimeError, match="runtime_hash_mismatch"):
        provision.provision(tmp_path / "models", tmp_path / "runtime", tmp_path)
