"""A release freezes its private checked candidate despite development rebuilds."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zipfile import ZipFile

from tools.build.output import write_build_output
from tools.release.build import build_release
from tools.release.manifest import PROJECT_FILES


class ReleaseBuildTests(unittest.TestCase):
    def test_candidate_is_private_until_freezing_and_owned_directories_are_cleaned(self):
        with TemporaryDirectory(prefix='ern-release-build-') as directory:
            root = Path(directory)
            (root / 'version.txt').write_text('1.0.2\n')
            for name, source in PROJECT_FILES.items():
                path = root / source
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(name.encode())
            runtime = root / 'runtime'
            runtime.mkdir()
            dll = runtime / 'ern-relics.dll'
            dll.write_bytes(b'checked candidate')
            used = {}

            def check(*, build_directory, package_directory, jobs, root):
                self.assertTrue(build_directory.is_dir())
                self.assertNotEqual(build_directory, root / '.build/release')
                used.update(build=build_directory, candidate=package_directory)
                candidate = write_build_output(
                    root, runtime, 'ern-relics-1.0.2-dev', destination=package_directory
                )
                # A development build publishes different bytes after this check.
                dll.write_bytes(b'unrelated development rebuild')
                write_build_output(root, runtime, 'ern-relics-1.0.2-dev')
                return candidate

            with patch('tools.release.build.check', side_effect=check):
                release = build_release(root / 'dist', root=root)
            with ZipFile(release.archive) as archive:
                self.assertEqual(archive.read('ern-relics.dll'), b'checked candidate')
            self.assertEqual(
                (root / 'dist/ern-relics-1.0.2-dev/ern-relics.dll').read_bytes(),
                b'unrelated development rebuild',
            )
            self.assertFalse(used['build'].exists())
            self.assertFalse(used['candidate'].parent.exists())


if __name__ == '__main__':
    unittest.main()
