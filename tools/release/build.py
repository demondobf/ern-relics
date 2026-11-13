"""Run the full check and create a new immutable release package."""

import argparse
from pathlib import Path

from tools.check import check
from tools.process import ROOT, cli
from tools.release.package import package_release


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-directory', type=Path, default=ROOT / 'dist')
    parser.add_argument('--build-directory', type=Path)
    parser.add_argument('--jobs', type=int, default=0)
    args = parser.parse_args()
    version = (ROOT / 'version.txt').read_text(encoding='utf-8').strip()
    package = check(build_directory=args.build_directory, jobs=args.jobs)
    release = package_release(package, version, args.output_directory)
    print(f'Ready for Nexus Mods upload or ME3 import: {release.archive}')


if __name__ == '__main__':
    cli(main)
