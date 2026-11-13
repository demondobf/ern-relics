"""Fetch only the native source checkouts pinned in sources.lock.json."""

import argparse
import json
from pathlib import Path

from tools.build.output import safe_path
from tools.process import ROOT, cli, run


def git(directory, *arguments, check=True):
    return run(['git', '-C', directory, *arguments], capture_output=True, check=check)


def setup(root=ROOT):
    run(['git', '--version'], capture_output=True)
    root = Path(root)
    dependencies = json.loads((root / 'sources.lock.json').read_text(encoding='utf-8'))
    for dependency in dependencies:
        directory = safe_path(root / 'third_party' / dependency['Name'])
        if directory.parent != safe_path(root / 'third_party'):
            raise ValueError('Dependency checkout must stay inside third_party')
        if not (directory / '.git').exists():
            if directory.exists() and any(directory.iterdir()):
                raise ValueError(
                    f'Refusing to initialize a nonempty dependency directory: {directory}'
                )
            git(root, 'init', '--quiet', directory)
            git(directory, 'remote', 'add', 'origin', dependency['Url'])
        origin = git(directory, 'remote', 'get-url', 'origin').stdout.strip()
        if origin != dependency['Url']:
            raise ValueError(f'Unexpected dependency origin in {directory}')
        if git(directory, 'status', '--porcelain').stdout:
            raise ValueError(f'Dependency has local changes: {directory}')
        current = git(directory, 'rev-parse', '--verify', 'HEAD', check=False).stdout.strip()
        if current != dependency['Commit']:
            git(directory, 'fetch', '--quiet', '--depth', '1', 'origin', dependency['Commit'])
            git(directory, 'checkout', '--quiet', '--detach', dependency['Commit'])
        print(f'{dependency["Name"]}: {dependency["Commit"]}')


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    setup()


if __name__ == '__main__':
    cli(main)
