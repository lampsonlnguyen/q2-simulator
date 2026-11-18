# Actual firmware execution (experimental)

This path runs `/release/bin/demo` from the selected firmware package. The
firmware executable, AWTK, fonts, layout, menu construction, and firmware patches
own every displayed pixel. The desktop only decodes the guest framebuffer and
supplies raw Linux input events. It does not implement an App Store, substitute
game rules, synthesize a music library, or select fonts for the firmware.

**This is an initial user-mode runtime, not a completed hardware emulator.**
It is not yet validated through an interactive Home screen or the Custom tab.
Opening an update package is not evidence that all its features work.

## Ubuntu / Windows 11 with WSL

Run inside Ubuntu WSL with GUI support (WSLg), or a Linux desktop:

```sh
sudo apt update
sudo apt install qemu-user proot squashfs-tools clang lld python3-venv python3-tk

bash run-firmware.sh \
  --firmware "$HOME/q2-custom-app-store-20261118-132617/update.tar" \
  --sd-card "$HOME/q2-test-sd"
```

The existing launcher also routes `--firmware` to this runtime:

```sh
bash run-simulator.sh --firmware /path/to/update.tar --sd-card /path/to/card
```

Native Windows/macOS execution is not implemented for this backend. The
packaged desktop app does not include QEMU, PRoot, or the compiler. Use WSL for
the experimental runtime. There is no automatic fallback to the Python UI.

## What executes

| Boundary | Implementation |
| --- | --- |
| Firmware UI and patched features | Original MIPS `demo`, loaded from the package |
| Shared libraries and assets | Package root filesystem |
| CPU instructions | QEMU MIPS32, P5600 ISA/NaN2008 compatibility |
| Linux system calls | QEMU user-mode translation into the host Linux kernel |
| Guest paths and child executables | PRoot, with a separate writable extracted root |
| Display | File-backed 320×375 BGRA framebuffer, three pages, pan/blank ioctls |
| Desktop image | Visible framebuffer page rotated upright to 375×320 |
| Buttons, touch, wheel | MIPS o32 evdev records consumed by firmware input code |
| SD card | Selected host directory at guest `/mnt/mmc` |
| D-Bus | Firmware `dbus-daemon`, started before `demo` |

The P5600 selection supplies the instruction/FPU features used by the binary;
it is not a model of the Q2's physical CPU and peripherals. The firmware kernel,
boot ROM, init sequence, timings, PMIC, DAC, ALSA device, Wi-Fi/Bluetooth drivers,
USB, and other vendor devices are not emulated. Unsupported device ioctls return
an error and are logged. No device result is replaced by a Python feature.

This is not a sandbox for untrusted firmware or apps. Guest processes run with
the host user's permissions and have access to the selected SD directory,
explicitly bound Linux interfaces, and host networking through system calls.

## Controls

- Enter: Centre, including a real held key when held down.
- Escape / Backspace: Return.
- Space: Play/Pause.
- Left / Right: Previous/Next.
- Click/drag: touchscreen, transformed into the panel's portrait axes.
- Mouse wheel: raw wheel gestures. The firmware applies its saved sensitivity.

The window contains only the framebuffer. Settings changes must be made inside
the firmware; there are no desktop controls that manufacture firmware state.

## Diagnostics and validation status

Each firmware SHA-256 gets its own state directory under
`~/.cache/q2-emulation/firmware-runtime/`. The executable's MIPS32 little-endian
NaN2008 header is checked. The packaged executable is not patched by the runtime;
only a device-boundary shared library is added to the extracted filesystem.
Guest settings persist there. A second concurrent session using the same state
is rejected.

```sh
# Extract and compile the bridge without starting guest processes:
bash run-firmware.sh --firmware /path/to/update.tar --prepare-only

# Run with guest syscall diagnostics:
bash run-firmware.sh --firmware /path/to/update.tar --strace

# Capture only the actual framebuffer after 10 seconds, with no Python rendering:
bash run-firmware.sh --firmware /path/to/update.tar --snapshot /tmp/q2.png --seconds 10

python3 -m unittest discover -s emulation/tests -p test_firmware_runtime.py -v
```

`demo.log` and `dbus.log` are in the printed state directory. If PRoot cannot
use `ptrace`, or Unix sockets are unavailable, startup fails with that log path.
The runtime does not display a replacement Home screen on a guest failure.

Validated here: real-package extraction, device-library cross compilation, QEMU
loading the actual executable and its original libraries/assets, successful
framebuffer initialization, and opens of keyboard/touch/wheel inputs. The test
host rejects PRoot tracing and local Unix sockets; the firmware aborts when its
required D-Bus connection is missing. No interactive screen, App Store install,
audio playback, or full hardware boot is claimed as tested.

Remaining work is to run the original service startup on a compatible host,
identify and implement the vendor device interfaces it actually requests, then
compare guest frames and input behavior against a physical Q2. A full boot needs
a board/kernel implementation beyond this user-mode path.

## Legacy Python preview

The old UI model is retained only behind an explicit option:

```sh
bash run-simulator.sh --preview
bash run-simulator.sh --preview --firmware /path/to/update.tar
```

That mode is a visual approximation. It cannot validate the firmware's Custom
tab or any other compiled UI feature. Firmware launches default to execution,
and a launch without a mode now asks for `--firmware` or `--preview`.
