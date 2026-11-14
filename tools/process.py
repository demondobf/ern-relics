"""Shared process policy for development commands; never invoke a command shell."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def python_tool(name):
    executable = Path(sys.executable).parent / (name + ('.exe' if os.name == 'nt' else ''))
    if not executable.is_file():
        raise RuntimeError(f'Run uv sync --locked to install {name} in the project environment')
    return executable


def hidden_process():
    if os.name != 'nt':
        return {}
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = subprocess.SW_HIDE
    return {'creationflags': subprocess.CREATE_NO_WINDOW, 'startupinfo': startup}


def run(arguments, *, cwd=ROOT, **options):
    # Hidden console children need explicit output handles on Windows.
    if not options.get('capture_output'):
        options.setdefault('stdout', sys.stdout)
        options.setdefault('stderr', sys.stderr)
    return subprocess.run(
        [str(argument) for argument in arguments],
        cwd=cwd,
        check=options.pop('check', True),
        encoding='utf-8',
        errors='replace',
        **hidden_process(),
        **options,
    )


def print_output(stdout, stderr):
    for text, stream in ((stdout, sys.stdout), (stderr, sys.stderr)):
        if text:
            print(text, file=stream, end='', flush=True)


def cli(main):
    # Redirected Windows streams may use a code page that cannot encode a path.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(errors='backslashreplace')
    try:
        main()
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        print(error, file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError):
            print_output(error.stdout, error.stderr)
        raise SystemExit(1) from None
