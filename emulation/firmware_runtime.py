#!/usr/bin/env python3
"""Experimental execution of the packaged Q2 UI, with no desktop menu renderer.

QEMU executes demo and its libraries. PRoot supplies the firmware filesystem.
The preload implements only Linux framebuffer/evdev devices. This is user-mode
execution, not an emulation of the Q2 kernel or a full Ingenic board.
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import shlex
import shutil
import signal
import struct
import subprocess
import sys
import time
import uuid

HERE = Path(__file__).resolve().parent
WIDTH, HEIGHT, STRIDE, PAGES = 320, 375, 1280, 3
FB_SIZE = STRIDE * HEIGHT * PAGES
KEYS = {'Return': 116, 'Escape': 103, 'BackSpace': 103,
        'space': 108, 'Left': 165, 'Right': 163}


def tool(name):
    result = shutil.which(name)
    if not result:
        raise RuntimeError(f'Missing {name}. On Ubuntu/WSL: sudo apt install '
                           'qemu-user proot squashfs-tools clang lld python3-tk')
    return result


def validate_demo(path):
    with path.open('rb') as source:
        header = source.read(52)
    if (len(header) != 52 or header[:7] != b'\x7fELF\x01\x01\x01' or
            struct.unpack_from('<H', header, 18)[0] != 8 or
            not struct.unpack_from('<I', header, 36)[0] & 0x400):
        raise ValueError('Expected a little-endian MIPS32 NaN2008 Q2 demo executable')


def image_hash(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def compile_devices(target):
    source = HERE / 'firmware_devices.c'
    common = ['-fPIC', '-mabi=32', '-march=mips32r2', '-mfp64', '-mnan=2008',
              '-O2', '-Wall', '-Wextra', '-Werror', '-fno-stack-protector']
    libraries = [str(target.parent / name) for name in ('libdl.so.2', 'libc.so.6')]
    gcc = shutil.which('mipsel-linux-gnu-gcc')
    if gcc:
        subprocess.run([gcc, *common, '-shared', '-nostdlib', '-Wl,--hash-style=sysv',
                        str(source), *libraries, '-o', str(target)], check=True)
    else:
        obj = target.with_suffix('.o')
        subprocess.run([tool('clang'), '--target=mipsel-linux-gnu', *common,
                        '-c', str(source), '-o', str(obj)], check=True)
        subprocess.run([tool('ld.lld'), '-m', 'elf32ltsmip', '-shared',
                        '--hash-style=sysv', str(obj), *libraries, '-o', str(target)], check=True)
        obj.unlink()


def event(kind, code, value):
    now = time.time_ns() // 1000
    return struct.pack('<IIHHi', now // 1000000, now % 1000000, kind, code, value)


def touch_sample(x, y, down):
    if not 0 <= x < HEIGHT or not 0 <= y < WIDTH:
        raise ValueError('Touch coordinates must be inside the 375 x 320 display')
    return (event(3, 0, WIDTH - 1 - y) + event(3, 1, x) +
            event(3, 24, int(down)) + event(1, 330, int(down)) + event(0, 0, 0))


def wheel_samples(direction):
    """One physical gesture, not a menu step. Guest sensitivity still applies."""
    yield (event(3, 0, 100) + event(3, 1, 100) + event(3, 24, 1) +
           event(1, 330, 1) + event(0, 0, 0))
    # Same raw 1..200 axis and settling samples used by Q2's remote input.
    for i, distance in enumerate((10, 20, 30, 42, 42, 42, 42, 42)):
        yield (event(3, 0, (99 - direction * distance) % 200 + 1) +
               event(3, 1, 100 + i % 2) + event(0, 0, 0))
    yield event(3, 24, 0) + event(1, 330, 0) + event(0, 0, 0)


def framebuffer(path, state):
    """Only decode the displayed guest page; never draw labels or menus here."""
    from PIL import Image
    yoffset, blank = struct.unpack('<II', state.read_bytes())
    if yoffset > HEIGHT * (PAGES - 1):
        raise ValueError('Firmware requested an invalid framebuffer page')
    if blank:
        return Image.new('RGB', (HEIGHT, WIDTH))
    with path.open('rb') as source:
        source.seek(yoffset * STRIDE)
        data = source.read(HEIGHT * STRIDE)
    if len(data) != HEIGHT * STRIDE:
        raise ValueError('Truncated guest framebuffer')
    return Image.frombytes('RGB', (WIDTH, HEIGHT), data, 'raw', 'BGRX', STRIDE).transpose(
        Image.Transpose.ROTATE_90)


class Runtime:
    def __init__(self, firmware, sd_card, state_dir, trace=False):
        if sys.platform != 'linux':
            raise RuntimeError('Firmware execution currently requires Linux or Ubuntu WSL')
        import fcntl
        self.qemu, self.proot = tool('qemu-mipsel'), tool('proot')
        self.firmware = firmware.resolve(strict=True)
        self.directory = state_dir.expanduser().resolve() / image_hash(self.firmware)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock = (self.directory / 'runtime.lock').open('w')
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.lock.close()
            raise RuntimeError('This firmware already has a running session') from None
        self.root = self.directory / 'rootfs'
        self.sd_card = sd_card.expanduser().resolve()
        self.sd_card.mkdir(parents=True, exist_ok=True)
        self.trace = trace
        self.children, self.fds = [], {}
        self.logs = []

    def prepare(self):
        if not self.root.exists():
            # read_rootfs checks the model and copies only the SquashFS member;
            # tar/ZIP pathnames are never extracted onto the host filesystem.
            from simulator_firmware import read_rootfs
            squashfs = self.directory / 'rootfs.squashfs'
            read_rootfs(self.firmware, squashfs)
            staging = self.directory / 'rootfs.new'
            if staging.exists():
                shutil.rmtree(staging)
            subprocess.run([tool('unsquashfs'), '-no-progress', '-no-xattrs',
                            '-d', str(staging), str(squashfs)], check=True)
            validate_demo(staging / 'release/bin/demo')
            staging.rename(self.root)
            squashfs.unlink()
        validate_demo(self.root / 'release/bin/demo')
        for directory in ('tmp/q2-hardware', 'dev/input', 'proc', 'sys', 'run/dbus',
                          'var/lib/dbus', 'mnt/data', 'mnt/mmc'):
            target = self.root / directory
            if not target.resolve().is_relative_to(self.root):
                raise ValueError(f'Firmware directory escapes its root: {directory}')
            target.mkdir(parents=True, exist_ok=True)
        compile_devices(self.root / 'lib/q2-devices.so')
        (self.root / 'dev/fb0').write_bytes(bytes(FB_SIZE))
        (self.root / 'tmp/q2-hardware/display').write_bytes(bytes(8))
        for i in range(1, 5):
            path = self.root / f'dev/input/event{i}'
            if path.exists():
                path.unlink()
            os.mkfifo(path, 0o600)
            self.fds[i] = os.open(path, os.O_RDWR | os.O_NONBLOCK)
        for name in ('null', 'zero', 'random', 'urandom'):
            (self.root / 'dev' / name).touch(exist_ok=True)
        machine = self.root / 'var/lib/dbus/machine-id'
        if not machine.exists():
            machine.write_text(uuid.uuid4().hex + '\n')

    def command(self, *argv, devices=False):
        # Do not use -R: its default host bindings include /dev, /sys and $HOME.
        # Bind just the Linux interfaces needed by the guest services.
        command = [self.proot, '-r', str(self.root), '-0', '-w', '/release',
                   '-q', shlex.join([self.qemu, '-cpu', 'P5600']),
                   '-b', '/proc:/proc', '-b', f'{self.sd_card}:/mnt/mmc']
        for name in ('null', 'zero', 'random', 'urandom'):
            command += ['-b', f'/dev/{name}:/dev/{name}']
        environment = ['PATH=/usr/bin:/bin:/sbin:/usr/sbin:/release/bin',
                       'HOME=/root', 'LD_LIBRARY_PATH=/release/bin:/usr/lib:/lib',
                       'TSLIB_TSDEVICE=/dev/input/event2', 'TSLIB_CONFFILE=/etc/ts.conf',
                       'TSLIB_PLUGINDIR=/usr/lib/ts']
        if devices:
            environment.append('LD_PRELOAD=/lib/q2-devices.so')
        if self.trace:
            environment.append('QEMU_STRACE=1')
        return command + ['/bin/busybox', 'env', '-i', *environment, *argv]

    def spawn(self, name, *argv, devices=False):
        log = (self.directory / f'{name}.log').open('wb')
        self.logs.append(log)
        process = subprocess.Popen(self.command(*argv, devices=devices),
                                   stdout=log, stderr=subprocess.STDOUT,
                                   start_new_session=True,
                                   env={k: v for k, v in os.environ.items()
                                        if k not in ('LD_PRELOAD', 'LD_LIBRARY_PATH')})
        self.children.append(process)
        return process

    def start(self):
        self.prepare()
        print(f'Firmware runtime state and logs: {self.directory}', flush=True)
        socket = self.root / 'run/dbus/system_bus_socket'
        socket.unlink(missing_ok=True)
        bus = self.spawn('dbus', '/usr/bin/dbus-daemon', '--system', '--nofork', '--nopidfile')
        deadline = time.monotonic() + 10
        while not socket.exists():
            if bus.poll() is not None or time.monotonic() >= deadline:
                raise RuntimeError('Firmware D-Bus did not start. See dbus.log. '
                                   'PRoot needs ptrace and local Unix sockets; '
                                   'no preview fallback is used.')
            time.sleep(.05)
        self.demo = self.spawn('demo', '/release/bin/demo', devices=True)

    def check(self):
        for process in self.children:
            if process.poll() is not None:
                raise RuntimeError(f'Firmware process exited ({process.returncode}). '
                                   f'Inspect {self.directory}/demo.log and dbus.log')

    def key(self, code, down):
        os.write(self.fds[1], event(1, code, int(down)) + event(0, 0, 0))

    def touch(self, x, y, down):
        os.write(self.fds[2], touch_sample(x, y, down))

    def frame(self):
        return framebuffer(self.root / 'dev/fb0', self.root / 'tmp/q2-hardware/display')

    def close(self):
        for process in reversed(self.children):
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        for process in self.children:
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
        for fd in self.fds.values():
            os.close(fd)
        self.fds.clear()
        for log in self.logs:
            log.close()
        self.lock.close()


def window(runtime):
    import tkinter as tk
    from PIL import ImageTk
    root = tk.Tk()
    root.title('Q2 — firmware framebuffer (experimental)')
    screen = tk.Label(root, borderwidth=0)
    screen.pack()
    held = set()
    failures = []
    wheel_busy = False

    def key(e, down):
        code = KEYS.get(e.keysym)
        if code is not None and (down and code not in held or not down and code in held):
            held.add(code) if down else held.discard(code)
            runtime.key(code, down)

    root.bind('<KeyPress>', lambda e: key(e, True))
    root.bind('<KeyRelease>', lambda e: key(e, False))
    screen.bind('<ButtonPress-1>', lambda e: runtime.touch(e.x, e.y, True))
    screen.bind('<B1-Motion>', lambda e: runtime.touch(
        min(374, max(0, e.x)), min(319, max(0, e.y)), True))
    screen.bind('<ButtonRelease-1>', lambda e: runtime.touch(
        min(374, max(0, e.x)), min(319, max(0, e.y)), False))

    def wheel(direction):
        nonlocal wheel_busy
        if wheel_busy:
            return
        wheel_busy = True
        samples = iter(wheel_samples(direction))

        def send():
            nonlocal wheel_busy
            data = next(samples, None)
            if data is None:
                wheel_busy = False
                return
            os.write(runtime.fds[3], data)
            root.after(20, send)
        send()

    screen.bind('<Button-4>', lambda e: wheel(-1))
    screen.bind('<Button-5>', lambda e: wheel(1))
    screen.bind('<MouseWheel>', lambda e: wheel(-1 if e.delta > 0 else 1))

    def release(_):
        for code in tuple(held):
            runtime.key(code, False)
        held.clear()
    root.bind('<FocusOut>', release)

    def refresh():
        try:
            runtime.check()
            screen.image = ImageTk.PhotoImage(runtime.frame())
            screen.configure(image=screen.image)
        except Exception as exc:
            failures.append(exc)
            root.destroy()
            return
        root.after(33, refresh)

    refresh()
    root.mainloop()
    if failures:
        raise failures[0]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--firmware', required=True, type=Path)
    parser.add_argument('--sd-card', type=Path, default=Path.home() / 'q2-test-sd')
    parser.add_argument('--state-dir', type=Path,
                        default=Path.home() / '.cache/q2-emulation/firmware-runtime')
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--strace', action='store_true', help='log guest system calls')
    parser.add_argument('--snapshot', type=Path, help='capture the actual guest framebuffer')
    parser.add_argument('--seconds', type=float, default=10, help='wait before --snapshot')
    args = parser.parse_args(argv)
    if not 0 <= args.seconds <= 120:
        parser.error('--seconds must be between 0 and 120')
    runtime = None
    try:
        runtime = Runtime(args.firmware, args.sd_card, args.state_dir, args.strace)
        if args.prepare_only:
            runtime.prepare()
            print(f'Prepared firmware runtime: {runtime.directory}')
        else:
            runtime.start()
            if args.snapshot:
                deadline = time.monotonic() + args.seconds
                while time.monotonic() < deadline:
                    runtime.check()
                    time.sleep(.05)
                runtime.check()
                runtime.frame().save(args.snapshot)
                print(f'Saved guest framebuffer: {args.snapshot}')
            else:
                window(runtime)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        parser.exit(1, f'{parser.prog}: {exc}\n')
    finally:
        if runtime:
            runtime.close()


if __name__ == '__main__':
    main()
