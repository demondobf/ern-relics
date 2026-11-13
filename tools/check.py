"""Combine lint, formatting, native verification, packaging, and static analysis."""

import argparse

from tools.build.package import arguments, build
from tools.format import format_sources
from tools.process import ROOT, cli, python_tool, run


def check(
    preset='release',
    build_directory=None,
    jobs=0,
    root=ROOT,
    *,
    package_directory=None,
):
    run([python_tool('ruff'), 'check', '--no-cache', root], cwd=root)
    format_sources(root=root)
    package = build(
        preset,
        build_directory,
        jobs,
        root,
        analysis=True,
        package_directory=package_directory,
    )
    checks = 'lint, formatting, compiler warnings, CTest and static analysis'
    if package is not None:
        checks += ', packaged DLL'
    print(f'All checks passed: {checks}')
    return package


def main():
    args = arguments(argparse.ArgumentParser(description=__doc__)).parse_args()
    check(
        args.preset,
        args.build_directory,
        args.jobs,
        package_directory=args.package_directory,
    )


if __name__ == '__main__':
    cli(main)
