"""从 service 仓库下载原版小赖字体，校验后原子写入本地缓存。"""

import hashlib
from importlib import resources
import json
from pathlib import Path
import tempfile
from zipfile import ZipFile

from .bundle import _LOCK, _copy_remote, validate_options


FONT_NAME = "Xiaolai-Regular.ttf"
FILES = {
    FONT_NAME: (
        22220806,
        "e2f68daf0e72777a8cf58bc83de1b98634b251e537ddbfca24b0ae50d1802da2",
    ),
    "OFL-Xiaolai.txt": (
        4432,
        "0df7e09be4c2c850a48bd8beb9cd64b343aad49cd5d3f6cfb2ad2e3d28a56ca4",
    ),
}


def expected_manifest():
    return json.loads(resources.files(__package__).joinpath(
        "data", "font-manifest.json",
    ).read_bytes())


def _valid(path, size, digest):
    if not path.is_file() or path.stat().st_size != size:
        return False
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            checksum.update(chunk)
    return checksum.hexdigest() == digest


def _atomic_write(path, content):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent, suffix=".download", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(content)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def ensure_font(data_dir, source="Github", service_url=""):
    """校验全部缓存文件；无效时下载，始终同时保留完整 OFL 许可。"""
    validate_options(source, service_url)
    manifest = expected_manifest()
    root = Path(data_dir) / "fonts" / manifest["sha256"]
    with _LOCK:
        if all(_valid(root / name, *checks)
               for name, checks in FILES.items()):
            return root / FONT_NAME
        root.mkdir(parents=True, exist_ok=True)
        archive_path = root / "assets.zip"
        if not _valid(archive_path, manifest["size_bytes"],
                      manifest["sha256"]):
            url = (
                service_url.rstrip("/") + "/v1/fonts/"
                + manifest["sha256"] + "/assets.zip"
                if source == "farm_service"
                else manifest["sources"][source.lower()]
            )
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(
                    dir=root, suffix=".download", delete=False,
                ) as stream:
                    temporary = Path(stream.name)
                    _copy_remote(url, stream, manifest["size_bytes"])
                if not _valid(temporary, manifest["size_bytes"],
                              manifest["sha256"]):
                    raise ValueError("Font archive size or SHA256 mismatch")
                temporary.replace(archive_path)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
        with ZipFile(archive_path) as archive:
            entries = archive.infolist()
            if (len(entries) != len(FILES)
                    or {item.filename for item in entries} != set(FILES)):
                raise ValueError("Unexpected font archive contents")
            content = {}
            for item in entries:
                size, digest = FILES[item.filename]
                if item.file_size != size or item.flag_bits & 1:
                    raise ValueError("Invalid font archive member")
                value = archive.read(item)
                if hashlib.sha256(value).hexdigest() != digest:
                    raise ValueError("Font member SHA256 mismatch")
                content[item.filename] = value
        # 先写许可，再使字体可用；不使用 extractall 或远端提供的路径。
        for name in ("OFL-Xiaolai.txt", FONT_NAME):
            _atomic_write(root / name, content[name])
        return root / FONT_NAME
