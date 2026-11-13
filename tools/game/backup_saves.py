"""Copy explicitly supplied saves into a new backup and verify every byte by SHA-256."""

import argparse
import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from tools.build.output import safe_path
from tools.process import cli


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def backup(save_directory, destination):
    source = Path(save_directory).resolve(strict=True)
    files = sorted(path for path in source.glob('*.sl2') if path.is_file())
    if not files:
        raise ValueError('No Nightreign .sl2 saves found in the supplied directory')
    output = safe_path(Path(destination) / datetime.now(UTC).strftime('%Y%m%d-%H%M%S-%f'))
    output.mkdir(parents=True, exist_ok=False)
    manifest = []
    for path in files:
        expected = digest(path)
        copy = output / path.name
        shutil.copy2(path, copy)
        if digest(copy) != expected:
            raise ValueError(f'Backup verification failed for {path.name}')
        manifest.append({'name': path.name, 'length': copy.stat().st_size, 'sha256': expected})
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(f'Verified {len(files)} save backups: {output}')
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--save-directory', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    backup(args.save_directory, args.destination)


if __name__ == '__main__':
    cli(main)
