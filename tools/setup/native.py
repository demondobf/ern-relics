"""Read pinned analyzer metadata and require an explicitly activated Windows shell."""

import os
import re
import shutil
import tomllib
from pathlib import Path

from tools.process import ROOT, run


def llvm_version(root=ROOT):
    project = tomllib.loads((Path(root) / 'pyproject.toml').read_text(encoding='utf-8'))
    for requirement in project['dependency-groups']['dev']:
        if re.fullmatch(r'clang-format==\d+\.\d+\.\d+', requirement):
            return requirement.split('==')[1]
    raise ValueError('Cannot read the clang-format pin in pyproject.toml')


def llvm_directory(root=ROOT):
    return Path(root) / '.tools/llvm' / llvm_version(root)


def clang_tidy(root=ROOT, directory=None):
    version = llvm_version(root)
    directory = Path(directory) if directory is not None else llvm_directory(root)
    executable = directory / 'bin/clang-tidy.exe'
    header = directory / f'lib/clang/{version.split(".")[0]}/include/stddef.h'
    if not executable.is_file() or not header.is_file():
        raise RuntimeError(
            f'Incomplete LLVM {version}; run python -m tools.setup.llvm after removing {directory}'
        )
    actual = run([executable, '--version'], capture_output=True).stdout
    if not re.search(rf'\bLLVM version {re.escape(version)}\b', actual):
        raise RuntimeError(f'LLVM does not match version {version}: {directory}')
    return executable


def seven_zip():
    installed = shutil.which('7z')
    if installed:
        return Path(installed)
    fallback = Path(os.environ.get('ProgramFiles', r'C:\Program Files')) / '7-Zip/7z.exe'
    if fallback.is_file():
        return fallback
    raise RuntimeError('Install 7-Zip to extract LLVM')


def require_native_shell():
    if os.name != 'nt' or os.environ.get('VSCMD_ARG_TGT_ARCH') != 'x64':
        raise RuntimeError('Activate the Windows compiler first: ./tools/setup/shell.ps1')
    for name in ('cmake', 'ctest', 'ninja', 'cl'):
        if not shutil.which(name):
            raise RuntimeError(f'{name} is unavailable; run ./tools/setup/shell.ps1')
