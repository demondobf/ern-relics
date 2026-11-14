"""Build and test through CMake/CTest, then validate a runnable development package."""

import argparse
import re
import sys
from pathlib import Path

from tools.build.output import safe_path, write_build_output
from tools.build.verify import verify
from tools.checks.analyze import analyze
from tools.process import ROOT, cli, run
from tools.setup.native import require_native_shell


def build(
    preset='release',
    build_directory=None,
    jobs=0,
    root=ROOT,
    *,
    analysis=False,
    package_directory=None,
):
    if preset not in ('release', 'debug', 'asan') or jobs < 0 or jobs > 1024:
        raise ValueError('Invalid native preset or job count')
    require_native_shell()
    directory = safe_path(
        build_directory if build_directory is not None else root / '.build' / preset
    )
    run(
        [
            'cmake',
            '--preset',
            preset,
            '-B',
            directory,
            f'-DPython3_EXECUTABLE={sys.executable}',
        ],
        cwd=root,
    )
    run(['cmake', '--build', directory, *(['--parallel', str(jobs)] if jobs else [])], cwd=root)
    run(['ctest', '--test-dir', directory, '--output-on-failure', '--no-tests=error'], cwd=root)
    if analysis:
        analyze(directory, jobs or None, root)
    if preset == 'asan':
        print('Built and tested with AddressSanitizer')
        return None
    cache = (directory / 'CMakeCache.txt').read_text(encoding='utf-8')
    version = re.search(r'^CMAKE_PROJECT_VERSION:STATIC=(.+)$', cache, re.M)
    if not version:
        raise ValueError('Cannot read the configured project version')
    name = f'ern-relics-{version[1]}' + (f'-{preset}' if preset != 'release' else '') + '-dev'
    package = write_build_output(
        root,
        directory / 'runtime',
        name,
        lambda staged: verify(directory, staged, root=root),
        destination=package_directory,
    )
    print(f'Built and tested: {package}')
    return package


def arguments(parser):
    parser.add_argument('--preset', choices=('release', 'debug', 'asan'), default='release')
    parser.add_argument('--build-directory', type=Path)
    parser.add_argument(
        '--package-directory',
        type=Path,
        help='Write a new candidate instead of replacing development output',
    )
    parser.add_argument('--jobs', type=int, default=0)
    return parser


def main():
    args = arguments(argparse.ArgumentParser(description=__doc__)).parse_args()
    build(
        args.preset,
        args.build_directory,
        args.jobs,
        package_directory=args.package_directory,
    )


if __name__ == '__main__':
    cli(main)
