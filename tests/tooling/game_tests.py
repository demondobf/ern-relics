"""Verify explicit game paths, isolated profiles, hidden launch, and save backups."""

import hashlib
import io
import json
import os
import tomllib
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from tools.game.backup_saves import backup
from tools.game.launch_test import launch


class GameToolTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(prefix='ern-game-tests-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.package = self.root / 'Package [named]'
        self.package.mkdir()
        (self.package / 'ern-relics.dll').write_bytes(b'fixture DLL')
        (self.package / 'keep.txt').write_text('keep')
        self.me3, self.game = self.root / 'ME3 [local].exe', self.root / 'Game local.exe'
        for path in (self.me3, self.game):
            path.write_text('fixture, not executable')

    def test_caller_paths_check_mode_and_launch_arguments(self):
        caller = Path.cwd()
        output = self.root / 'external profile'
        try:
            os.chdir(self.root)
            with (
                patch('tools.game.launch_test.game_running', return_value=False),
                patch('tools.game.launch_test.subprocess.Popen') as process,
            ):
                profile = launch(
                    Path('Package [named]'),
                    Path('ME3 [local].exe'),
                    Path('Game local.exe'),
                    True,
                    output,
                )
                process.assert_not_called()
                content = profile.read_text()
                self.assertIn('start_online = false', content)
                self.assertIn('ern-relics-test.sl2', content)
                self.assertIn(json.dumps((self.package / 'ern-relics.dll').as_posix()), content)
                launch(self.package, self.me3, self.game, False, output)
                self.assertEqual(
                    process.call_args.args[0],
                    [str(self.me3), 'launch', '--profile', str(profile), '--exe', str(self.game)],
                )
                self.assertEqual(process.call_args.kwargs['cwd'], self.package)
                if os.name == 'nt':
                    self.assertIn('startupinfo', process.call_args.kwargs)
            self.assertEqual(
                {path.name for path in self.package.iterdir()}, {'ern-relics.dll', 'keep.txt'}
            )
            self.assertEqual(Path.cwd(), self.root)
        finally:
            os.chdir(caller)

    def test_busy_game_missing_inputs_and_package_output_are_rejected(self):
        with (
            patch('tools.game.launch_test.game_running', return_value=True),
            self.assertRaisesRegex(RuntimeError, 'already running'),
        ):
            launch(self.package, self.me3, self.game, True, self.root / 'out')
        with patch('tools.game.launch_test.game_running', return_value=False):
            with self.assertRaises(FileNotFoundError):
                launch(self.package, self.root / 'missing.exe', self.game, True)
            with self.assertRaisesRegex(ValueError, 'outside replaceable'):
                launch(self.package, self.me3, self.game, True, self.package / 'profile')
        self.assertFalse((self.package / 'profile').exists())

    def test_non_bmp_paths_produce_valid_toml(self):
        package = self.root / 'Package \U0001f9ea'
        package.mkdir()
        (package / 'ern-relics.dll').write_bytes(b'fixture DLL')
        with (
            patch('tools.game.launch_test.game_running', return_value=False),
            redirect_stdout(io.StringIO()),
        ):
            profile = launch(package, self.me3, self.game, True, self.root / 'Profile \U0001f9ea')
        content = tomllib.loads(profile.read_text(encoding='utf-8'))
        self.assertEqual(content['natives'][0]['path'], (package / 'ern-relics.dll').as_posix())

    def test_backup_checksums_and_source_bytes(self):
        saves = self.root / 'saves'
        saves.mkdir()
        data = b'synthetic save fixture'
        (saves / 'profile.sl2').write_bytes(data)
        (saves / 'unrelated.txt').write_text('do not copy')
        output = backup(saves, self.root / 'backups')
        self.assertEqual((output / 'profile.sl2').read_bytes(), data)
        self.assertEqual((saves / 'profile.sl2').read_bytes(), data)
        manifest = json.loads((output / 'manifest.json').read_text())
        self.assertEqual(
            manifest,
            [
                {
                    'name': 'profile.sl2',
                    'length': len(data),
                    'sha256': hashlib.sha256(data).hexdigest(),
                }
            ],
        )
        self.assertEqual({path.name for path in output.iterdir()}, {'profile.sl2', 'manifest.json'})
        empty = self.root / 'empty'
        empty.mkdir()
        with self.assertRaises(ValueError):
            backup(empty, self.root / 'no-backup')
        self.assertFalse((self.root / 'no-backup').exists())


if __name__ == '__main__':
    unittest.main()
