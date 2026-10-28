"""固定摘要的外部素材缓存；下载后校验，原子替换，不解压到磁盘。"""

import hashlib
import json
import sys
import tempfile
import threading
import time
from importlib import resources
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from zipfile import ZipFile

from astrbot.api import logger

_LOCK = threading.Lock()
SOURCES = ("Github", "Gitea", "farm_service")
MAX_BYTES = 64 * 1024 * 1024


def expected_manifest():
    return json.loads(
        resources.files(__package__)
        .joinpath(
            "data",
            "asset-manifest.json",
        )
        .read_bytes()
    )


def validate_options(source, service_url):
    if source not in SOURCES:
        raise ValueError("Unknown resource source")
    if service_url:
        checked_url(service_url)
    if source == "farm_service" and not service_url:
        raise ValueError("farm_service address required")


def checked_url(url):
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Resource URL requires HTTPS without credentials")
    return url


class _DownloadProgress:
    """仅在交互终端原位刷新；重定向输出不写控制字符。"""

    def __init__(self, name):
        self.name = name
        self.stream = sys.stderr
        self.enabled = bool(getattr(self.stream, "isatty", lambda: False)())
        self.last_report = float("-inf")
        self.progress = None
        self.task = None

    def update(self, total, length, now, *, force=False):
        if not self.enabled or (not force and now - self.last_report < 0.2):
            return
        try:
            if self.progress is None:
                from rich.console import Console
                from rich.progress import (
                    BarColumn,
                    DownloadColumn,
                    Progress,
                    TextColumn,
                    TimeRemainingColumn,
                    TransferSpeedColumn,
                )

                console = Console(file=self.stream)
                if not console.is_terminal:
                    self.enabled = False
                    return
                self.progress = Progress(
                    TextColumn("{task.description}", markup=False),
                    BarColumn(bar_width=None),
                    TextColumn("{task.fields[percentage]}"),
                    DownloadColumn(),
                    TransferSpeedColumn(),
                    TextColumn("eta"),
                    TimeRemainingColumn(),
                    console=console,
                    auto_refresh=False,
                    expand=True,
                    redirect_stdout=False,
                    redirect_stderr=False,
                )
                self.task = self.progress.add_task(
                    f"[农场] {self.name}",
                    total=length if length > 0 else None,
                    percentage="",
                )
                self.progress.start()
            percentage = f"{min(1, total / length):.1%}" if length > 0 else ""
            self.progress.update(
                self.task, completed=total, percentage=percentage
            )
            self.progress.refresh()
        except Exception:
            # 终端或显示库故障不影响资源下载，也不接管宿主输出流。
            self.close()
            self.enabled = False
        self.last_report = now

    def close(self):
        progress, self.progress = self.progress, None
        self.task = None
        if progress is not None:
            try:
                progress.stop()
            except Exception:
                pass


def _copy_remote(url, destination, limit):
    request = Request(checked_url(url), headers={"User-Agent": "Farm-assets/1"})
    parts = urlsplit(url).path.split("/")
    name = {
        "manifest.json": "作物版本清单",
        "plants.json": "作物列表",
        "metadata.json": "展示配置",
        "land-soils.zip": "土地素材",
        "assets.zip": "字体包" if "fonts" in parts else "图片素材包",
    }.get(parts[-1], "资源")
    started = time.monotonic()
    progress = _DownloadProgress(name)
    logger.info("农场下载开始：%s", name)
    try:
        with urlopen(request, timeout=15) as response:
            checked_url(response.geturl())
            header = response.headers.get("Content-Length")
            length = int(header) if header is not None else 0
            if length > limit:
                raise ValueError("Resource download exceeds limit")
            total = 0
            progress.update(total, length, started)
            while True:
                chunk = response.read(min(65536, limit - total + 1))
                if not chunk:
                    break
                total += len(chunk)
                now = time.monotonic()
                if total > limit or now - started > 60:
                    raise ValueError("Resource download limit or timeout")
                destination.write(chunk)
                progress.update(total, length, now)
            progress.update(total, length, started, force=True)
        progress.close()
        logger.info(
            "农场下载完成：%s 共 %.2f MiB（待校验）", name, total / 1048576
        )
    except Exception as error:
        progress.close()
        logger.warning("农场下载失败：%s（%s）", name, type(error).__name__)
        raise


def verify_bundle(path, manifest):
    path = Path(path)
    if (
        not path.is_file()
        or path.stat().st_size != manifest["size_bytes"]
        or not 0 < manifest["size_bytes"] <= MAX_BYTES
    ):
        raise ValueError("Resource size mismatch")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    if digest.hexdigest() != manifest["sha256"]:
        raise ValueError("Resource SHA256 mismatch")
    metadata = json.loads(
        resources.files(__package__)
        .joinpath(
            "data",
            "metadata.json",
        )
        .read_bytes()
    )
    with ZipFile(path) as archive:
        entries = archive.infolist()
        names = [item.filename for item in entries]
        if (
            len(names) != len(set(names))
            or set(names) != set(metadata["images"])
            or sum(item.file_size for item in entries) > 256 * 1024 * 1024
            or any(item.is_dir() or item.flag_bits & 1 for item in entries)
        ):
            raise ValueError("Resource contents mismatch")
    return path


def ensure_assets(data_dir, source="Github", service_url=""):
    """每次启动校验缓存；仅缺失或不匹配时访问所选源。"""
    validate_options(source, service_url)
    expected = expected_manifest()
    target = Path(data_dir) / "assets" / expected["sha256"] / "assets.zip"
    with _LOCK:
        try:
            cached = verify_bundle(target, expected)
            logger.info("农场图片素材：复用已校验缓存")
            return cached
        except (OSError, ValueError):
            pass
        target.parent.mkdir(parents=True, exist_ok=True)
        # 清单绑定在插件内；远端不能通过更换清单放行不兼容的素材。
        if source == "farm_service":
            if "catalogue_release" in expected:
                url = (
                    service_url.rstrip("/")
                    + "/v1/catalogue/releases/"
                    + expected["catalogue_release"]
                    + "/assets.zip"
                )
            else:
                url = (
                    service_url.rstrip("/")
                    + "/v1/assets/"
                    + expected["sha256"]
                    + "/assets.zip"
                )
        else:
            url = expected["sources"][source.lower()]
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=target.parent,
                suffix=".download",
                delete=False,
            ) as stream:
                temporary = Path(stream.name)
                _copy_remote(url, stream, expected["size_bytes"])
            verify_bundle(temporary, expected)
            temporary.replace(target)
            logger.info(
                "farm assets ready source=%s sha256=%s",
                source,
                expected["sha256"],
            )
            return target
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
