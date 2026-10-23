"""包内素材与有界 LRU；不下载、不解压到磁盘、不暴露共享图片。"""

from collections import OrderedDict
from importlib import resources
from io import BytesIO
import json
from threading import RLock
from zipfile import ZipFile

from PIL import Image


class ByteLRU:
    def __init__(self, limit):
        if type(limit) is not int or limit < 0:
            raise ValueError("Invalid cache budget")
        self.limit = limit
        self.used_bytes = 0
        self._items = OrderedDict()
        self._lock = RLock()

    def get(self, key):
        with self._lock:
            item = self._items.get(key)
            if item is None:
                return None
            self._items.move_to_end(key)
            return item[0]

    def put(self, key, value, size):
        with self._lock:
            old = self._items.pop(key, None)
            if old is not None:
                self.used_bytes -= old[1]
            if size > self.limit or self.limit == 0:
                return
            while self._items and self.used_bytes + size > self.limit:
                _, (_, removed) = self._items.popitem(last=False)
                self.used_bytes -= removed
            self._items[key] = (value, size)
            self.used_bytes += size


class Assets:
    def __init__(self, cache_bytes=32 * 1024 * 1024, bundle_path=None):
        data = resources.files(__package__).joinpath("data")
        self.metadata = json.loads(data.joinpath("metadata.json").read_bytes())
        self.cache = ByteLRU(cache_bytes)
        self._bundle = (bundle_path if bundle_path is not None
                        else data.joinpath('assets.zip'))

    def image(self, name, size=None):
        if name not in self.metadata["images"]:
            raise KeyError("Unknown packaged image")
        size = tuple(size or self.metadata["images"][name]["size"])
        key = (name, size)
        cached = self.cache.get(key)
        if cached is None:
            with self._bundle.open("rb") as stream, ZipFile(stream) as bundle:
                content = bundle.read(name)
            with Image.open(BytesIO(content)) as original:
                original.thumbnail(size, Image.Resampling.LANCZOS)
                cached = original.convert("RGBA")
                if cached.size != size:
                    cached = cached.resize(size, Image.Resampling.LANCZOS)
            self.cache.put(key, cached, size[0] * size[1] * 4)
        return cached.copy()
