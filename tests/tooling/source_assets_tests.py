"""Exercise archive and complete Git-history asset boundaries with local fixtures."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tools.checks.source_assets import check, forbidden
from tools.process import run


class SourceAssetTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(prefix='ern-asset-tests-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def git(self, *arguments):
        return run(
            [
                'git',
                '-C',
                self.root,
                '-c',
                'user.name=Fixture',
                '-c',
                'user.email=fixture@example.invalid',
                '-c',
                'commit.gpgsign=false',
                '-c',
                'core.autocrlf=false',
                '-c',
                'core.hooksPath=',
                *arguments,
            ],
            capture_output=True,
        ).stdout.strip()

    def write(self, name):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'synthetic fixture')
        return path

    def test_screenshots_source_groups_and_generated_output(self):
        for name in (
            'docs/screenshots/editor.webp',
            'src/data/decoder.cpp',
            'tests/data/types.hpp',
            'src/data/game_keys.hpp.in',
        ):
            self.assertFalse(forbidden(name), name)
            self.write(name)
        for name in (
            'icons.png',
            'docs/editor.webp',
            'docs/screenshots/data/editor.webp',
            'docs/screenshots/editor.dds',
            'src/data/catalogue.json',
            'oo2core_9_win64.dll',
        ):
            path = self.write(name)
            with self.assertRaisesRegex(ValueError, 'assets are not allowed'):
                check(self.root, all_files=True)
            path.unlink()
        for name in (
            'third_party/bcdec/test_images/dice.dds',
            '.build/compiler.bin',
            '.tools/local.bin',
            'dist/local.bin',
            'output/local.bin',
            '.venv/local.bin',
        ):
            self.write(name)
        check(self.root)
        with self.assertRaisesRegex(ValueError, 'assets are not allowed'):
            check(self.root, all_files=True)

    def test_git_worktrees_retained_branches_reflogs_and_tree_refs(self):
        self.git('init', '--quiet', '--initial-branch=clean', '--template=')
        (self.root / '.gitignore').write_text('/third_party/\n')
        self.write('third_party/fixture.dds')
        self.write('docs/screenshots/editor.webp')
        self.git('add', '.gitignore', 'docs/screenshots/editor.webp')
        self.git('commit', '--quiet', '-m', 'test: source-only fixture')
        check(self.root, history=True)
        worktree = self.root / 'linked checkout'
        self.git('worktree', 'add', '--quiet', '--detach', str(worktree))
        self.assertTrue((worktree / '.git').is_file())
        check(worktree)
        self.git('switch', '--quiet', '-c', 'asset-fixture')
        self.write('icons.png')
        self.git('add', 'icons.png')
        self.git('commit', '--quiet', '-m', 'test: synthetic forbidden asset')
        tree = self.git('rev-parse', 'HEAD^{tree}')
        self.git('switch', '--quiet', 'clean')
        check(self.root)
        with self.assertRaisesRegex(ValueError, 'Git history'):
            check(self.root, history=True)
        self.git('branch', '--delete', '--force', 'asset-fixture')
        with self.assertRaisesRegex(ValueError, 'Git history'):
            check(self.root, history=True)
        self.git('update-ref', 'refs/snapshots/asset-fixture', tree)
        self.git('reflog', 'expire', '--expire=now', '--all')
        with self.assertRaisesRegex(ValueError, 'Git history'):
            check(self.root, history=True)
        self.git('update-ref', '-d', 'refs/snapshots/asset-fixture')
        check(self.root, history=True)


if __name__ == '__main__':
    unittest.main()
