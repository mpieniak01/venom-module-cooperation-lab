"""Explicit operator provisioning of one pinned model and tiny runtime wheel.

No dependencies installed into Full. Invoke manually; not imported by startup,
API or tests. The host must already provide qualified Torch 2.13 / CUDA 13.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import os
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from venom_module_cooperation_lab.adapters.component import (  # noqa: E402
    OVERLAY_PINS,
    checked_members,
    verify_overlay,
)

MODEL_REVISION = "2a17e911155a5be23a4ed2792e978c77038f14e2"
MODEL_FILENAME = "rwkv7-g1d-0.4b-20260210-ctx8192.pth"
MODEL_SHA256 = "947cb9b8013224e06b112b72204256bec65096cc935a7767ce63d8e3ddef83bb"
MODEL_BYTES = 901776749
WHEEL_URL = "https://files.pythonhosted.org/packages/5b/61/d7c764f01da87145342a8cdc3a86690e03cda4dfc2cf20377bdf5dc86b05/rwkv-0.8.32-py3-none-any.whl"
WHEEL_SHA256 = "d3f0594810a4a7e91569f177003ec22294c3eabc91c5f8d0ff3511702d4b67c1"


def download(url: str, target: Path, expected: str, size: int) -> None:
    if target.exists():
        with target.open("rb") as stream:
            if (
                target.stat().st_size == size
                and hashlib.file_digest(stream, "sha256").hexdigest() == expected
            ):
                return
        raise RuntimeError("existing_artifact_mismatch")
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".partial")
    total, digest = 0, hashlib.sha256()
    created = False
    try:
        with partial.open("xb") as stream:
            created = True
            with urllib.request.urlopen(url, timeout=60) as source:
                while chunk := source.read(4 * 1024**2):
                    total += len(chunk)
                    if total > size:
                        raise RuntimeError("artifact_size_exceeded")
                    stream.write(chunk)
                    digest.update(chunk)
        if total != size or digest.hexdigest() != expected:
            raise RuntimeError("artifact_hash_mismatch")
        os.link(partial, target)
    finally:
        if created:
            partial.unlink(missing_ok=True)


def install_overlay(runtime_root: Path, wheel_cache: Path | None = None) -> None:
    if not runtime_root.is_absolute() or (
        wheel_cache is not None and not wheel_cache.is_absolute()
    ):
        raise ValueError("absolute_paths_required")
    root = runtime_root.resolve()
    if runtime_root.is_symlink():
        raise RuntimeError("unsafe_runtime_archive")
    for pin in OVERLAY_PINS:
        cached = wheel_cache / pin.filename if wheel_cache else None
        if cached is not None:
            if not cached.is_file() or cached.stat().st_size != pin.size:
                raise RuntimeError("component_wheel_hash_mismatch")
            wheel = cached.read_bytes()
        else:
            with urllib.request.urlopen(pin.url, timeout=30) as source:
                wheel = source.read(pin.size + 1)
        files = checked_members(wheel, pin)
        files[f".wheel-pins/{pin.filename}"] = wheel
        # Preflight the complete wheel before writing any file from it.
        for name, payload in files.items():
            target = root / name
            if target.is_symlink() or not target.resolve().is_relative_to(root):
                raise RuntimeError("unsafe_runtime_archive")
            if target.exists() and (
                not target.is_file() or target.read_bytes() != payload
            ):
                raise RuntimeError("existing_runtime_mismatch")
        for name, payload in files.items():
            target = root / name
            if target.exists():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as destination:
                destination.write(payload)
    verify_overlay(root)


def provision(model_root: Path, runtime_root: Path, storage_root: Path) -> None:
    if not all(path.is_absolute() for path in (model_root, runtime_root, storage_root)):
        raise ValueError("absolute_paths_required")
    if shutil.disk_usage(storage_root).free < 5 * 1024**3:
        raise RuntimeError("insufficient_backing_volume_space")
    model = model_root / MODEL_REVISION / MODEL_FILENAME
    download(
        f"https://huggingface.co/BlinkDL/rwkv7-g1/resolve/{MODEL_REVISION}/{MODEL_FILENAME}",
        model,
        MODEL_SHA256,
        MODEL_BYTES,
    )
    with urllib.request.urlopen(WHEEL_URL, timeout=30) as source:
        wheel = source.read(411389)
    if len(wheel) != 411388 or hashlib.sha256(wheel).hexdigest() != WHEEL_SHA256:
        raise RuntimeError("runtime_hash_mismatch")
    runtime_root.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(wheel)) as archive:
        for member in archive.infolist():
            destination = (runtime_root / member.filename).resolve()
            if not destination.is_relative_to(runtime_root.resolve()):
                raise RuntimeError("unsafe_runtime_archive")
            if member.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
            else:
                data = archive.read(member)
                if destination.exists() and destination.read_bytes() != data:
                    raise RuntimeError("existing_runtime_mismatch")
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(data)
    install_overlay(runtime_root)
    print(
        "Pinned RWKV artefact/runtime verified. "
        "No model loaded or Full packages changed."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-root", required=True, type=Path)
    parser.add_argument("--runtime-root", required=True, type=Path)
    parser.add_argument("--storage-root", required=True, type=Path)
    parser.add_argument("--overlay-only", action="store_true")
    parser.add_argument("--wheel-cache", type=Path)
    args = parser.parse_args()
    if args.overlay_only:
        install_overlay(args.runtime_root, args.wheel_cache)
    else:
        if args.wheel_cache is not None:
            parser.error("--wheel-cache requires --overlay-only")
        provision(args.model_root, args.runtime_root, args.storage_root)


if __name__ == "__main__":
    main()
