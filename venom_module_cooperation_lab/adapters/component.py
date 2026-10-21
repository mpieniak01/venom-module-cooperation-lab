"""Small pinned security overlay, checked before importing the shared Torch stack."""

from __future__ import annotations

import hashlib
import importlib
import io
import stat
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


@dataclass(frozen=True)
class WheelPin:
    name: str
    version: str
    size: int
    sha256: str
    url: str

    @property
    def filename(self) -> str:
        return f"{self.name}-{self.version}-py3-none-any.whl"


OVERLAY_PINS = (
    WheelPin(
        "certifi",
        "2026.10.19",
        136464,
        "42d35340cc5b9ba78e818ddbff0c5b1c2b779de448a340fd1b989f5fa8670e1b",
        "https://files.pythonhosted.org/packages/c4/51/29046e48f693c54e5b7412216d447a1d8362c9653148d98c02cdf65fa733/certifi-2026.10.19-py3-none-any.whl",
    ),
    WheelPin(
        "filelock",
        "4.2.1",
        162455,
        "7be2662e9e826b9bba28afc0f843a123280d799a2ea44bb5d35ccec67905ae44",
        "https://files.pythonhosted.org/packages/28/00/db89d339bc4ecdc8087fa7b8607ba22ffc27bf96286f340c9620bea428b3/filelock-4.2.1-py3-none-any.whl",
    ),
)
OVERLAY_RUNTIME = ";".join(f"{pin.name}=={pin.version}" for pin in OVERLAY_PINS)


def checked_members(wheel: bytes, pin: WheelPin) -> dict[str, bytes]:
    if len(wheel) != pin.size or hashlib.sha256(wheel).hexdigest() != pin.sha256:
        raise RuntimeError("component_wheel_hash_mismatch")
    files: dict[str, bytes] = {}
    with zipfile.ZipFile(io.BytesIO(wheel)) as archive:
        members = archive.infolist()
        if len(members) > 1024 or sum(item.file_size for item in members) > 8 * 1024**2:
            raise RuntimeError("unsafe_component_archive")
        for item in members:
            path = PurePosixPath(item.filename)
            if (
                path.is_absolute()
                or ".." in path.parts
                or "__pycache__" in path.parts
                or path.suffix in {".pyc", ".pyo"}
                or "\\" in item.filename
                or not path.parts
                or ":" in path.parts[0]
                or stat.S_ISLNK(item.external_attr >> 16)
                or item.filename in files
                or path.parts[0]
                not in {pin.name, f"{pin.name}-{pin.version}.dist-info"}
            ):
                raise RuntimeError("unsafe_component_archive")
            if not item.is_dir():
                files[item.filename] = archive.read(item)
    return files


def _verify_pinned_files(root: Path, files: dict[str, bytes]) -> None:
    for name, expected in files.items():
        path = root / name
        if (
            not path.is_file()
            or path.is_symlink()
            or not path.resolve().is_relative_to(root)
            or path.read_bytes() != expected
        ):
            raise RuntimeError("component_overlay_integrity_mismatch")


def _reject_unlisted_files(root: Path, package: Path, files: dict[str, bytes]) -> None:
    if package.is_symlink():
        raise RuntimeError("component_overlay_integrity_mismatch")
    for path in package.rglob("*"):
        if path.is_symlink() or (
            path.is_file() and path.relative_to(root).as_posix() not in files
        ):
            raise RuntimeError("component_overlay_integrity_mismatch")


def verify_overlay(runtime_root: Path) -> None:
    root = runtime_root.resolve()
    for pin in OVERLAY_PINS:
        wheel_path = root / ".wheel-pins" / pin.filename
        if not wheel_path.is_file() or wheel_path.is_symlink():
            raise RuntimeError("component_overlay_missing")
        files = checked_members(wheel_path.read_bytes(), pin)
        _verify_pinned_files(root, files)
        _reject_unlisted_files(root, root / pin.name, files)


def activate_overlay(runtime_root: Path) -> dict[str, str]:
    """Only the isolated child calls this; never mutate the host import paths."""
    verify_overlay(runtime_root)
    # Only this isolated child changes the flag. Verification rejects all existing
    # bytecode; suppressing new caches keeps subsequent source imports verifiable.
    sys.dont_write_bytecode = True
    root = runtime_root.resolve()
    sys.path.insert(0, str(root))
    versions = {}
    for pin in OVERLAY_PINS:
        module = importlib.import_module(pin.name)
        location = getattr(module, "__file__", None)
        if (
            getattr(module, "__version__", None) != pin.version
            or not isinstance(location, str)
            or not Path(location).resolve().is_relative_to(root / pin.name)
        ):
            raise RuntimeError("component_overlay_not_effective")
        versions[f"{pin.name}_version"] = pin.version
    return versions
