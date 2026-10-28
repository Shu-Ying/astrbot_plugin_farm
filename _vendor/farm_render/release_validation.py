"""校验同版本展示配置及ZIP图片，不将不可信路径解压到磁盘。"""

import math
from io import BytesIO
from pathlib import PurePosixPath
from zipfile import ZipFile

from PIL import Image

from ..farm_core.catalogue_release import decode, digest


def _numbers(values, length):
    if (
        type(values) is not list
        or len(values) != length
        or any(
            type(v) not in (int, float)
            or abs(v) > 10000000
            or not math.isfinite(v)
            for v in values
        )
    ):
        raise ValueError("Invalid render coordinates")
    return values


def _size(values):
    _numbers(values, 2)
    if (
        any(type(v) is not int or not 0 < v <= 8192 for v in values)
        or values[0] * values[1] > 32 * 1024 * 1024
    ):
        raise ValueError("Invalid image dimensions")


def _rect(values):
    _numbers(values, 4)
    if values[2] <= 0 or values[3] <= 0:
        raise ValueError("Invalid render rectangle")


def safe_member(name):
    if (
        not isinstance(name, str)
        or not name
        or len(name) > 512
        or "\\" in name
        or ":" in name
    ):
        raise ValueError("Invalid image path")
    path = PurePosixPath(name)
    if path.is_absolute() or any(p in ("", ".", "..") for p in name.split("/")):
        raise ValueError("Invalid image path")


def validate_metadata(content, catalogue):
    value = decode(content)
    try:
        if type(value["schema"]) is not int or value["schema"] != 1:
            raise ValueError("Unknown render metadata schema")
        _size(value["canvas"])
        _size(value["soil_size"])
        if len(value["positions"]) != 30:
            raise ValueError("Expected 30 plot positions")
        for pos in value["positions"]:
            _numbers([pos["x"], pos["y"]], 2)
        images = value["images"]
        if not isinstance(images, dict) or not 0 < len(images) <= 10000:
            raise ValueError("Invalid image manifest")
        for name, item in images.items():
            safe_member(name)
            _size(item["size"])
            if (
                not isinstance(item["sha256"], str)
                or len(item["sha256"]) != 64
                or any(c not in "0123456789abcdef" for c in item["sha256"])
            ):
                raise ValueError("Invalid image checksum")
        plants = value["plants"]
        if set(plants) != {plant.name for plant in catalogue}:
            raise ValueError("Catalogue and render plants differ")
        for plant in catalogue:
            phases = plants[plant.name]["phase"].split(",")
            numbers = list(dict.fromkeys(int(v) for v in phases))
            if (
                len(numbers) < 2
                or min(numbers) <= 0
                or numbers != sorted(numbers)
            ):
                raise ValueError("Invalid render growth phases")
        placement = value["placement"]
        if (
            type(placement["schema"]) is not int
            or placement["schema"] != 4
            or placement["mode"] != "visible_contact_center"
        ):
            raise ValueError("Unknown crop placement")
        for key in (
            "common_scale",
            "growth_scale",
            "reference_soil_height",
            "reference_soil_width",
        ):
            _numbers([placement[key]], 1)
            if placement[key] <= 0:
                raise ValueError("Invalid crop scale")
        _numbers([placement["contact_alpha_threshold"]], 1)
        _numbers([placement["contact_band_fraction"]], 1)
        if (
            not 0 <= placement["contact_alpha_threshold"] <= 255
            or not 0 < placement["contact_band_fraction"] <= 1
        ):
            raise ValueError("Invalid ground contact rule")
        matrix = placement["scene_transform"]
        if len(matrix) != 2:
            raise ValueError("Invalid scene transform")
        a, b = _numbers(matrix[0], 2)
        c, d = _numbers(matrix[1], 2)
        if abs(a * d - b * c) < 1e-8:
            raise ValueError("Degenerate scene transform")
        pest = value["pest"]
        _size(pest["display_size"])
        if len(pest["frames"]) < 3 or len(set(pest["frames"])) != len(
            pest["frames"]
        ):
            raise ValueError("Invalid pest frames")
        for name in pest["frames"]:
            if name not in images:
                raise ValueError("Missing pest image")
        if len(pest["positions"]) < 3:
            raise ValueError("Missing pest positions")
        for pos in pest["positions"]:
            _numbers(pos, 2)
        panel = value["panel"]
        _size(panel["reference_canvas"])
        _rect(panel["avatar"])
        fields = {"name", "experience", "level", "point", "vip_point"}
        if {entry["field"] for entry in panel["fields"]} != fields:
            raise ValueError("Invalid panel fields")
        for entry in panel["fields"]:
            _rect(entry["rect"])
            _numbers(entry["color"], 3)
            if any(not 0 <= v <= 255 for v in entry["color"]) or entry[
                "alignment"
            ] not in (3, 4):
                raise ValueError("Invalid panel text")
        for entry in panel["sprites"]:
            _rect(entry["rect"])
            if entry["sprite"] not in images:
                raise ValueError("Missing panel sprite")
        if set(value["decorations"]) != {
            "default",
            "spring",
            "summer",
            "autumn",
            "winter",
            "bee",
        }:
            raise ValueError("Invalid decoration themes")
        for entries in value["decorations"].values():
            for entry in entries:
                _numbers(entry["position"], 2)
                _numbers(entry["size"], 2)
                if (
                    min(entry["size"]) <= 0
                    or entry["layer"] not in ("background", "foreground")
                    or entry["sprite"] not in images
                ):
                    raise ValueError("Invalid decoration")
        for name in (
            "webgl/seed.png",
            "webgl/wither.png",
            "background/ripe.png",
            "soil/草土地.png",
            "soil/普通土地.png",
        ):
            if name not in images:
                raise ValueError("Missing required farm sprite")
        return value
    except (KeyError, TypeError, IndexError, AttributeError) as error:
        raise ValueError("Invalid render metadata") from error


def validate_archive(content, images=None):
    with ZipFile(BytesIO(content)) as archive:
        entries = archive.infolist()
        names = [entry.filename for entry in entries]
        expected = (
            set(images)
            if images is not None
            else {
                "soil/红土地.png",
                "soil/黑土地.png",
                "soil/金土地.png",
            }
        )
        if (
            len(names) != len(set(names))
            or set(names) != expected
            or sum(e.file_size for e in entries) > 256 * 1024 * 1024
        ):
            raise ValueError("Unexpected release ZIP contents")
        for entry in entries:
            safe_member(entry.filename)
            if (
                entry.is_dir()
                or entry.flag_bits & 1
                or entry.file_size > 32 * 1024 * 1024
                or (entry.external_attr >> 16) & 0o170000 == 0o120000
            ):
                raise ValueError("Invalid release ZIP member")
            data = archive.read(entry)
            expected_image = images[entry.filename] if images else None
            if (
                expected_image is not None
                and digest(data) != expected_image["sha256"]
            ):
                raise ValueError("Release image checksum differs")
            with Image.open(BytesIO(data)) as image:
                _size(list(image.size))
                if (
                    expected_image is not None
                    and list(image.size) != expected_image["size"]
                ):
                    raise ValueError("Release image dimensions differ")
                image.verify()
