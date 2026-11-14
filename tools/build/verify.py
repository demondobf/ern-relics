"""Run the synthetic DX12 host in isolation against a build or exact staged package."""

import argparse
import os
import shutil
import sys
from pathlib import Path

from tools.build.output import temporary_directory
from tools.process import ROOT, cli, run


def verify(
    build_directory, package_directory=None, game_directory=None, regulation_path=None, *, root=ROOT
):
    build = Path(build_directory).resolve(strict=True)
    if not (build / 'ern-relics-host.exe').is_file():
        raise ValueError('Build the synthetic host before verification')
    if package_directory is not None and (
        game_directory is not None or regulation_path is not None
    ):
        raise ValueError('Package smoke tests use synthetic data only')
    runtime = (
        Path(package_directory).resolve(strict=True) if package_directory is not None else build
    )
    game = Path(game_directory).resolve(strict=True) if game_directory is not None else None
    regulation = Path(regulation_path).resolve(strict=True) if regulation_path is not None else None
    ini = runtime / 'ern-relics.ini'
    if package_directory is not None and not ini.is_file():
        raise ValueError('The package is missing ern-relics.ini')
    with temporary_directory() as directory:
        for source in (
            build / 'ern-relics-host.exe',
            runtime / 'ern-relics.dll',
            ini if ini.is_file() else root / 'config/ern-relics.ini',
        ):
            shutil.copy2(source, directory / source.name)
        for source in (
            build / 'ern-relics-host.pdb',
            runtime / 'ern-relics.pdb',
            *build.glob('clang_rt.asan*_dynamic-x86_64.dll'),
        ):
            if source.is_file():
                shutil.copy2(source, directory / source.name)
        environment = dict(os.environ)
        for key, value in {
            'ERN_RELICS_TEST_GAME_DIRECTORY': game,
            'ERN_RELICS_TEST_REGULATION': regulation,
        }.items():
            environment.pop(key, None)
            if value is not None:
                environment[key] = str(value)
        try:
            with (
                (directory / 'host-stdout.txt').open('wb') as stdout,
                (directory / 'host-stderr.txt').open('wb') as stderr,
            ):
                result = run(
                    [
                        directory / 'ern-relics-host.exe',
                        '--smoke-test' if package_directory is not None else '--self-test',
                    ],
                    cwd=directory,
                    env=environment,
                    stdout=stdout,
                    stderr=stderr,
                    timeout=30,
                    check=False,
                )
            report = directory / 'host-test.txt'
            if report.is_file():
                print(report.read_text(encoding='utf-8', errors='replace'))
            if result.returncode:
                raise RuntimeError(f'DX12 integration test failed: exit {result.returncode}')
            if not report.is_file():
                raise RuntimeError('The synthetic host did not produce its test report')
        except Exception:
            for filename in ('host-stderr.txt', 'ern-relics.log'):
                path = directory / filename
                if path.is_file():
                    print(
                        '\n'.join(
                            path.read_text(encoding='utf-8', errors='replace').splitlines()[-80:]
                        ),
                        file=sys.stderr,
                    )
            raise
    if game is not None:
        run(
            [
                sys.executable,
                '-m',
                'tools.assets.verify_regulation',
                '--game-dir',
                game,
                '--regulation',
                regulation or game / 'regulation.bin',
                '--probe',
                build / 'ern_relics_rules_probe.exe',
            ],
            cwd=root,
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-directory', type=Path, required=True)
    parser.add_argument('--package-directory', type=Path)
    parser.add_argument('--game-directory', type=Path)
    parser.add_argument('--regulation-path', type=Path)
    args = parser.parse_args()
    verify(args.build_directory, args.package_directory, args.game_directory, args.regulation_path)


if __name__ == '__main__':
    cli(main)
