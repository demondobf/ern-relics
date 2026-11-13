"""Run the pinned analyzer against project translation units in a compilation database."""

import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from tools.process import ROOT, cli, run
from tools.setup.native import clang_tidy


def analyze(build_directory, jobs=None, root=ROOT):
    build = Path(build_directory).resolve(strict=True)
    commands = json.loads((build / 'compile_commands.json').read_text(encoding='utf-8'))
    files = sorted(
        {
            (Path(command['directory']) / command['file']).resolve()
            for command in commands
            if any(
                (Path(command['directory']) / command['file'])
                .resolve()
                .is_relative_to(root / group)
                for group in ('src', 'tests')
            )
        }
    )
    if not files:
        raise ValueError('The compilation database contains no project sources')
    tidy = clang_tidy(root)
    run([tidy, '--verify-config', '--config-file', root / '.clang-tidy'])

    def check(file):
        return run([tidy, '-p', build, '--quiet', file], capture_output=True, check=False)

    with ThreadPoolExecutor(max_workers=jobs or os.cpu_count()) as workers:
        results = list(workers.map(check, files))
    for result in results:
        if result.stdout or result.stderr:
            print(result.stdout + result.stderr)
    if any(result.returncode for result in results):
        raise RuntimeError('C++ static analysis failed')
    print(f'C++ static analysis passed: {len(files)} project sources, pinned clang-tidy')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-directory', type=Path, required=True)
    parser.add_argument('--jobs', type=int)
    args = parser.parse_args()
    if args.jobs is not None and args.jobs < 1:
        parser.error('--jobs must be positive')
    analyze(args.build_directory, args.jobs)


if __name__ == '__main__':
    cli(main)
