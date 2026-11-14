"""Install the pinned LLVM analyzer for local development and CI."""

import argparse
import hashlib
import shutil
import urllib.request
from pathlib import Path

from tools.build.output import move_new, safe_path, temporary_directory
from tools.process import ROOT, cli, run
from tools.setup.native import clang_tidy, llvm_directory, llvm_version, seven_zip

VERSION = '23.1.5'
SHA256 = 'b2be33385ddc86e83511417a060de927ae8b09d1f3017cc3cdce5c73cd5029d7'


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
    name = f'clang+llvm-{version}-x86_64-pc-windows-msvc'
    url = f'https://github.com/llvm/llvm-project/releases/download/llvmorg-{version}/{name.replace("+", "%2B")}.tar.zst'
    with temporary_directory(directory.parent, '.stage-llvm-') as stage:
        archive = stage / 'LLVM.tar.zst'
        download(url, archive)
        with archive.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != SHA256:
                raise ValueError('The LLVM archive checksum differs. Nothing installed.')
        run([extractor, 'x', archive, f'-o{stage}', '-y'], capture_output=True)
        expanded = stage / 'expanded'
        run(
            [
                extractor,
                'x',
                stage / 'LLVM.tar',
                f'-o{expanded}',
                f'{name}/bin/clang-tidy.exe',
                f'{name}/lib/clang/*',
                '-y',
            ],
            capture_output=True,
        )
        clang_tidy(root, expanded / name)
        move_new(directory.parent, expanded / name, directory)
    print(f'LLVM {version} ready: {directory}')
    return directory


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    setup()


if __name__ == '__main__':
    cli(main)
