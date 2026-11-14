"""Run the full check and create a new immutable release package."""

import argparse
from contextlib import nullcontext
from pathlib import Path

from tools.build.output import temporary_directory
from tools.check import check
from tools.process import ROOT, cli
from tools.release.package import package_release


def build_release(output_directory=ROOT / 'dist', build_directory=None, jobs=0, *, root=ROOT):
    version = (root / 'version.txt').read_text(encoding='utf-8').strip()
    context = (
        temporary_directory(root / '.build', 'release-')
        if build_directory is None
        else nullcontext(build_directory)
    )
    with context as native, temporary_directory(root / 'dist', '.release-') as staging:
        package = check(
            build_directory=native,
            jobs=jobs,
            root=root,
            package_directory=staging / 'package',
        )
        return package_release(package, version, output_directory)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-directory', type=Path, default=ROOT / 'dist')
    parser.add_argument('--build-directory', type=Path)
    parser.add_argument('--jobs', type=int, default=0)
    args = parser.parse_args()
    release = build_release(args.output_directory, args.build_directory, args.jobs)
    print(f'Ready for Nexus Mods upload or ME3 import: {release.archive}')


if __name__ == '__main__':
    cli(main)
