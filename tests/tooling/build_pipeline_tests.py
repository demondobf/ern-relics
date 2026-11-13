"""Check native CLI sequencing and production DLL validation before publication."""

import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from tools.build.package import build
from tools.release.manifest import PROJECT_FILES


class BuildPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(prefix='ern-build-tests-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.directory = self.root / 'build [native]'
        self.directory.mkdir()
        for name, source in PROJECT_FILES.items():
            path = self.root / source
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(name)
        (self.directory / 'CMakeCache.txt').write_text('CMAKE_PROJECT_VERSION:STATIC=1.0.2\n')
        (self.directory / 'runtime').mkdir()
        (self.directory / 'runtime/ern-relics.dll').write_bytes(b'production DLL')

    def test_native_commands_and_exact_staged_validation(self):
        def validate(directory, package, *, root):
            self.assertEqual(directory, self.directory)
            self.assertEqual(root, self.root)
            self.assertEqual((package / 'ern-relics.dll').read_bytes(), b'production DLL')

        with (
            patch('tools.build.package.require_native_shell'),
            patch('tools.build.package.run') as command,
            patch('tools.build.package.verify', side_effect=validate) as verifier,
        ):
            package = build(build_directory=self.directory, jobs=2, root=self.root)
        self.assertEqual(
            [call.args[0][0] for call in command.call_args_list], ['cmake', 'cmake', 'ctest']
        )
        self.assertIn('--parallel', command.call_args_list[1].args[0])
        self.assertIn('--no-tests=error', command.call_args_list[2].args[0])
        verifier.assert_called_once()
        self.assertEqual(package.name, 'ern-relics-1.0.2-dev')
        self.assertEqual((package / 'ern-relics.dll').read_bytes(), b'production DLL')

    def test_custom_labels_stay_in_the_development_namespace(self):
        with (
            patch('tools.build.package.require_native_shell'),
            patch('tools.build.package.run'),
            patch('tools.build.package.verify'),
        ):
            package = build(label='rc1', build_directory=self.directory, root=self.root)
        self.assertEqual(package.name, 'ern-relics-1.0.2-rc1-dev')

    def test_default_build_directory_matches_the_native_preset(self):
        with (
            patch('tools.build.package.require_native_shell'),
            patch('tools.build.package.run') as command,
            patch('tools.build.package.verify'),
        ):
            build(preset='asan', root=self.root)
        self.assertEqual(command.call_args_list[0].args[0][4], self.root / '.build/asan')

    def test_analysis_failure_preserves_the_existing_package(self):
        package = self.root / 'dist/ern-relics-1.0.2-dev'
        package.mkdir(parents=True)
        (package / 'ern-relics.dll').write_bytes(b'previous DLL')
        with (
            patch('tools.build.package.require_native_shell'),
            patch('tools.build.package.run'),
            patch('tools.build.package.analyze', side_effect=RuntimeError('Analysis failed')),
            self.assertRaisesRegex(RuntimeError, 'Analysis failed'),
        ):
            build(build_directory=self.directory, root=self.root, analysis=True)
        self.assertEqual((package / 'ern-relics.dll').read_bytes(), b'previous DLL')

    def test_failures_do_not_publish_and_asan_does_not_package(self):
        with (
            patch('tools.build.package.require_native_shell'),
            patch('tools.build.package.run', side_effect=subprocess.CalledProcessError(1, 'ctest')),
        ):
            with self.assertRaises(subprocess.CalledProcessError):
                build(build_directory=self.directory, root=self.root)
        self.assertFalse((self.root / 'dist').exists())
        with (
            patch('tools.build.package.require_native_shell'),
            patch('tools.build.package.run'),
            patch('tools.build.package.verify') as verifier,
        ):
            self.assertIsNone(build(preset='asan', build_directory=self.directory, root=self.root))
            verifier.assert_not_called()
        self.assertFalse((self.root / 'dist').exists())


if __name__ == '__main__':
    unittest.main()
