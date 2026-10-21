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
        "filelock/__pycache__/unverified.cpython-314.pyc",
        "filelock/unverified.pyc",
        "filelock/unverified.pyo",
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
    monkeypatch.setattr(sys, "dont_write_bytecode", False)
    assert component.activate_overlay(tmp_path) == {"filelock_version": pin.version}
    assert sys.dont_write_bytecode
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


def test_timestamp_valid_unverified_bytecode_is_rejected_before_import(
    tmp_path, monkeypatch
):
    import importlib.util
    import marshal
    import struct
    from pathlib import Path

    pin, wheel = tiny_pin()
    monkeypatch.setattr(component, "OVERLAY_PINS", (pin,))
    put_overlay(tmp_path, pin, wheel)
    source = tmp_path / "filelock" / "__init__.py"
    cached = importlib.util.cache_from_source(str(source))
    cache = Path(cached)
    cache.parent.mkdir()
    # A valid CPython header makes ordinary import prefer this cached code even
    # though the wheel-pinned .py remains unchanged. Use a harmless marker only.
    code = compile('__version__ = "4.2.1"; review_marker = True', str(source), "exec")
    header = importlib.util.MAGIC_NUMBER + struct.pack(
        "<III", 0, int(source.stat().st_mtime), source.stat().st_size
    )
    cache.write_bytes(header + marshal.dumps(code))
    with pytest.raises(RuntimeError, match="integrity_mismatch"):
        component.activate_overlay(tmp_path)
    assert (
        source.read_bytes()
        == component.checked_members(wheel, pin)["filelock/__init__.py"]
    )


def test_actual_child_source_import_never_creates_overlay_bytecode(tmp_path):
    import json
    import os
    import subprocess
    from dataclasses import asdict

    pin, wheel = tiny_pin()
    put_overlay(tmp_path, pin, wheel)
    script = """
import json, sys
from pathlib import Path
from venom_module_cooperation_lab.adapters import component
root = Path(sys.argv[1])
component.OVERLAY_PINS = (component.WheelPin(**json.loads(sys.argv[2])),)
assert not sys.dont_write_bytecode
assert 'filelock' not in sys.modules
assert component.activate_overlay(root) == {'filelock_version': '4.2.1'}
assert sys.dont_write_bytecode
assert not list(root.rglob('*.pyc'))
component.verify_overlay(root)
print('source-import-without-bytecode-pass')
"""
    environment = dict(os.environ)
    environment.pop("PYTHONDONTWRITEBYTECODE", None)
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path), json.dumps(asdict(pin))],
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "source-import-without-bytecode-pass" in result.stdout


@pytest.mark.parametrize("location", ["package", "nested_directory"])
def test_overlay_rejects_symlinked_package_or_unlisted_directory(
    tmp_path, monkeypatch, location
):
    pin, wheel = tiny_pin()
    monkeypatch.setattr(component, "OVERLAY_PINS", (pin,))
    put_overlay(tmp_path, pin, wheel)
    package = tmp_path / "filelock"
    if location == "package":
        original = tmp_path / "verified-payload"
        package.rename(original)
        package.symlink_to(original, target_is_directory=True)
    else:
        (package / "unlisted-directory").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(RuntimeError, match="integrity_mismatch"):
        component.verify_overlay(tmp_path)
