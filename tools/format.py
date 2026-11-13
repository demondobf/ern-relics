"""Run the pinned Python and C++ formatters without selecting a separate tool version."""

import argparse

from tools.process import ROOT, cli, python_tool, run


def format_sources(fix=False, root=ROOT):
    if fix:
        run([python_tool('ruff'), 'check', '--select', 'I', '--fix', root], cwd=root)
    run([python_tool('ruff'), 'format', *([] if fix else ['--check']), root], cwd=root)
    files = sorted(
        path
        for directory in ('src', 'tests')
        for path in (root / directory).rglob('*')
        if path.suffix in ('.cpp', '.hpp')
    )
    run(
        [
            python_tool('clang-format'),
            '--style=file',
            *(['-i'] if fix else ['--dry-run', '--Werror']),
            *files,
        ],
        cwd=root,
    )
    print(f'C++ formatting passed: {len(files)} files, locked clang-format')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fix', action='store_true')
    format_sources(parser.parse_args().fix)


if __name__ == '__main__':
    cli(main)
