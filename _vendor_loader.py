from __future__ import annotations

import os
import platform
import sys
from typing import Iterable


def _norm_machine(raw: str) -> str:
    m = (raw or "").strip().lower()
    if m in {"amd64", "x64", "x86_64"}:
        return "x86_64"
    if m in {"arm64", "aarch64"}:
        return "arm64"
    return m or "unknown"


def _platform_keys() -> list[str]:
    plat = (sys.platform or "").lower()
    machine = _norm_machine(platform.machine())
    if plat.startswith("win"):
        return [f"win_{machine}", "win"]
    if plat.startswith("linux"):
        return [f"linux_{machine}", "linux"]
    if plat == "darwin":
        return [f"macos_{machine}", "macos"]
    return [f"{plat}_{machine}", plat]


def _iter_existing(paths: Iterable[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for p in paths:
        full = os.path.abspath(p)
        key = full.lower()
        if key in seen:
            continue
        seen.add(key)
        if os.path.isdir(full):
            out.append(full)
    return out


def vendor_paths(addon_dir: str) -> list[str]:
    root = os.path.abspath(os.path.join(addon_dir, "vendor"))
    platform_dirs = [os.path.join(root, k) for k in _platform_keys()]
    common_dir = os.path.join(root, "common")
    # Keep legacy flat vendor/ as final fallback for older local setups.
    return _iter_existing([*platform_dirs, common_dir, root])


def install_vendor_paths(addon_dir: str) -> list[str]:
    installed: list[str] = []
    paths = vendor_paths(addon_dir)
    insert_at = 0
    for path in paths:
        if path not in sys.path:
            # Keep declared priority order at the front:
            # platform-specific -> common -> legacy root fallback.
            sys.path.insert(insert_at, path)
            insert_at += 1
        installed.append(path)
        if os.name == "nt":
            try:
                os.add_dll_directory(path)
            except Exception:
                pass
            libs = os.path.join(path, "fugashi.libs")
            if os.path.isdir(libs):
                try:
                    os.add_dll_directory(libs)
                except Exception:
                    pass
    return installed
