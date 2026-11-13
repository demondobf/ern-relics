"""Exercise pinned dependency setup using real, offline Git repositories."""

import json
import os
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from tools.process import run
from tools.setup.sources import setup


class SourceSetupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(prefix='ern-source-tests-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        config = self.root / 'empty.gitconfig'
        config.write_text('')
        self.environment = patch.dict(
            os.environ, {'GIT_CONFIG_GLOBAL': str(config), 'GIT_CONFIG_NOSYSTEM': '1'}
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.origin = self.root / 'local origin'
        self.origin.mkdir()
        self.git(self.origin, 'init', '--quiet', '--template=')
        (self.origin / 'fixture.txt').write_text('pinned')
        self.git(self.origin, 'add', '.')
        self.git(self.origin, 'commit', '--quiet', '-m', 'test: pinned fixture')
        self.revision = self.git(self.origin, 'rev-parse', 'HEAD')
        (self.origin / 'fixture.txt').write_text('newer')
        self.git(self.origin, 'commit', '--quiet', '-am', 'test: newer fixture')
        self.newer = self.git(self.origin, 'rev-parse', 'HEAD')
        (self.root / 'sources.lock.json').write_text(
            json.dumps(
                [
                    {'Name': 'first', 'Url': str(self.origin), 'Commit': self.revision},
                    {'Name': 'second', 'Url': str(self.origin), 'Commit': self.revision},
                ]
            )
        )

    def git(self, directory, *arguments):
        return run(
            [
                'git',
                '-C',
                directory,
                '-c',
                'user.name=Fixture',
                '-c',
                'user.email=fixture@example.invalid',
                '-c',
                'commit.gpgsign=false',
                *arguments,
            ],
            capture_output=True,
        ).stdout.strip()

    def test_fetch_reuse_and_dirty_checkout_preservation(self):
        setup(self.root)
        setup(self.root)
        first = self.root / 'third_party/first'
        self.assertEqual(self.git(first, 'rev-parse', 'HEAD'), self.revision)
        self.assertEqual(self.git(first, 'rev-parse', '--abbrev-ref', 'HEAD'), 'HEAD')
        self.assertFalse((self.root / '.venv').exists())
        self.assertFalse((self.root / '.tools').exists())
        self.git(first, 'fetch', '--quiet', 'origin', self.newer)
        self.git(first, 'checkout', '--quiet', '--detach', self.newer)
        (first / 'local.txt').write_text('preserve')
        with self.assertRaisesRegex(ValueError, 'local changes'):
            setup(self.root)
        self.assertEqual(self.git(first, 'rev-parse', 'HEAD'), self.newer)
        self.assertEqual((first / 'local.txt').read_text(), 'preserve')

    def test_git_failures_and_origin_mismatch_are_not_hidden(self):
        setup(self.root)
        first = self.root / 'third_party/first'
        index = first / '.git/index'
        original = index.read_bytes()
        index.write_bytes(b'bad index')
        with self.assertRaises(subprocess.CalledProcessError):
            setup(self.root)
        index.write_bytes(original)
        self.git(first, 'remote', 'remove', 'origin')
        with self.assertRaises(subprocess.CalledProcessError):
            setup(self.root)
        self.git(first, 'remote', 'add', 'origin', 'https://invalid.example/repository.git')
        with self.assertRaisesRegex(ValueError, 'origin'):
            setup(self.root)

    def test_nonempty_unversioned_directory_is_not_initialized(self):
        first = self.root / 'third_party/first'
        first.mkdir(parents=True)
        (first / 'keep.txt').write_text('keep')
        with self.assertRaisesRegex(ValueError, 'nonempty'):
            setup(self.root)
        self.assertFalse((first / '.git').exists())


if __name__ == '__main__':
    unittest.main()
