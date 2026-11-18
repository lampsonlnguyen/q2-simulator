"""Checks for the actual-firmware boundary, without needing a proprietary image."""
import ctypes as C
import errno
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import firmware_runtime as fw


class FirmwareBoundary(unittest.TestCase):
    def test_firmware_launch_does_not_enter_the_python_preview(self):
        import simulator
        with patch.object(sys, 'argv', ['simulator.py', '--firmware', 'custom/update.tar',
                                       '--sd-card', 'test-card']), \
                patch.object(fw, 'main') as execute, \
                patch.object(simulator, 'load_firmware', side_effect=AssertionError('preview used')):
            simulator.main()
        execute.assert_called_once_with(['--firmware', 'custom/update.tar', '--sd-card', 'test-card'])

    def test_framebuffer_page_stride_rotation_and_blanking(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = bytearray(fw.FB_SIZE)
            # The top right physical pixel rotates to the top left upright pixel.
            offset = 375 * fw.STRIDE + (fw.WIDTH - 1) * 4
            data[offset:offset + 4] = bytes((3, 2, 1, 0))
            (root / 'fb').write_bytes(data)
            (root / 'state').write_bytes(struct.pack('<II', 375, 0))
            image = fw.framebuffer(root / 'fb', root / 'state')
            self.assertEqual(image.size, (375, 320))
            self.assertEqual(image.getpixel((0, 0)), (1, 2, 3))
            (root / 'state').write_bytes(struct.pack('<II', 375, 4))
            self.assertIsNone(fw.framebuffer(root / 'fb', root / 'state').getbbox())
            (root / 'state').write_bytes(struct.pack('<II', 751, 0))
            with self.assertRaises(ValueError):
                fw.framebuffer(root / 'fb', root / 'state')

    def test_raw_touch_matches_the_panel_axes_and_o32_event_abi(self):
        records = list(struct.iter_unpack('<IIHHi', fw.touch_sample(374, 319, True)))
        self.assertEqual([r[2:] for r in records],
                         [(3, 0, 0), (3, 1, 374), (3, 24, 1), (1, 330, 1), (0, 0, 0)])
        with self.assertRaises(ValueError):
            fw.touch_sample(375, 0, True)

    def test_guest_command_uses_the_firmware_root_and_only_explicit_bindings(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(fw, 'tool', side_effect=lambda n: '/tools/' + n):
            directory = Path(directory)
            image = directory / 'image.tar'
            image.write_bytes(b'test image')
            runtime = fw.Runtime(image, directory / 'SD with spaces', directory / 'state')
            try:
                command = runtime.command('/release/bin/demo', devices=True)
                self.assertEqual(command[:3], ['/tools/proot', '-r', str(runtime.root)])
                self.assertIn('/tools/qemu-mipsel -cpu P5600', command)
                self.assertIn(f'{runtime.sd_card}:/mnt/mmc', command)
                self.assertNotIn('/dev:/dev', command)
                self.assertNotIn('/sys:/sys', command)
                self.assertIn('LD_PRELOAD=/lib/q2-devices.so', command)
                self.assertEqual(command[-1], '/release/bin/demo')
            finally:
                runtime.close()

    def test_reject_foreign_or_wrong_nan_mode_executables(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'demo'
            header = bytearray(52)
            header[:7] = b'\x7fELF\x01\x01\x01'
            struct.pack_into('<H', header, 18, 8)
            path.write_bytes(header)
            with self.assertRaises(ValueError):
                fw.validate_demo(path)
            struct.pack_into('<I', header, 36, 0x400)
            path.write_bytes(header)
            fw.validate_demo(path)
            header[5] = 2
            path.write_bytes(header)
            with self.assertRaises(ValueError):
                fw.validate_demo(path)

    @unittest.skipUnless(sys.platform == 'linux' and shutil.which('cc'), 'Linux C compiler required')
    def test_device_ioctls_pan_bounds_blank_state_and_evdev(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            display = root / 'display'
            display.write_bytes(bytes(8))
            target = root / 'devices.so'
            subprocess.run(['cc', '-shared', '-fPIC', '-O2', '-Wall', '-Wextra', '-Werror',
                            f'-DQ2_DISPLAY_PATH="{display}"', str(fw.HERE / 'firmware_devices.c'),
                            '-o', str(target), '-ldl'], check=True)
            bridge = C.CDLL(str(target), use_errno=True)
            ioctl = bridge.ioctl
            ioctl.argtypes = [C.c_int, C.c_ulong, C.c_void_p]
            ioctl.restype = C.c_int
            (root / 'dev/input').mkdir(parents=True)
            (root / 'dev/fb0').write_bytes(bytes(fw.FB_SIZE))
            fd = os.open(root / 'dev/fb0', os.O_RDWR)
            try:
                mode = C.create_string_buffer(160)
                self.assertEqual(ioctl(fd, 0x4600, mode), 0)
                self.assertEqual(struct.unpack_from('<4I', mode.raw), (320, 375, 320, 1125))
                struct.pack_into('<I', mode, 20, 375)
                self.assertEqual(ioctl(fd, 0x4606, mode), 0)
                self.assertEqual(struct.unpack('<II', display.read_bytes()), (375, 0))
                self.assertEqual(ioctl(fd, 0x4611, 4), 0)
                self.assertEqual(ioctl(fd, 0x4606, mode), 0)
                self.assertEqual(struct.unpack('<II', display.read_bytes()), (375, 4))
                struct.pack_into('<I', mode, 20, 751)
                self.assertEqual(ioctl(fd, 0x4606, mode), -1)
                self.assertEqual(C.get_errno(), errno.EINVAL)
                self.assertEqual(ioctl(fd, 0x46ff, None), -1)
                self.assertEqual(C.get_errno(), errno.ENOTTY)
            finally:
                os.close(fd)
            (root / 'dev/input/event2').touch()
            fd = os.open(root / 'dev/input/event2', os.O_RDONLY)
            try:
                version = C.c_uint32()
                self.assertEqual(ioctl(fd, 0x40044501, C.byref(version)), 0)
                self.assertEqual(version.value, 0x10001)
                bits = C.create_string_buffer(64)
                self.assertEqual(ioctl(fd, 0x40404523, bits), 64)
                self.assertEqual(struct.unpack_from('<I', bits.raw)[0], (1 << 24) | 3)
            finally:
                os.close(fd)


if __name__ == '__main__':
    unittest.main()
