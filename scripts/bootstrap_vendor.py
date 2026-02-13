from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

FUGASHI_VERSION = "1.5.2"
UNIDIC_VERSION = "1.0.8"
PY_VER = "313"
ABI = "cp313"

PLATFORM_TAGS: dict[str, str] = {
    "win": "win_amd64",
    "linux": "manylinux_2_17_x86_64",
    "macos_x86_64": "macosx_10_13_x86_64",
    "macos_arm64": "macosx_11_0_arm64",
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _vendor_root() -> Path:
    return _repo_root() / "vendor"


def _wheelhouse() -> Path:
    return _repo_root() / ".tmp_wheelhouse"


def _pip_download(dest: Path, package: str, platform_tag: str | None = None) -> None:
    cmd = [
        sys.executable,
        "-m",
        "pip",
        "download",
        "--no-deps",
        "--only-binary=:all:",
        "--dest",
        str(dest),
    ]
    if platform_tag:
        cmd.extend(
            [
                "--platform",
                platform_tag,
                "--implementation",
                "cp",
                "--python-version",
                PY_VER,
                "--abi",
                ABI,
            ]
        )
    cmd.append(package)
    subprocess.run(cmd, check=True)


def _pip_wheel(dest: Path, package: str) -> None:
    cmd = [
        sys.executable,
        "-m",
        "pip",
        "wheel",
        "--no-deps",
        "--wheel-dir",
        str(dest),
        package,
    ]
    subprocess.run(cmd, check=True)


def _extract_wheels(src: Path, dst: Path) -> None:
    wheels = sorted(src.glob("*.whl"))
    if not wheels:
        raise RuntimeError(f"no wheels in {src}")
    dst.mkdir(parents=True, exist_ok=True)
    for wheel in wheels:
        with zipfile.ZipFile(wheel) as zf:
            zf.extractall(dst)
        print(f"extracted {wheel.name} -> {dst}")


def _target_for_local_platform() -> str:
    sp = sys.platform.lower()
    machine = (platform.machine() or "").lower()
    if sp.startswith("win"):
        return "win"
    if sp.startswith("linux"):
        return "linux"
    if sp == "darwin":
        if machine in {"arm64", "aarch64"}:
            return "macos_arm64"
        return "macos_x86_64"
    raise RuntimeError(f"unsupported local platform: {sys.platform} / {platform.machine()}")


def _install_platform(platform_key: str) -> None:
    if platform_key not in PLATFORM_TAGS:
        raise RuntimeError(f"unsupported platform key: {platform_key}")
    wh = _wheelhouse() / platform_key
    shutil.rmtree(wh, ignore_errors=True)
    wh.mkdir(parents=True, exist_ok=True)
    _pip_download(
        wh,
        f"fugashi=={FUGASHI_VERSION}",
        platform_tag=PLATFORM_TAGS[platform_key],
    )
    out_dir = _vendor_root() / platform_key
    shutil.rmtree(out_dir, ignore_errors=True)
    _extract_wheels(wh, out_dir)


def _install_common() -> None:
    wh = _wheelhouse() / "common"
    shutil.rmtree(wh, ignore_errors=True)
    wh.mkdir(parents=True, exist_ok=True)
    _pip_wheel(wh, f"unidic-lite=={UNIDIC_VERSION}")
    out_dir = _vendor_root() / "common"
    shutil.rmtree(out_dir, ignore_errors=True)
    _extract_wheels(wh, out_dir)


def _required_files_for_platform(platform_key: str) -> list[Path]:
    root = _vendor_root()
    files: list[Path] = [
        root / platform_key / f"fugashi-{FUGASHI_VERSION}.dist-info" / "METADATA",
        root / platform_key / f"fugashi-{FUGASHI_VERSION}.dist-info" / "licenses" / "LICENSE",
        root / platform_key / f"fugashi-{FUGASHI_VERSION}.dist-info" / "licenses" / "LICENSE.mecab",
        root / "common" / f"unidic_lite-{UNIDIC_VERSION}.dist-info" / "METADATA",
        root / "common" / f"unidic_lite-{UNIDIC_VERSION}.dist-info" / "licenses" / "LICENSE",
        root / "common" / f"unidic_lite-{UNIDIC_VERSION}.dist-info" / "licenses" / "LICENSE.unidic",
    ]
    return files


def _check(targets: list[str]) -> None:
    missing: list[Path] = []
    for t in targets:
        for p in _required_files_for_platform(t):
            if not p.exists():
                missing.append(p)
    if missing:
        print("missing vendor files:")
        for p in missing:
            print(f" - {p}")
        raise SystemExit(2)
    print("vendor check ok")


def _clean() -> None:
    shutil.rmtree(_vendor_root(), ignore_errors=True)
    shutil.rmtree(_wheelhouse(), ignore_errors=True)
    print("cleaned vendor and wheel cache")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--target",
        default="local",
        choices=["local", "all", "win", "linux", "macos_x86_64", "macos_arm64"],
        help="vendor target",
    )
    ap.add_argument("--check-only", action="store_true")
    ap.add_argument("--clean", action="store_true")
    ns = ap.parse_args(argv)

    if ns.clean:
        _clean()
        return 0

    if ns.target == "local":
        targets = [_target_for_local_platform()]
    elif ns.target == "all":
        targets = ["win", "linux", "macos_x86_64", "macos_arm64"]
    else:
        targets = [ns.target]

    _vendor_root().mkdir(parents=True, exist_ok=True)
    _wheelhouse().mkdir(parents=True, exist_ok=True)

    if not ns.check_only:
        for t in targets:
            _install_platform(t)
        _install_common()
    _check(targets)
    shutil.rmtree(_wheelhouse(), ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
