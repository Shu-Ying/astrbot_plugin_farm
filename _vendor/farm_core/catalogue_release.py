"""作物发布协议的纯离线校验；不联网、不依赖绘图库。"""

import hashlib
import json
import re

from .catalogue import Catalogue

FILES = {
    'plants.json': 2 * 1024 * 1024,
    'metadata.json': 4 * 1024 * 1024,
    'assets.zip': 64 * 1024 * 1024,
    'land-soils.zip': 64 * 1024 * 1024,
}
MANIFEST_LIMIT = 16 * 1024
DIGEST = re.compile(r'[0-9a-f]{64}')
VERSION = re.compile(r'[A-Za-z0-9._-]{1,64}')
ROOTS = {
    'Github': 'https://raw.githubusercontent.com/Shu-Ying/'
              'farm_service/main/catalogue',
    'Gitea': 'https://gitea.diuse.work/Diuse/farm_service/'
             'raw/branch/main/catalogue',
}


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError('Duplicate JSON key')
        result[key] = value
    return result


def decode(content):
    def invalid(_value):
        raise ValueError('Non-finite JSON value')
    try:
        return json.loads(content, object_pairs_hook=_pairs,
                          parse_constant=invalid)
    except (UnicodeError, TypeError, RecursionError) as error:
        raise ValueError('Invalid release JSON') from error


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':'), allow_nan=False).encode()


def digest(content):
    return hashlib.sha256(content).hexdigest()


def make_manifest(files, version):
    descriptors = {
        name: {'size_bytes': len(content), 'sha256': digest(content)}
        for name, content in files.items()
    }
    result = {'schema': 1, 'version': version,
              'release': digest(canonical(descriptors)), 'files': descriptors}
    return parse_manifest(canonical(result))


def parse_manifest(content):
    if len(content) > MANIFEST_LIMIT:
        raise ValueError('Catalogue manifest exceeds limit')
    value = decode(content)
    if (type(value) is not dict or set(value) != {
            'schema', 'version', 'release', 'files'}
            or type(value['schema']) is not int or value['schema'] != 1
            or not isinstance(value['version'], str)
            or VERSION.fullmatch(value['version']) is None
            or not isinstance(value['release'], str)
            or DIGEST.fullmatch(value['release']) is None
            or type(value['files']) is not dict
            or set(value['files']) != set(FILES)):
        raise ValueError('Invalid catalogue manifest')
    for name, limit in FILES.items():
        item = value['files'][name]
        if (type(item) is not dict or set(item) != {'size_bytes', 'sha256'}
                or type(item['size_bytes']) is not int
                or not 0 < item['size_bytes'] <= limit
                or not isinstance(item['sha256'], str)
                or DIGEST.fullmatch(item['sha256']) is None):
            raise ValueError('Invalid catalogue file descriptor')
    if digest(canonical(value['files'])) != value['release']:
        raise ValueError('Catalogue release fingerprint differs')
    return value


def check_file(content, descriptor):
    if (len(content) != descriptor['size_bytes']
            or digest(content) != descriptor['sha256']):
        raise ValueError('Catalogue file size or SHA256 differs')


def load_catalogue(content, previous=None, required_ids=()):
    value = decode(content)
    if (type(value) is not dict or type(value.get('plants')) is not list
            or not 0 < len(value['plants']) <= 10000):
        raise ValueError('Invalid catalogue document')
    catalogue = Catalogue.loads(content)
    names = [plant.name for plant in catalogue]
    if (len(set(names)) != len(names) or any(
            name in ('.', '..') or '/' in name or '\\' in name
            for name in names)):
        raise ValueError('Invalid or duplicate catalogue name')
    indexed = {plant.plant_id: plant for plant in catalogue}
    if not set(required_ids).issubset(indexed):
        raise ValueError('catalogue missing player crop ID')
    if previous is not None:
        for plant in previous:
            current = indexed.get(plant.plant_id)
            if current is None or current.name != plant.name:
                raise ValueError('Catalogue removed or renamed crop ID')
    return catalogue
