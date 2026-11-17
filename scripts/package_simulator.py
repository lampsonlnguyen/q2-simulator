#!/usr/bin/env python3
"""Build and smoke-test platform-native Q2 Simulator release archives."""
import os
import platform
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
NAME = "Q2-Simulator"

def run(*args):
    print("+", *map(str, args), flush=True)
    subprocess.run([str(a) for a in args], cwd=ROOT, check=True)

def main():
    system = platform.system()
    if system not in ("Windows", "Darwin", "Linux"):
        raise SystemExit(f"Unsupported build platform: {system}")
    pyinstaller = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--name", NAME, "--windowed", "--paths", str(ROOT / "tools"),
        "--hidden-import", "art", "--hidden-import", "build",
        "--hidden-import", "ipod", "--hidden-import", "theme",
        "--collect-all", "unicorn",
    ]
    for folder in ("assets", "patch"):
        pyinstaller.extend(("--add-data", f"{ROOT / folder}{os.pathsep}{folder}"))
    for folder in ("abi",):
        pyinstaller.extend(("--add-data", f"{ROOT / 'emulation' / folder}{os.pathsep}emulation/{folder}"))
    for source in (ROOT / "emulation").glob("*.c"):
        pyinstaller.extend(("--add-data", f"{source}{os.pathsep}emulation"))
    if system != "Darwin":
        pyinstaller.append("--onefile")
    else:
        pyinstaller.append("--onedir")
    pyinstaller.append(str(ROOT / "emulation" / "simulator.py"))
    run(*pyinstaller)

    DIST.mkdir(exist_ok=True)
    if system == "Darwin":
        app = DIST / f"{NAME}.app"
        assert app.is_dir(), f"Missing macOS .app: {app}"
        arch = "arm64" if platform.machine().lower() in ("arm64", "aarch64") else "x64"
        archive = DIST / f"{NAME}-macOS-{arch}.zip"
        # ditto preserves bundle permissions, symlinks and macOS metadata.
        run("ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", app, archive)
    elif system == "Windows":
        binary = DIST / f"{NAME}.exe"
        assert binary.is_file(), f"Missing Windows executable: {binary}"
        archive = DIST / f"{NAME}-Windows-x64.zip"
        import zipfile
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as out:
            out.write(binary, binary.name)
    else:
        binary = DIST / NAME
        assert binary.is_file(), f"Missing Linux executable: {binary}"
        archive = DIST / f"{NAME}-Linux-x64.tar.gz"
        with tarfile.open(archive, "w:gz") as out:
            out.add(binary, arcname=binary.name)

    # Confirm that the frozen executable can load fonts/assets and render a frame.
    binary = (DIST / f"{NAME}.app" / "Contents" / "MacOS" / NAME) if system == "Darwin" else (
        DIST / (f"{NAME}.exe" if system == "Windows" else NAME))
    screenshot = DIST / "simulator-smoke.png"
    run(binary, "--snapshot", screenshot, "--screen", "home", "--with-device")
    if not screenshot.is_file() or screenshot.stat().st_size < 1000:
        raise SystemExit("Frozen simulator smoke test did not produce an image")
    print("Release archive:", archive)

if __name__ == "__main__":
    main()
