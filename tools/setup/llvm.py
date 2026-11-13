"""Install the pinned LLVM analyzer for local development and CI."""

import argparse
import hashlib
import shutil
import urllib.request
from pathlib import Path

from tools.build.output import move_new, safe_path, temporary_directory
from tools.process import ROOT, cli, run
from tools.setup.native import clang_tidy, llvm_directory, llvm_version, seven_zip

VERSION = '22.1.3'
SHA256 = '72ca54c3b7940615776d8994c0b918a1d8c4981bdcf13b439eaa86a1bd477001'


def download(url, destination):
    with urllib.request.urlopen(url, timeout=120) as response, destination.open('wb') as stream:
        shutil.copyfileobj(response, stream)


def setup(root=ROOT):
    root = Path(root)
    version, directory = llvm_version(root), safe_path(llvm_directory(root))
    if directory.exists():
        clang_tidy(root, directory)
        print(f'LLVM {version} ready: {directory}')
        return directory
    extractor = seven_zip()
    if version != VERSION:
        raise ValueError('Update the LLVM download checksum in tools/setup/llvm.py for the new pin')
    url = f'https://github.com/llvm/llvm-project/releases/download/llvmorg-{version}/LLVM-{version}-win64.exe'
    with temporary_directory(directory.parent, '.stage-llvm-') as stage:
        installer = stage / 'LLVM.exe'
        download(url, installer)
        with installer.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != SHA256:
                raise ValueError('The LLVM installer checksum differs. Nothing installed.')
        expanded = stage / 'expanded'
        run(
            [extractor, 'x', installer, f'-o{expanded}', 'bin/clang-tidy.exe', 'lib/clang/*', '-y'],
            capture_output=True,
        )
        clang_tidy(root, expanded)
        move_new(directory.parent, expanded, directory)
    print(f'LLVM {version} ready: {directory}')
    return directory


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    setup()


if __name__ == '__main__':
    cli(main)
