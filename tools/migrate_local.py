"""Move legacy checkout data without overwriting or losing any file."""
import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from re4pc.assets import sha256_file
from re4pc.filesystem import rename_new
from re4pc.paths import game_dir, logs_dir


def inventory(root):
    records = {}
    for path in sorted(Path(root).rglob('*')):
        name = path.relative_to(root).as_posix()
        if path.is_symlink():
            records[name] = {'symlink': os.readlink(path)}
        elif path.is_file():
            records[name] = {'bytes': path.stat().st_size, 'sha256': sha256_file(path)}
        elif path.is_dir():
            records[name] = {'directory': True}
        else:
            raise ValueError(f'Unsupported local file: {path}')
    return records


def migrate(pairs, receipt):
    receipt = Path(receipt)
    if os.path.lexists(receipt):
        raise ValueError(f'Migration receipt already exists: {receipt}')
    for source, destination in pairs:
        if not source.is_dir() or source.is_symlink():
            raise ValueError(f'Expected a real source directory: {source}')
        if os.path.lexists(destination):
            raise ValueError(f'Destination already exists: {destination}')
        if source == destination or source in destination.parents:
            raise ValueError('Migration destination must be outside its source')
    before = [{'source': str(source), 'destination': str(destination),
               'inventory': inventory(source)} for source, destination in pairs]
    receipt.parent.mkdir(parents=True, exist_ok=True)
    # Persist the pre-move inventory first so interruption is recoverable.
    with receipt.open('x') as stream:
        json.dump(before, stream, indent=2)
        stream.write('\n')
    for (source, destination), record in zip(pairs, before):
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.stat().st_dev == destination.parent.stat().st_dev:
            rename_new(source, destination)
        else:
            with tempfile.TemporaryDirectory(prefix='.re4-move-', dir=destination.parent) as temporary:
                copy = Path(temporary) / 'data'
                shutil.copytree(source, copy, symlinks=True)
                if inventory(copy) != record['inventory']:
                    raise ValueError('Migration copy checksum mismatch; source retained')
                rename_new(copy, destination)
            if inventory(destination) != record['inventory']:
                raise ValueError('Migration checksum mismatch; source retained')
            shutil.rmtree(source)
        if inventory(destination) != record['inventory']:
            raise ValueError(f'Migration checksum mismatch: {destination}')
    verify(receipt)


def verify(receipt):
    for record in json.loads(Path(receipt).read_text()):
        if Path(record['source']).exists():
            raise ValueError(f'Legacy source still exists: {record["source"]}')
        current = inventory(Path(record['destination']))
        if any(current.get(name) != value for name, value in record['inventory'].items()):
            raise ValueError(f'Migration inventory changed: {record["destination"]}')
    print('MIGRATION_VERIFIED')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify', action='store_true')
    parser.add_argument('--receipt', type=Path, default=logs_dir().parent / 'migration.json')
    args = parser.parse_args()
    if args.verify:
        verify(args.receipt)
    else:
        root = Path(__file__).resolve().parent.parent
        migrate([(root / 'game', game_dir()), (root / 'logs', logs_dir())], args.receipt)


if __name__ == '__main__':
    main()
