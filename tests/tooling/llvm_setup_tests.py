"""Validate LLVM prerequisites, download integrity, staging, and cache reuse offline."""

import hashlib
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from tools.setup import llvm
from tools.setup.native import llvm_directory


class LLVMSetupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(prefix='ern-llvm-tests-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / 'pyproject.toml').write_text(
            f'[dependency-groups]\ndev = ["clang-format=={llvm.VERSION}"]\n'
        )

    def test_missing_extractor_and_unknown_pin_do_not_download(self):
        with (
            patch.object(llvm, 'seven_zip', side_effect=RuntimeError('7-Zip unavailable')),
            patch.object(llvm, 'download') as download,
        ):
            with self.assertRaisesRegex(RuntimeError, '7-Zip'):
                llvm.setup(self.root)
            download.assert_not_called()
        self.assertFalse((self.root / '.tools').exists())
        (self.root / 'pyproject.toml').write_text(
            '[dependency-groups]\ndev = ["clang-format==99.0.0"]\n'
        )
        with (
            patch.object(llvm, 'seven_zip', return_value='unused-7z'),
            patch.object(llvm, 'download') as download,
        ):
            with self.assertRaisesRegex(ValueError, 'checksum'):
                llvm.setup(self.root)
            download.assert_not_called()

    def test_corrupt_downloads_are_rejected_and_cleaned(self):
        def corrupt(url, destination):
            destination.write_bytes(b'corrupt installer')

        with (
            patch.object(llvm, 'seven_zip', return_value='unused-7z'),
            patch.object(llvm, 'download', side_effect=corrupt),
            patch.object(llvm, 'run') as extract,
        ):
            for _ in range(2):
                with self.assertRaisesRegex(ValueError, 'checksum differs'):
                    llvm.setup(self.root)
            extract.assert_not_called()
        self.assertEqual(list((self.root / '.tools/llvm').iterdir()), [])

    def test_incomplete_cache_is_reported_without_execution_or_download(self):
        directory = llvm_directory(self.root)
        (directory / 'bin').mkdir(parents=True)
        (directory / 'bin/clang-tidy.exe').write_text('not executable')
        (directory / 'lib/clang').mkdir(parents=True)
        with (
            patch.object(llvm, 'download') as download,
            self.assertRaisesRegex(RuntimeError, 'Incomplete LLVM'),
        ):
            llvm.setup(self.root)
        download.assert_not_called()

    def test_verified_install_is_published_then_reused(self):
        payload = b'offline verified installer'

        def download(url, destination):
            destination.write_bytes(payload)

        def extract(arguments, **options):
            if Path(arguments[2]).suffix != '.tar':
                return
            expanded = Path(
                next(argument[2:] for argument in arguments if str(argument).startswith('-o'))
            )
            expanded /= f'clang+llvm-{llvm.VERSION}-x86_64-pc-windows-msvc'
            (expanded / 'bin').mkdir(parents=True)
            (expanded / 'bin/clang-tidy.exe').write_bytes(b'analyzer fixture')

        with (
            patch.object(llvm, 'SHA256', hashlib.sha256(payload).hexdigest()),
            patch.object(llvm, 'seven_zip', return_value='fixture-7z'),
            patch.object(llvm, 'download', side_effect=download) as fetch,
            patch.object(llvm, 'run', side_effect=extract) as extraction,
            patch.object(llvm, 'clang_tidy'),
        ):
            directory = llvm.setup(self.root)
            self.assertTrue((directory / 'bin/clang-tidy.exe').is_file())
            llvm.setup(self.root)
            self.assertEqual(fetch.call_count, 1)
            self.assertEqual(extraction.call_count, 2)
            self.assertTrue(fetch.call_args.args[0].endswith('-windows-msvc.tar.zst'))
        self.assertEqual(list(directory.parent.iterdir()), [directory])


if __name__ == '__main__':
    unittest.main()
