"""Verify caller-relative paths, exact package bytes, child environment, and failures."""

import os
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from tools.build.verify import verify


class VerifyPathsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(prefix='ern-verify-tests-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.build = self.root / 'Build [local]'
        self.package = self.root / 'Package [smoke]'
        self.game = self.root / 'Game directory'
        for directory in (self.build, self.package, self.game, self.root / 'config'):
            directory.mkdir()
        for filename in (
            'ern-relics-host.exe',
            'ern-relics-host.pdb',
            'ern-relics.dll',
            'ern-relics.pdb',
            'clang_rt.asan_dynamic-x86_64.dll',
        ):
            (self.build / filename).write_text('build ' + filename)
        (self.root / 'config/ern-relics.ini').write_text('default ini')
        (self.package / 'ern-relics.dll').write_text('exact packaged DLL')
        (self.package / 'ern-relics.ini').write_text('exact packaged ini')
        (self.package / 'ern-relics.pdb').write_text('exact packaged symbols')
        self.host_directory = None
        self.environment = None

    def execute(self, arguments, **options):
        if Path(arguments[0]).name == 'ern-relics-host.exe':
            directory = Path(options['cwd'])
            self.host_directory = directory
            self.environment = options['env']
            packaged = arguments[1] == '--smoke-test'
            self.assertEqual(
                (directory / 'ern-relics.dll').read_text(),
                'exact packaged DLL' if packaged else 'build ern-relics.dll',
            )
            self.assertEqual(
                (directory / 'ern-relics.ini').read_text(),
                'exact packaged ini' if packaged else 'default ini',
            )
            self.assertEqual(
                (directory / 'ern-relics.pdb').read_text(),
                'exact packaged symbols' if packaged else 'build ern-relics.pdb',
            )
            self.assertTrue((directory / 'clang_rt.asan_dynamic-x86_64.dll').is_file())
            (directory / 'host-test.txt').write_text('PASS: synthetic host')
        return subprocess.CompletedProcess(arguments, 0)

    def test_package_selection_and_environment_are_isolated(self):
        with (
            patch.dict(
                os.environ,
                {
                    'ERN_RELICS_TEST_GAME_DIRECTORY': 'caller game',
                    'ERN_RELICS_TEST_REGULATION': 'caller regulation',
                },
            ),
            patch('tools.build.verify.run', side_effect=self.execute),
        ):
            verify(self.build, self.package, root=self.root)
            self.assertNotIn('ERN_RELICS_TEST_GAME_DIRECTORY', self.environment)
            self.assertNotIn('ERN_RELICS_TEST_REGULATION', self.environment)
            self.assertEqual(os.environ['ERN_RELICS_TEST_GAME_DIRECTORY'], 'caller game')
            self.assertEqual(os.environ['ERN_RELICS_TEST_REGULATION'], 'caller regulation')
        self.assertFalse(self.host_directory.exists())

    def test_caller_paths_and_audit_arguments(self):
        caller = Path.cwd()
        regulation = self.root / 'custom regulation.bin'
        regulation.write_bytes(b'fixture')
        try:
            os.chdir(self.root)
            with patch('tools.build.verify.run', side_effect=self.execute) as command:
                verify(
                    Path('Build [local]'),
                    game_directory=Path('Game directory'),
                    regulation_path=Path('custom regulation.bin'),
                    root=self.root,
                )
            self.assertEqual(self.environment['ERN_RELICS_TEST_GAME_DIRECTORY'], str(self.game))
            self.assertEqual(self.environment['ERN_RELICS_TEST_REGULATION'], str(regulation))
            arguments = command.call_args.args[0]
            self.assertIn('tools.assets.verify_regulation', arguments)
            self.assertIn(self.game, arguments)
            self.assertIn(regulation, arguments)
            self.assertEqual(Path.cwd(), self.root)
        finally:
            os.chdir(caller)

    def test_reject_mixed_or_missing_inputs_host_failure_and_timeout(self):
        with self.assertRaisesRegex(ValueError, 'synthetic data only'):
            verify(self.build, self.package, self.game, root=self.root)
        (self.package / 'ern-relics.ini').unlink()
        with self.assertRaisesRegex(ValueError, 'missing ern-relics.ini'):
            verify(self.build, self.package, root=self.root)
        with patch('tools.build.verify.run', return_value=subprocess.CompletedProcess([], 7)):
            with self.assertRaisesRegex(RuntimeError, 'exit 7'):
                verify(self.build, root=self.root)
        with patch('tools.build.verify.run', side_effect=subprocess.TimeoutExpired('host', 30)):
            with self.assertRaises(subprocess.TimeoutExpired):
                verify(self.build, root=self.root)
        with self.assertRaises(FileNotFoundError):
            verify(self.build, self.root / 'missing package', root=self.root)


if __name__ == '__main__':
    unittest.main()
