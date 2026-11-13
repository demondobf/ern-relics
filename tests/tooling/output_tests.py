"""Preserve tested output, frozen releases, and filesystem boundaries."""

import inspect
import os
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tools.build.output import remove_child, safe_path, write_build_output
from tools.build.package import build
from tools.check import check
from tools.release.manifest import PACKAGE_FILES, PROJECT_FILES


class OutputTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(prefix='ern-output-tests-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.runtime = self.root / 'runtime'
        self.runtime.mkdir()
        (self.runtime / 'ern-relics.dll').write_bytes(b'first DLL')
        for filename, source in PROJECT_FILES.items():
            path = self.root / source
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(filename)

    def test_default_dev_and_validation_before_replacement(self):
        for command in (build, check):
            self.assertEqual(inspect.signature(command).parameters['label'].default, 'dev')
        name = 'ern-relics-1.0.0-dev'
        output = write_build_output(self.root, self.runtime, name)
        self.assertEqual({path.name for path in output.iterdir()}, PACKAGE_FILES)
        (output / 'journal.bin').write_bytes(b'keep until validation succeeds')
        (self.runtime / 'ern-relics.dll').write_bytes(b'new DLL')

        def reject(stage):
            self.assertEqual((stage / 'ern-relics.dll').read_bytes(), b'new DLL')
            raise RuntimeError('Synthetic package rejection')

        with self.assertRaisesRegex(RuntimeError, 'package rejection'):
            write_build_output(self.root, self.runtime, name, reject)
        self.assertEqual((output / 'ern-relics.dll').read_bytes(), b'first DLL')
        self.assertTrue((output / 'journal.bin').exists())
        validated = []
        write_build_output(
            self.root,
            self.runtime,
            name,
            lambda stage: validated.append((stage / 'ern-relics.dll').read_bytes()),
        )
        self.assertEqual(validated, [b'new DLL'])
        self.assertEqual((output / 'ern-relics.dll').read_bytes(), b'new DLL')
        self.assertFalse((output / 'journal.bin').exists())
        self.assertFalse(list((self.root / 'dist').glob('.stage-*')))

    def test_frozen_release_and_other_packages_survive(self):
        frozen = write_build_output(self.root, self.runtime, 'ern-relics-1.0.0')
        archive = self.root / 'dist/ern-relics-1.0.0.zip'
        archive.write_bytes(b'frozen archive')
        checksum = archive.with_suffix('.zip.sha256')
        checksum.write_bytes(b'frozen checksum')
        for _ in range(2):
            with self.assertRaises(FileExistsError):
                write_build_output(self.root, self.runtime, 'ern-relics-1.0.0')
        first = write_build_output(self.root, self.runtime, 'ern-relics-1.0.0-dev')
        (self.runtime / 'ern-relics.dll').write_bytes(b'feature DLL')
        feature = write_build_output(self.root, self.runtime, 'ern-relics-1.0.0-feature')
        self.assertEqual((first / 'ern-relics.dll').read_bytes(), b'first DLL')
        self.assertEqual((feature / 'ern-relics.dll').read_bytes(), b'feature DLL')
        self.assertEqual((frozen / 'ern-relics.dll').read_bytes(), b'first DLL')
        self.assertEqual(archive.read_bytes(), b'frozen archive')
        self.assertEqual(checksum.read_bytes(), b'frozen checksum')

    def test_failed_staging_and_traversal(self):
        output = write_build_output(self.root, self.runtime, 'ern-relics-1.0.0-dev')
        (self.root / 'LICENSE').unlink()
        with self.assertRaises(FileNotFoundError):
            write_build_output(self.root, self.runtime, output.name)
        self.assertEqual((output / 'ern-relics.dll').read_bytes(), b'first DLL')
        with self.assertRaises(ValueError):
            write_build_output(self.root, self.runtime, '../outside')
        with self.assertRaises(ValueError):
            remove_child(self.root / 'dist', self.root)
        self.assertFalse(list((self.root / 'dist').glob('.stage-*')))

    def test_junctions_are_rejected_before_cleanup(self):
        target = self.root / 'keep'
        target.mkdir()
        sentinel = target / 'sentinel.txt'
        sentinel.write_bytes(b'preserve')
        generated = self.root / 'generated'
        generated.mkdir()
        link = generated / 'junction'
        if os.name == 'nt':
            environment = dict(os.environ, ERN_TEST_LINK=str(link), ERN_TEST_TARGET=str(target))
            subprocess.run(
                [
                    'pwsh',
                    '-NoProfile',
                    '-Command',
                    'New-Item -ItemType Junction -Path $env:ERN_TEST_LINK -Target $env:ERN_TEST_TARGET | Out-Null',
                ],
                env=environment,
                check=True,
                capture_output=True,
            )
        else:
            link.symlink_to(target, target_is_directory=True)
        try:
            with self.assertRaisesRegex(ValueError, 'reparse'):
                safe_path(link / 'sentinel.txt')
            with self.assertRaisesRegex(ValueError, 'reparse'):
                remove_child(self.root, generated)
            self.assertEqual(sentinel.read_bytes(), b'preserve')
        finally:
            if os.name == 'nt':
                link.rmdir()
            else:
                link.unlink()


if __name__ == '__main__':
    unittest.main()
