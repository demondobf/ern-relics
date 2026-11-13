"""Launch an explicit package with an offline ME3 profile and a separate test save."""

import argparse
import csv
import io
import json
import os
import shutil
import stat
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from tools.build.output import safe_path, temporary_directory
from tools.process import ROOT, cli, hidden_process, run


def game_running():
    names = {
        row[0].lower()
        for row in csv.reader(
            io.StringIO(run(['tasklist.exe', '/FO', 'CSV', '/NH'], capture_output=True).stdout)
        )
        if row
    }
    return bool(names & {'nightreign.exe', 'easyanticheat_eos.exe', 'easyanticheat.exe'})


def launch(
    package_directory, me3_exe, game_exe, check=False, output_directory=ROOT / 'output/game-test'
):
    package = Path(package_directory).resolve(strict=True)
    me3, game = Path(me3_exe).resolve(strict=True), Path(game_exe).resolve(strict=True)
    for path in (me3, game, package / 'ern-relics.dll', package / 'ern-relics.ini'):
        if not path.is_file():
            raise ValueError(f'Required file not found: {path}')
    if game_running():
        raise RuntimeError(
            'Nightreign or EAC is already running. Close it before starting the test profile.'
        )
    # Check reparse points before resolving Windows 8.3 aliases for containment.
    output = safe_path(output_directory).resolve()
    if output == package or output.is_relative_to(package):
        raise ValueError('Keep the test profile and logs outside replaceable package output')
    output.mkdir(parents=True, exist_ok=True)
    installation = safe_path(output / 'installation')
    installation.mkdir(exist_ok=True)
    native_dll = safe_path(installation / 'ern-relics.dll')
    ini = safe_path(installation / 'ern-relics.ini')
    with temporary_directory(installation, '.stage-') as stage:
        shutil.copy2(package / 'ern-relics.dll', stage / 'ern-relics.dll')
        if native_dll.exists():
            native_dll.chmod(native_dll.stat().st_mode | stat.S_IWRITE)
        (stage / 'ern-relics.dll').replace(native_dll)
    if not ini.exists():
        shutil.copy2(package / 'ern-relics.ini', ini)
    profile = output / 'nightreign-relics-test.me3'
    native = json.dumps(native_dll.as_posix(), ensure_ascii=False)
    profile.write_text(
        f'profileVersion = "v1"\nsavefile = "ern-relics-test.sl2"\nstart_online = false\n\n[[supports]]\ngame = "nightreign"\n\n[[natives]]\npath = {native}\nload_early = true\n',
        encoding='utf-8',
    )
    if check:
        print(f'Test installation and profile prepared: {profile}. No game was launched.')
        return profile
    stamp = datetime.now(UTC).strftime('%Y%m%d-%H%M%S-%f')
    with (
        (output / f'launch-{stamp}.log').open('wb') as stdout,
        (output / f'launch-{stamp}.err.log').open('wb') as stderr,
    ):
        process = subprocess.Popen(
            [str(me3), 'launch', '--profile', str(profile), '--exe', str(game)],
            cwd=installation,
            stdout=stdout,
            stderr=stderr,
            **hidden_process(),
        )
    print(f'Started offline test profile with ern-relics-test.sl2. ME3 process: {process.pid}')
    return profile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package-directory', type=Path, required=True)
    parser.add_argument(
        '--me3-exe',
        type=Path,
        default=Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs/garyttierney/me3/bin/me3.exe',
    )
    parser.add_argument(
        '--game-exe',
        type=Path,
        default=Path(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)'))
        / 'Steam/steamapps/common/ELDEN RING NIGHTREIGN/Game/nightreign.exe',
    )
    parser.add_argument('--output-directory', type=Path, default=ROOT / 'output/game-test')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    launch(args.package_directory, args.me3_exe, args.game_exe, args.check, args.output_directory)


if __name__ == '__main__':
    cli(main)
