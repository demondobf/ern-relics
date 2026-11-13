"""The actual synthetic host must reject premature close and fixture DLL packaging."""

import argparse
import ctypes
import shutil
import subprocess
import time
from ctypes import wintypes
from pathlib import Path
from unittest.mock import patch

from tools.build.output import temporary_directory
from tools.build.verify import verify
from tools.process import ROOT, hidden_process


def close_host(process_id):
    user = ctypes.WinDLL('user32', use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user.EnumWindows.argtypes = (callback_type, wintypes.LPARAM)
    user.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
    user.GetClassNameW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    user.PostMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
    sent = False

    @callback_type
    def visit(window, parameter):
        nonlocal sent
        owner = wintypes.DWORD()
        user.GetWindowThreadProcessId(window, ctypes.byref(owner))
        name = ctypes.create_unicode_buffer(256)
        user.GetClassNameW(window, name, len(name))
        if owner.value == process_id and name.value == 'ERNRelicsHost':
            sent = bool(user.PostMessageW(window, 0x0010, 0, 0))
            return False
        return True

    user.EnumWindows(visit, 0)
    return sent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-directory', type=Path, required=True)
    build = parser.parse_args().build_directory.resolve(strict=True)
    captured = {}
    close_early = True

    def execute(arguments, **options):
        with subprocess.Popen(
            [str(item) for item in arguments],
            cwd=options['cwd'],
            env=options['env'],
            stdout=options['stdout'],
            stderr=options['stderr'],
            **hidden_process(),
        ) as process:
            try:
                if close_early:
                    deadline = time.monotonic() + 15
                    while process.poll() is None and time.monotonic() < deadline:
                        if close_host(process.pid):
                            break
                        time.sleep(0.001)
                    else:
                        raise AssertionError(
                            'Did not locate the synthetic host window before it exited'
                        )
                process.wait(timeout=10)
                captured['report'] = (Path(options['cwd']) / 'host-test.txt').read_text().strip()
                captured['exit'] = process.returncode
                return subprocess.CompletedProcess(arguments, process.returncode)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()

    with patch('tools.build.verify.run', side_effect=execute):
        try:
            verify(build)
        except RuntimeError as error:
            if str(error) != 'DX12 integration test failed: exit 1':
                raise
        else:
            raise AssertionError('Premature host close passed verification')
        assert captured == {
            'exit': 1,
            'report': 'FAIL: Self-test closed before completing integration checks',
        }
        with temporary_directory() as package:
            shutil.copy2(build / 'ern-relics.dll', package / 'ern-relics.dll')
            shutil.copy2(ROOT / 'config/ern-relics.ini', package / 'ern-relics.ini')
            close_early = False
            try:
                verify(build, package)
            except RuntimeError as error:
                if str(error) != 'DX12 integration test failed: exit 1':
                    raise
            else:
                raise AssertionError('Smoke verification accepted an integration fixture DLL')
            assert captured == {
                'exit': 1,
                'report': 'FAIL: Packaged DLL contains integration fixture exports',
            }
    print('PASS: actual DX12 host rejects early close and fixture exports in package smoke tests')


if __name__ == '__main__':
    main()
