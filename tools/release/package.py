"""Freeze a clean development package as a release ZIP and checksum."""

import argparse
import hashlib
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from tools.build.output import move_new, safe_path, temporary_directory
from tools.process import ROOT, cli
from tools.release.manifest import PACKAGE_FILES


@dataclass(frozen=True)
class ReleaseArtifacts:
    package: Path
    archive: Path
    checksum: Path
    sha256: str


def package_release(package_directory, version, output_directory=ROOT / 'dist'):
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:-[a-z0-9]+(?:[.-][a-z0-9]+)*)?', version):
        raise ValueError('Invalid release version')
    if version.endswith('-dev'):
        raise ValueError('The -dev suffix is reserved for replaceable development output')
    source, dist = safe_path(package_directory), safe_path(output_directory)
    items = list(source.iterdir())
    if {path.name for path in items} != PACKAGE_FILES or any(
        not safe_path(path).is_file() or path.stat().st_size == 0 for path in items
    ):
        raise ValueError('Package only a clean build containing the expected release files')
    name = f'ern-relics-{version}'
    package, archive = dist / name, dist / f'{name}.zip'
    checksum = dist / f'{name}.zip.sha256'
    for path in (package, archive, checksum):
        if path.exists():
            raise FileExistsError(f'Release output already exists; it will not be replaced: {path}')
    with temporary_directory(dist, '.stage-') as stage:
        staged_package = stage / name
        staged_package.mkdir()
        for filename in sorted(PACKAGE_FILES):
            shutil.copy2(source / filename, staged_package / filename)
        staged_archive = stage / archive.name
        with ZipFile(staged_archive, 'w', compression=ZIP_DEFLATED) as zipped:
            for filename in sorted(PACKAGE_FILES):
                zipped.write(staged_package / filename, filename)
        with ZipFile(staged_archive) as zipped:
            if (
                len(zipped.infolist()) != len(PACKAGE_FILES)
                or set(zipped.namelist()) != PACKAGE_FILES
            ):
                raise ValueError('The ZIP contains unexpected or missing files')
            for filename in PACKAGE_FILES:
                if zipped.read(filename) != (staged_package / filename).read_bytes():
                    raise ValueError(f'The ZIP changed {filename}')
        with staged_archive.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        staged_checksum = stage / checksum.name
        staged_checksum.write_text(f'{digest}  {archive.name}\n', encoding='utf-8', newline='\n')
        for origin, destination in (
            (staged_package, package),
            (staged_archive, archive),
            (staged_checksum, checksum),
        ):
            move_new(dist, origin, destination)
    return ReleaseArtifacts(package, archive, checksum, digest)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package-directory', type=Path, required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--output-directory', type=Path, default=ROOT / 'dist')
    args = parser.parse_args()
    release = package_release(args.package_directory, args.version, args.output_directory)
    print(f'Created {release.archive} and {release.checksum}')


if __name__ == '__main__':
    cli(main)
