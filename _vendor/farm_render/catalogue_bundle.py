"""启动时选择完整作物版本；网络失败保留已验证缓存或初始目录。"""

import tempfile
import threading
import uuid
from dataclasses import dataclass, replace
from importlib import resources
from io import BytesIO
from pathlib import Path
from zipfile import BadZipFile

from astrbot.api import logger

from ..farm_core.catalogue_release import (
    FILES,
    MANIFEST_LIMIT,
    ROOTS,
    canonical,
    check_file,
    decode,
    load_catalogue,
    parse_manifest,
)
from ..farm_core.domain import FarmError
from ..farm_core.release_lock import release_lock
from .bundle import _copy_remote, validate_options
from .release_validation import validate_archive, validate_metadata

_LOCK = threading.RLock()
_FAILURES = (OSError, ValueError, FarmError, EOFError, BadZipFile)


@dataclass(frozen=True)
class ReleaseSnapshot:
    catalogue: object  # 完整且已校验的离线业务目录。
    metadata: dict  # 与目录和图片绑定的展示配置。
    bundle_path: Path | None  # 无图片缓存的离线初始启动可为空。
    soils_path: Path  # 小型升级土地资源所在路径。
    manifest: dict  # 本次采用的发布版本和四文件摘要。
    origin: str  # remote、cache或bootstrap，仅用于安全日志。


def _fetch(url, limit):
    output = BytesIO()
    _copy_remote(url, output, limit)
    return output.getvalue()


def _read(path, limit):
    with path.open("rb") as stream:
        content = stream.read(limit + 1)
    if len(content) > limit:
        raise ValueError("Catalogue file exceeds limit")
    return content


def _atomic(path, content):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent, suffix=".download", delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(content)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _validate(content, manifest, previous, required_ids):
    for name, value in content.items():
        check_file(value, manifest["files"][name])
    catalogue = load_catalogue(content["plants.json"], previous, required_ids)
    metadata = validate_metadata(content["metadata.json"], catalogue)
    for row in decode(content["plants.json"])["plants"]:
        info = metadata["plants"][row["name"]]
        if info["phase"] != row["phase"] or info.get("general") != row.get(
            "general"
        ):
            raise ValueError("Catalogue and render growth definitions differ")
    if "assets.zip" in content:
        validate_archive(content["assets.zip"], metadata["images"])
    validate_archive(content["land-soils.zip"])
    return catalogue, metadata


def _snapshot(root, manifest, previous=None, required_ids=(), origin="cache"):
    content = {
        name: _read(root / name, checks["size_bytes"])
        for name, checks in manifest["files"].items()
    }
    catalogue, metadata = _validate(
        content,
        manifest,
        previous,
        required_ids,
    )
    return ReleaseSnapshot(
        catalogue,
        metadata,
        root / "assets.zip",
        root / "land-soils.zip",
        manifest,
        origin,
    )


def _bootstrap(required_ids=()):
    core_name = (
        "farm_core"
        if __package__ == "farm_render"
        else __package__.rsplit(".", 1)[0] + ".farm_core"
    )
    core = resources.files(core_name).joinpath("data")
    render = resources.files(__package__).joinpath("data")
    manifest = parse_manifest(
        core.joinpath(
            "catalogue-manifest.json",
        ).read_bytes()
    )
    content = {
        "plants.json": core.joinpath("plants.json").read_bytes(),
        "metadata.json": render.joinpath("metadata.json").read_bytes(),
        "land-soils.zip": render.joinpath("land-soils.zip").read_bytes(),
    }
    catalogue, metadata = _validate(content, manifest, None, required_ids)
    return ReleaseSnapshot(
        catalogue,
        metadata,
        None,
        Path(str(render.joinpath("land-soils.zip"))),
        manifest,
        "bootstrap",
    )


def load_catalogue_release(
    data_dir, source="Github", service_url="", required_ids=()
):
    """每次调用只检查一次最新版本；调用方仅在启动时调用。"""
    validate_options(source, service_url)
    base = (
        service_url.rstrip("/") + "/v1/catalogue"
        if source == "farm_service"
        else ROOTS[source]
    )
    root = Path(data_dir) / "catalogue"
    root.mkdir(parents=True, exist_ok=True)
    with _LOCK, release_lock(root / ".cache.lock"):
        releases = root / "releases"
        releases.mkdir(exist_ok=True)
        bootstrap = _bootstrap()
        current = None
        try:
            manifest = parse_manifest(
                _read(root / "current.json", MANIFEST_LIMIT)
            )
            current = _snapshot(
                releases / manifest["release"],
                manifest,
                bootstrap.catalogue,
            )
        except _FAILURES:
            pass
        previous = (current or bootstrap).catalogue
        try:
            manifest = parse_manifest(
                _fetch(
                    base + "/manifest.json",
                    MANIFEST_LIMIT,
                )
            )
            target = releases / manifest["release"]
            if (
                current is not None
                and current.manifest["release"] == manifest["release"]
            ):
                if not set(required_ids).issubset(
                    plant.plant_id for plant in current.catalogue
                ):
                    raise ValueError("catalogue missing player crop ID")
                logger.info("农场作物版本未变化：复用已校验缓存")
                return replace(current, origin="remote")
            try:
                candidate = _snapshot(
                    target, manifest, previous, required_ids, "remote"
                )
            except _FAILURES:
                with tempfile.TemporaryDirectory(
                    dir=releases, prefix=".download-"
                ) as temporary:
                    staging = Path(temporary)
                    for name, item in manifest["files"].items():
                        content = _fetch(
                            base
                            + "/releases/"
                            + manifest["release"]
                            + "/"
                            + name,
                            item["size_bytes"],
                        )
                        check_file(content, item)
                        (staging / name).write_bytes(content)
                    _snapshot(staging, manifest, previous, required_ids)
                    if target.exists():
                        try:
                            _snapshot(target, manifest, previous, required_ids)
                        except _FAILURES:
                            target.rename(
                                releases / (".invalid-" + uuid.uuid4().hex)
                            )
                    if not target.exists():
                        try:
                            staging.rename(target)
                        except OSError:
                            if not target.exists():
                                raise
                    candidate = _snapshot(
                        target, manifest, previous, required_ids, "remote"
                    )
            previous_images = (current or bootstrap).metadata["images"]
            if not set(previous_images).issubset(candidate.metadata["images"]):
                raise ValueError("Catalogue removed existing image paths")
            logger.info("农场作物列表、配置和素材校验通过：正在切换版本")
            _atomic(root / "current.json", canonical(manifest))
            logger.info(
                "farm catalogue ready release=%s source=%s",
                manifest["release"],
                source,
            )
            return candidate
        except _FAILURES as error:
            logger.warning(
                "farm catalogue update unavailable source=%s "
                "reason=%s; keeping verified fallback",
                source,
                type(error).__name__,
            )
        if current is not None:
            if not set(required_ids).issubset(
                plant.plant_id for plant in current.catalogue
            ):
                raise ValueError("catalogue missing player crop ID")
            logger.info("农场更新不可用：使用已校验的作物缓存版本")
            return current
        bootstrap = _bootstrap(required_ids)
        logger.info("农场更新不可用：使用内置作物版本")
        # 若旧方式图片缓存可用，离线初始版本也能继续绘图。
        cached = (
            Path(data_dir)
            / "assets"
            / bootstrap.manifest["files"]["assets.zip"]["sha256"]
            / "assets.zip"
        )
        try:
            content = _read(cached, FILES["assets.zip"])
            check_file(content, bootstrap.manifest["files"]["assets.zip"])
            validate_archive(content, bootstrap.metadata["images"])
            bootstrap = replace(bootstrap, bundle_path=cached)
        except _FAILURES:
            pass
        return bootstrap
