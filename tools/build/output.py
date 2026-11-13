"""Stage verified output and reject traversal, reparse points, and release replacement."""

import os
import re
import shutil
import stat
import tempfile
from contextlib import contextmanager
from pathlib import Path

from tools.release.manifest import PROJECT_FILES


def is_reparse(path):
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
    )


def safe_path(path):
    path = Path(os.path.abspath(path))
    for ancestor in (path, *path.parents):
        try:
            if is_reparse(ancestor):
                raise ValueError(f'Generated output cannot use a reparse point: {ancestor}')
        except FileNotFoundError:
            pass
    return path


def remove_child(root, path):
    root, path = safe_path(root), safe_path(path)
    if path.parent != root:
        raise ValueError(f'Refusing to remove a directory outside generated output: {path}')
    if not path.exists():
        return
    pending = [path]
    checked = []
    while pending:
        current = pending.pop()
        if is_reparse(current):
            raise ValueError(f'Refusing to remove a tree containing reparse points: {current}')
        checked.append(current)
        if current.is_dir():
            pending.extend(current.iterdir())
    # copy2 preserves Windows read-only attributes. Validate the entire tree
    # before making owned output writable or deleting any of it.
    for current in checked:
        mode = current.stat().st_mode
        if not mode & stat.S_IWRITE:
            current.chmod(mode | stat.S_IWRITE)
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


@contextmanager
def temporary_directory(parent=None, prefix='ern-relics-'):
    parent = safe_path(parent if parent is not None else tempfile.gettempdir())
    parent.mkdir(parents=True, exist_ok=True)
    path = Path(tempfile.mkdtemp(prefix=prefix, dir=parent))
    try:
        yield path
    finally:
        remove_child(parent, path)


def move_new(root, source, destination):
    root, source, destination = safe_path(root), safe_path(source), safe_path(destination)
    if not source.is_relative_to(root) or not destination.is_relative_to(root):
        raise ValueError('Publication must stay within its output directory')
    if destination.exists():
        raise FileExistsError(
            f'Release output already exists; it will not be replaced: {destination}'
        )
    # Windows rename refuses existing destinations, including a collision after preflight.
    source.rename(destination)


def write_build_output(root, runtime, name, validate=None):
    if not re.fullmatch(r'ern-relics-\d+\.\d+\.\d+(?:-[a-z0-9]+(?:[.-][a-z0-9]+)*)?', name):
        raise ValueError('Invalid package name')
    root = safe_path(root)
    dist = safe_path(root / 'dist')
    output = safe_path(dist / name)
    with temporary_directory(dist, '.stage-') as stage:
        shutil.copy2(Path(runtime) / 'ern-relics.dll', stage / 'ern-relics.dll')
        for destination, source in PROJECT_FILES.items():
            shutil.copy2(root / source, stage / destination)
        if validate is not None:
            validate(stage)
        if re.fullmatch(r'ern-relics-\d+\.\d+\.\d+', name):
            move_new(dist, stage, output)
        else:
            remove_child(dist, output)
            move_new(dist, stage, output)
    return output
