"""Verify release bytes and checksums and reject contaminated or existing output."""

import hashlib
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from tools.build.output import temporary_directory
from tools.process import ROOT
from tools.release.manifest import PACKAGE_FILES
from tools.release.package import package_release


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(prefix='ern-package-tests-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / 'source [package]'
        self.source.mkdir()
        for filename in PACKAGE_FILES:
            (self.source / filename).write_bytes(filename.encode())

    def test_package_bytes_checksum_and_existing_output(self):
        # Stage on the output volume even when hosted-runner TEMP is on another drive.
        with temporary_directory(ROOT / 'output', 'package-test-') as output:
            result = package_release(self.source, '1.0.3', output)
            with ZipFile(result.archive) as zipped:
                self.assertEqual(set(zipped.namelist()), PACKAGE_FILES)
                for filename in PACKAGE_FILES:
                    self.assertEqual(zipped.read(filename), (self.source / filename).read_bytes())
            digest = hashlib.sha256(result.archive.read_bytes()).hexdigest()
            self.assertEqual(
                result.checksum.read_bytes(), f'{digest}  {result.archive.name}\n'.encode()
            )
            original = result.archive.read_bytes()
            with self.assertRaises(FileExistsError):
                package_release(self.source, '1.0.3', output)
            self.assertEqual(result.archive.read_bytes(), original)
            self.assertFalse(list(output.glob('.stage-*')))

    def test_every_existing_release_artifact_is_preserved(self):
        for suffix in ('', '.zip', '.zip.sha256'):
            with self.subTest(suffix=suffix):
                output = self.root / f'output-{len(suffix)}'
                output.mkdir()
                frozen = output / f'ern-relics-1.0.3{suffix}'
                frozen.write_bytes(b'preserve')
                with self.assertRaises(FileExistsError):
                    package_release(self.source, '1.0.3', output)
                self.assertEqual(frozen.read_bytes(), b'preserve')

    def test_reject_runtime_files_directories_missing_notices_and_empty_files(self):
        for name in ('journal.bin', 'presets.json', 'unexpected.ini'):
            path = self.source / name
            path.write_bytes(b'local state')
            with self.assertRaises(ValueError):
                package_release(self.source, '1.0.3', self.root / 'out')
            path.unlink()
        directory = self.source / 'presets'
        directory.mkdir()
        with self.assertRaises(ValueError):
            package_release(self.source, '1.0.3', self.root / 'out')
        directory.rmdir()
        (self.source / 'LICENSE').write_bytes(b'')
        with self.assertRaises(ValueError):
            package_release(self.source, '1.0.3', self.root / 'out')
        (self.source / 'LICENSE').unlink()
        with self.assertRaises(ValueError):
            package_release(self.source, '1.0.3', self.root / 'out')
        self.assertFalse((self.root / 'out').exists())


if __name__ == '__main__':
    unittest.main()
