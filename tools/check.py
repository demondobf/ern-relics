"""Combine lint, formatting, native verification, packaging, and static analysis."""

import argparse
from contextlib import nullcontext

from tools.build.output import safe_path, temporary_directory
from tools.build.package import arguments, build
from tools.checks.analyze import analyze
from tools.format import format_sources
from tools.process import ROOT, cli, python_tool, run


def check(preset='release', label='dev', build_directory=None, jobs=0, root=ROOT):
    run([python_tool('ruff'), 'check', '--no-cache', root], cwd=root)
    format_sources(root=root)
    context = (
        temporary_directory()
        if build_directory is None
        else nullcontext(safe_path(build_directory))
    )
    with context as directory:
        package = build(preset, label, directory, jobs, root)
        analyze(directory, jobs or None, root)
    print(
        'All checks passed: lint, formatting, compiler warnings, CTest, packaged DLL and static analysis'
    )
    return package


def main():
    args = arguments(argparse.ArgumentParser(description=__doc__)).parse_args()
    check(args.preset, args.label, args.build_directory, args.jobs)


if __name__ == '__main__':
    cli(main)
