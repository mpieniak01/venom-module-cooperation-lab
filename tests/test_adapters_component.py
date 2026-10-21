"""Overlay tests use synthetic wheels; no downloads, Torch, GPU or models."""

from __future__ import annotations

import hashlib
import io
import sys
import types
import zipfile
from dataclasses import replace

import pytest

from venom_module_cooperation_lab.adapters import component


def tiny_pin(name="filelock", version="4.2.1", filename=None):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(
            filename or f"{name}/__init__.py", f'__version__ = "{version}"'
        )
    wheel = output.getvalue()
    return component.WheelPin(
        name,
        version,
        len(wheel),
        hashlib.sha256(wheel).hexdigest(),
        "https://fixture.invalid/pinned",
    ), wheel


def put_overlay(root, pin, wheel):
    cached = root / ".wheel-pins" / pin.filename
    cached.parent.mkdir(parents=True)
    cached.write_bytes(wheel)
    for name, data in component.checked_members(wheel, pin).items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def test_overlay_integrity_missing_tamper_and_extra(tmp_path, monkeypatch):
    pin, wheel = tiny_pin()
    monkeypatch.setattr(component, "OVERLAY_PINS", (pin,))
    with pytest.raises(RuntimeError, match="overlay_missing"):
        component.verify_overlay(tmp_path)
    put_overlay(tmp_path, pin, wheel)
    component.verify_overlay(tmp_path)
    body = tmp_path / "filelock" / "__init__.py"
    body.write_text("tampered")
    with pytest.raises(RuntimeError, match="integrity_mismatch"):
        component.verify_overlay(tmp_path)
    body.write_bytes(component.checked_members(wheel, pin)["filelock/__init__.py"])
    (body.parent / "unlisted.py").write_text("unlisted")
    with pytest.raises(RuntimeError, match="integrity_mismatch"):
        component.verify_overlay(tmp_path)


@pytest.mark.parametrize(
    "filename",
    [
        "../bad.py",
        "/bad.py",
        "wrong/__init__.py",
        "filelock/../../bad.py",
        "filelock\\bad.py",
        "C:/bad.py",
    ],
)
def test_overlay_rejects_unsafe_archive(filename):
    pin, wheel = tiny_pin(filename=filename)
    with pytest.raises(RuntimeError, match="unsafe_component_archive"):
        component.checked_members(wheel, pin)


def test_overlay_pin_rejects_changed_size_or_hash():
    pin, wheel = tiny_pin()
    for invalid in (replace(pin, size=1), replace(pin, sha256="0" * 64)):
        with pytest.raises(RuntimeError, match="wheel_hash_mismatch"):
            component.checked_members(wheel, invalid)


def test_actual_effective_import_is_required(tmp_path, monkeypatch):
    pin, wheel = tiny_pin()
    monkeypatch.setattr(component, "OVERLAY_PINS", (pin,))
    put_overlay(tmp_path, pin, wheel)
    module = types.ModuleType("filelock")
    module.__version__ = pin.version
    module.__file__ = str(tmp_path / "filelock" / "__init__.py")
    monkeypatch.setitem(sys.modules, "filelock", module)
    monkeypatch.setattr(sys, "path", list(sys.path))
    assert component.activate_overlay(tmp_path) == {"filelock_version": pin.version}
    module.__file__ = "/another/environment/filelock.py"
    with pytest.raises(RuntimeError, match="overlay_not_effective"):
        component.activate_overlay(tmp_path)
    module.__file__ = str(tmp_path / "filelock" / "__init__.py")
    module.__version__ = "old"
    with pytest.raises(RuntimeError, match="overlay_not_effective"):
        component.activate_overlay(tmp_path)


def test_overlay_provision_is_idempotent_and_no_overwrite(tmp_path, monkeypatch):
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "overlay_provision", Path(__file__).parents[1] / "scripts" / "provision_rwkv.py"
    )
    provision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(provision)
    pin, wheel = tiny_pin()
    monkeypatch.setattr(component, "OVERLAY_PINS", (pin,))
    monkeypatch.setattr(provision, "OVERLAY_PINS", (pin,))
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / pin.filename).write_bytes(wheel)
    root = tmp_path / "runtime"
    provision.install_overlay(root, cache)
    provision.install_overlay(root, cache)
    target = root / "filelock" / "__init__.py"
    target.write_text("operator content")
    with pytest.raises(RuntimeError, match="existing_runtime_mismatch"):
        provision.install_overlay(root, cache)
    assert target.read_text() == "operator content"
    (cache / pin.filename).write_bytes(b"bad")
    with pytest.raises(RuntimeError, match="wheel_hash_mismatch"):
        provision.install_overlay(root, cache)
