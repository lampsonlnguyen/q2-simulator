# Q2 Emulation

Desktop simulator and experimental MIPS app emulation for the Shanling Q2 and Q2 Pod.
This repository contains the emulation work extracted from Q2 Pod's
`desktop-simulator` branch. It runs independently from a Q2 Pod checkout.

Firmware packages now default to an **experimental actual-firmware runtime**.
QEMU executes the package's MIPS UI executable and libraries; the desktop displays
its framebuffer. It does not recreate firmware menus in Python. This is initial
user-mode execution, **not a complete hardware emulator**. Interactive startup
and the Custom App Store tab are not yet validated. See the
[firmware runtime and current blockers](emulation/docs/firmware-runtime.md).

The older Python UI model remains available explicitly with `--preview`. It
approximates firmware behavior and cannot test compiled firmware UI changes.

## Download a packaged app

Preview releases automatically build downloadable packages for **Windows x64**, **Linux x64**, **macOS Intel**, and **macOS Apple Silicon**. Download the ZIP or tarball for your platform from [Releases](https://github.com/lampsonlnguyen/q2-emulation/releases), extract it, and launch `Q2-Simulator.exe`, `Q2-Simulator`, or `Q2-Simulator.app` as applicable. Python and pip are not required for preview packages. They do not bundle the
experimental firmware runtime dependencies. Use `--preview` when launching
a package built from this branch.

macOS bundles are currently unsigned; Gatekeeper may require **Control-click → Open**, or approval in **System Settings → Privacy & Security**. Linux requires a compatible desktop system with the usual GUI libraries. Advanced MIPS game compilation still depends on an external LLVM toolchain; music playback uses an external `ffplay` executable; firmware extraction uses `unsquashfs`. These external tools are **not** bundled in this release workflow. The sample UI preview runs without them.

The packaging workflow is in [`.github/workflows/release-apps.yml`](.github/workflows/release-apps.yml). It builds on a **published release** and can be run manually via **Actions → Build Q2 Simulator release apps → Run workflow** for downloadable test artifacts. A manual run does not attach files to a release.

## Start the simulator

Clone this repository, then run the launcher from its root.

```sh
git clone https://github.com/lampsonlnguyen/q2-emulation.git
cd q2-emulation
bash run-simulator.sh --preview
```

For the legacy preview on Windows, run this in PowerShell. Actual firmware
execution currently requires Linux or Ubuntu WSL.

```powershell
.\run-simulator.bat --preview
```

The launcher creates `emulation/.venv-simulator` and installs the Python
dependencies. Use Python 3.10 or newer with Tkinter. Ubuntu and WSL users can
install the system dependencies with the following command.

```sh
sudo apt install python3 python3-venv python3-tk clang lld binutils squashfs-tools ffmpeg qemu-user proot
```

`clang` with MIPS support and `ld.lld` compile the built-in game previews.
`unsquashfs` reads firmware packages. `ffplay`, supplied by FFmpeg, plays music.
On Windows, the built-in game compiler uses an Ubuntu WSL installation with
`clang` and `lld`. On macOS, install Homebrew LLVM and SquashFS tools and use
a Python installation with Tkinter. See the [platform setup guide](emulation/docs/desktop-simulator.md).

## Load firmware and an SD folder

```sh
bash run-simulator.sh --firmware "/path/to/update.tar" --sd-card "/path/to/SD-card"
```

Official Shanling firmware ZIPs are also supported. The actual firmware runtime
uses Linux/WSL, QEMU, PRoot, and a compiler for its Linux device bridge. It reports
startup failures; it never silently falls back to the Python UI. See the
[runtime guide](emulation/docs/firmware-runtime.md) for preparation, diagnostics,
and validation limits.

For the old asset/UI approximation, explicitly use `--preview --firmware PATH`.
An invocation with no mode asks you to choose firmware execution or preview.
Mounted SD folders persist downloads and save files across sessions.

## Games and validation

```sh
bash run-emulator.sh --self-test
bash run-emulator.sh --game snake
```

The [MIPS guide](emulation/docs/unicorn-emulator.md) covers controls and installed
card apps. The [game ABI guide](emulation/docs/game-compatibility.md) covers
standalone games using the experimental generic interface.

GitHub Actions runs the extracted tests on pushes to `main` and pull requests,
including MIPS execution, generic game ABI checks, Buddy, App Store behavior,
SD-card discovery, audio synchronization, and screenshots.

## Source and license

Code is distributed under [GPL-3.0](LICENSE). The bundled fonts retain their
license notices in [assets/fonts](assets/fonts). [UPSTREAM.md](UPSTREAM.md)
records the source revision and the supporting files copied from Q2 Pod.
