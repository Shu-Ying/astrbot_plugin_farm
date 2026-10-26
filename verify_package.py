"""AstrBot插件ZIP的独立完整性校验；只使用标准库。"""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
from zipfile import ZipFile


ROOT_NAME = 'astrbot_plugin_farm'
MANIFEST = 'FARM-MANIFEST.json'
MAX_BYTES = 100 * 1024 * 1024
MAX_ARCHIVE_BYTES = 16 * 1024 * 1024


def safe_path(name):
    path = PurePosixPath(name)
    if (not name or '\\' in name or ':' in name or path.is_absolute()
            or any(p in ('', '.', '..') for p in name.split('/'))):
        raise ValueError('Unsafe package path')
    return path


def verify_files(files):
    if MANIFEST not in files or len(files[MANIFEST]) > 1024 * 1024:
        raise ValueError('Missing or oversized manifest')
    manifest = json.loads(files[MANIFEST])
    if (manifest.get('schema') != 1 or manifest.get('target') != 'astrbot'
            or manifest.get('plugin') != ROOT_NAME):
        raise ValueError('Invalid package identity')
    expected = manifest.get('files')
    if (not isinstance(expected, dict)
            or set(files) != set(expected) | {MANIFEST}):
        raise ValueError('Package files differ from manifest')
    for name, digest in expected.items():
        safe_path(name)
        if hashlib.sha256(files[name]).hexdigest() != digest:
            raise ValueError('Package checksum mismatch')
    required = {'main.py', 'avatars.py', 'metadata.yaml', '_conf_schema.json',
                'runtime.py', 'README.md', 'CHANGELOG.md', 'logo.png',
                'logo-readme.png',
                'images/farm-preview.png',
                'requirements.txt', 'LICENSE', 'version.txt', '_version.py',
                '_vendor/farm_core/__init__.py',
                '_vendor/farm_render/data/asset-manifest.json',
                '_vendor/farm_render/data/font-manifest.json',
                '_vendor/farm_render/data/OFL-Xiaolai.txt'}
    if any(name.endswith('/assets.zip') for name in files):
        raise ValueError('Resource ZIP must not be in plugin repository')
    if not required <= set(files):
        raise ValueError('Incomplete plugin')
    metadata = json.loads(files['metadata.yaml'])
    if (metadata.get('name') != ROOT_NAME
            or metadata.get('version') != manifest['version']
            or files['version.txt'].decode().strip() != manifest['version']):
        raise ValueError('Package version mismatch')
    return manifest


def read_package(path):
    with ZipFile(path) as archive:
        items = archive.infolist()
        names = [item.filename for item in items]
        if (len(names) != len(set(names)) or len(names) > 200
                or sum(item.file_size for item in items) > MAX_BYTES):
            raise ValueError('Duplicate paths or package too large')
        files = {}
        for item in items:
            name = safe_path(item.filename)
            if (len(name.parts) < 2 or name.parts[0] != ROOT_NAME
                    or item.is_dir()
                    or stat.S_ISLNK(item.external_attr >> 16)):
                raise ValueError('Unexpected package root or link')
            files[name.relative_to(ROOT_NAME).as_posix()] = archive.read(item)
    verify_files(files)
    return files


def verify_package(path, marketplace=False):
    if marketplace and Path(path).stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValueError('Marketplace ZIP exceeds 16 MiB')
    return verify_files(read_package(path))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path)
    parser.add_argument('--marketplace', action='store_true',
                        help='Also enforce the marketplace 16 MiB limit')
    args = parser.parse_args()
    manifest = verify_package(args.package, marketplace=args.marketplace)
    print(f"Verified astrbot {manifest['version']}: "
          f"{len(manifest['files'])} files")


if __name__ == '__main__':
    main()
