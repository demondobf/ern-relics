"""Exercise real CMake/Ninja/CTest workflows without compiler or game assets."""

import argparse
import os
import shutil
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tools.process import ROOT, run

CMAKE = 'cmake'
NINJA = 'ninja'


class PresetTests(unittest.TestCase):
    def test_workflows_use_separate_directories_and_propagate_test_failure(self):
        with TemporaryDirectory(prefix='ern-preset-tests-') as directory:
            root = Path(directory)
            shutil.copy2(ROOT / 'CMakePresets.json', root / 'CMakePresets.json')
            project = """cmake_minimum_required(VERSION 3.25)
project(preset_smoke NONE)
enable_testing()
add_custom_target(native_build ALL COMMAND "${CMAKE_COMMAND}" -E touch "${CMAKE_BINARY_DIR}/built.txt")
add_test(NAME workflow_smoke COMMAND "${CMAKE_COMMAND}" -E touch "${CMAKE_BINARY_DIR}/tested.txt")
"""
            (root / 'CMakeLists.txt').write_text(project)
            ninja = shutil.which(NINJA)
            if ninja is None:
                raise RuntimeError('Ninja is required to verify native presets')
            environment = dict(
                os.environ, PATH=str(Path(ninja).parent) + os.pathsep + os.environ['PATH']
            )
            for preset in ('release', 'debug', 'asan'):
                run(
                    [CMAKE, '--workflow', '--preset', preset],
                    cwd=root,
                    env=environment,
                    capture_output=True,
                )
                for marker in ('built.txt', 'tested.txt'):
                    self.assertTrue((root / '.build' / preset / marker).is_file())
            (root / 'CMakeLists.txt').write_text(
                project + 'add_test(NAME intentional_failure COMMAND "${CMAKE_COMMAND}" -E false)\n'
            )
            with self.assertRaises(subprocess.CalledProcessError) as error:
                run(
                    [CMAKE, '--workflow', '--preset', 'release', '--fresh'],
                    cwd=root,
                    env=environment,
                    capture_output=True,
                )
            self.assertIn('intentional_failure', error.exception.stdout)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cmake', default=CMAKE)
    parser.add_argument('--ninja', default=NINJA)
    arguments = parser.parse_args()
    CMAKE, NINJA = arguments.cmake, arguments.ninja
    unittest.main(argv=[__file__])
