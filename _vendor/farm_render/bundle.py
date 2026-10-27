"""固定摘要的外部素材缓存；下载后校验，原子替换，不解压到磁盘。"""

import hashlib
from importlib import resources
import json
import logging
from pathlib import Path
import tempfile
import threading
import time
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from zipfile import ZipFile

logger = logging.getLogger(__name__)
_LOCK = threading.Lock()
SOURCES = ('Github', 'Gitea', 'farm_service')
MAX_BYTES = 64 * 1024 * 1024


def expected_manifest():
    return json.loads(resources.files(__package__).joinpath(
        'data', 'asset-manifest.json',
    ).read_bytes())


def validate_options(source, service_url):
    if source not in SOURCES:
        raise ValueError('Unknown resource source')
    if service_url:
        checked_url(service_url)
    if source == 'farm_service' and not service_url:
        raise ValueError('farm_service address required')


def checked_url(url):
    parsed = urlsplit(url)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username
            or parsed.password or parsed.query or parsed.fragment):
        raise ValueError('Resource URL requires HTTPS without credentials')
    return url


def _copy_remote(url, destination, limit):
    request = Request(checked_url(url), headers={'User-Agent': 'Farm-assets/1'})
    started = time.monotonic()
    with urlopen(request, timeout=15) as response:
        checked_url(response.geturl())
        length = response.headers.get('Content-Length')
        if length is not None and int(length) > limit:
            raise ValueError('Resource download exceeds limit')
        total = 0
        while True:
            chunk = response.read(min(65536, limit-total+1))
            if not chunk:
                break
            total += len(chunk)
            if total > limit or time.monotonic()-started > 60:
                raise ValueError('Resource download limit or timeout')
            destination.write(chunk)


def verify_bundle(path, manifest):
    path = Path(path)
    if (not path.is_file() or path.stat().st_size != manifest['size_bytes']
            or not 0 < manifest['size_bytes'] <= MAX_BYTES):
        raise ValueError('Resource size mismatch')
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(65536), b''):
            digest.update(chunk)
    if digest.hexdigest() != manifest['sha256']:
        raise ValueError('Resource SHA256 mismatch')
    metadata = json.loads(resources.files(__package__).joinpath(
        'data', 'metadata.json',
    ).read_bytes())
    with ZipFile(path) as archive:
        entries = archive.infolist()
        names = [item.filename for item in entries]
        if (len(names) != len(set(names))
                or set(names) != set(metadata['images'])
                or sum(item.file_size for item in entries) > 256*1024*1024
                or any(item.is_dir() or item.flag_bits & 1
                       for item in entries)):
            raise ValueError('Resource contents mismatch')
    return path


def ensure_assets(data_dir, source='Github', service_url=''):
    """每次启动校验缓存；仅缺失或不匹配时访问所选源。"""
    validate_options(source, service_url)
    expected = expected_manifest()
    target = (Path(data_dir) / 'assets' / expected['sha256'] / 'assets.zip')
    with _LOCK:
        try:
            return verify_bundle(target, expected)
        except (OSError, ValueError):
            pass
        target.parent.mkdir(parents=True, exist_ok=True)
        # 清单绑定在插件内；远端不能通过更换清单放行不兼容的素材。
        if source == 'farm_service':
            if 'catalogue_release' in expected:
                url = (service_url.rstrip('/') + '/v1/catalogue/releases/'
                       + expected['catalogue_release'] + '/assets.zip')
            else:
                url = (service_url.rstrip('/') + '/v1/assets/'
                       + expected['sha256'] + '/assets.zip')
        else:
            url = expected['sources'][source.lower()]
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=target.parent, suffix='.download', delete=False,
            ) as stream:
                temporary = Path(stream.name)
                _copy_remote(url, stream, expected['size_bytes'])
            verify_bundle(temporary, expected)
            temporary.replace(target)
            logger.info('farm assets ready source=%s sha256=%s',
                        source, expected['sha256'])
            return target
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
