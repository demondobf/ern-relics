"""Shared diagnostics inspect real Git state and LLVM caches without mutation."""

import hashlib
import json
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from tools.process import run
from tools.setup import diagnose, native, sources


def snapshot(root):
    return {
        path.relative_to(root): (
            path.stat().st_mtime_ns,
            hashlib.sha256(path.read_bytes()).hexdigest(),
        )
        for path in root.rglob('*')
        if path.is_file()
    }


class DoctorValidationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(prefix='ern-doctor-validation-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        (self.root / 'pyproject.toml').write_text(
            '[dependency-groups]\ndev = ["clang-format==22.1.3"]\n'
        )
        (self.root / 'sources.lock.json').write_text('[]')

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

    def test_git_diagnosis_is_local_strict_and_preserves_index_and_files(self):
        directory = self.root / 'third_party/fixture'
        directory.mkdir(parents=True)
        self.git(directory, 'init', '--quiet', '--template=')
        self.git(directory, 'remote', 'add', 'origin', 'https://invalid.example/never-fetch.git')
        (directory / 'tracked.txt').write_text('fixture')
        self.git(directory, 'add', '.')
        self.git(directory, 'commit', '--quiet', '-m', 'test: fixture')
        dependency = {
            'Name': 'fixture',
            'Url': 'https://invalid.example/never-fetch.git',
            'Commit': self.git(directory, 'rev-parse', 'HEAD'),
        }
        lock = self.root / 'sources.lock.json'
        lock.write_text(json.dumps([dependency]))
        with (
            patch.object(diagnose, 'seven_zip', return_value='fixture 7-Zip'),
            patch.object(diagnose, 'clang_tidy', return_value='fixture LLVM'),
        ):
            for state in ('clean', 'wrong-pin', 'dirty'):
                with self.subTest(state=state):
                    if state == 'wrong-pin':
                        lock.write_text(json.dumps([{**dependency, 'Commit': '0' * 40}]))
                    if state == 'dirty':
                        lock.write_text(json.dumps([dependency]))
                        (directory / 'tracked.txt').write_text('local changes')
                    before = snapshot(self.root)
                    with patch.object(sources, 'git', wraps=sources.git) as command:
                        results = diagnose.diagnose(self.root)
                    self.assertEqual(results[-1]['ok'], state == 'clean')
                    self.assertEqual(snapshot(self.root), before)
                    for call in command.call_args_list:
                        self.assertIn(call.args[1], ('remote', 'status', 'rev-parse'))

    def test_missing_checkouts_and_incomplete_llvm_are_reported_without_execution(self):
        (self.root / 'sources.lock.json').write_text(
            json.dumps(
                [
                    {
                        'Name': 'missing',
                        'Url': 'https://invalid.example/never-fetch.git',
                        'Commit': '0' * 40,
                    }
                ]
            )
        )
        cache = native.llvm_directory(self.root)
        (cache / 'bin').mkdir(parents=True)
        (cache / 'bin/clang-tidy.exe').write_text('must not execute')
        before = snapshot(self.root)
        with (
            patch.object(diagnose, 'seven_zip', side_effect=RuntimeError('missing 7-Zip')),
            patch.object(native, 'run') as execute,
        ):
            results = diagnose.diagnose(self.root)
        self.assertTrue(all(not result['ok'] for result in results))
        self.assertIn('Incomplete LLVM', results[1]['detail'])
        self.assertIn('Missing checkout', results[2]['detail'])
        execute.assert_not_called()
        self.assertEqual(snapshot(self.root), before)

    def test_wrong_llvm_version_uses_the_installer_validation(self):
        cache = native.llvm_directory(self.root)
        (cache / 'bin').mkdir(parents=True)
        (cache / 'bin/clang-tidy.exe').write_text('version fixture')
        header = cache / 'lib/clang/22/include/stddef.h'
        header.parent.mkdir(parents=True)
        header.write_text('builtin header')
        before = snapshot(self.root)
        with (
            patch.object(diagnose, 'seven_zip', return_value='fixture 7-Zip'),
            patch.object(
                native,
                'run',
                return_value=subprocess.CompletedProcess([], 0, 'LLVM version 21.0.0'),
            ),
        ):
            results = diagnose.diagnose(self.root)
        self.assertFalse(results[1]['ok'])
        self.assertIn('does not match', results[1]['detail'])
        self.assertEqual(snapshot(self.root), before)


if __name__ == '__main__':
    unittest.main()
