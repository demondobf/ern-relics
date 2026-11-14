"""Reject game assets and extracted data in source trees, archives, and Git history."""

import argparse
import re
from pathlib import Path

from tools.process import ROOT, cli, run


def forbidden(path):
    path = path.lower()
    if re.fullmatch(r'docs/screenshots/[^/]+\.webp', path):
        return False
    source = re.fullmatch(r'(src|tests)/.+\.(cpp|hpp|hpp\.in)', path)
    return bool(
        (not source and re.search(r'(^|/)(data|output)/', path))
        or re.search(
            r'\.(png|jpe?g|gif|webp|dds|tpf|bnd|dcx|param|bhd|bdt|bin|tsv|sl2|co2|rgba)$',
            path,
            re.I,
        )
        or re.search(r'(^|/)oo2core[^/]*\.dll$', path, re.I)
    )


def git_paths(root, *arguments):
    result = run(['git', '--no-replace-objects', '-C', root, *arguments], capture_output=True)
    return result.stdout.rstrip('\0').split('\0') if result.stdout else []


def check(root=ROOT, all_files=False, history=False):
    root = Path(root).resolve(strict=True)
    if all_files or not (root / '.git').exists():
        paths = [path.relative_to(root).as_posix() for path in root.rglob('*') if path.is_file()]
        if not all_files:
            paths = [
                path
                for path in paths
                if not re.search(
                    r'^(dist|third_party|output|\.venv|\.build|\.tools)/|(^|/)\.git/', path
                )
            ]
    else:
        paths = git_paths(root, 'ls-files', '-z', '--cached', '--others', '--exclude-standard')
    rejected = [path for path in paths if (root / path).is_file() and forbidden(path)]
    if rejected:
        raise ValueError(
            'Generated or game assets are not allowed in the source tree:\n' + '\n'.join(rejected)
        )
    print(f'Source asset check passed: {root}')
    if history:
        if not (root / '.git').exists():
            raise ValueError('The history audit requires a full Git checkout')
        if (
            run(
                ['git', '-C', root, 'rev-parse', '--is-shallow-repository'], capture_output=True
            ).stdout.strip()
            != 'false'
        ):
            raise ValueError('The history audit requires complete Git history')
        commits = run(
            ['git', '--no-replace-objects', '-C', root, 'rev-list', '--all', '--reflog'],
            capture_output=True,
        ).stdout.splitlines()
        refs = run(
            ['git', '-C', root, 'for-each-ref', '--format=%(objectname)'], capture_output=True
        ).stdout.splitlines()
        retained = {
            path
            for commit in set(commits + refs)
            for path in git_paths(root, 'ls-tree', '-r', '-z', '--name-only', '--full-tree', commit)
            if forbidden(path)
        }
        if retained:
            raise ValueError(
                'Generated or game assets are not allowed in Git history:\n'
                + '\n'.join(sorted(retained))
            )
        print(f'Git history asset check passed: {len(commits)} commits and {len(refs)} refs')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--all-files', action='store_true')
    parser.add_argument('--history', action='store_true')
    args = parser.parse_args()
    check(args.root, args.all_files, args.history)


if __name__ == '__main__':
    cli(main)
