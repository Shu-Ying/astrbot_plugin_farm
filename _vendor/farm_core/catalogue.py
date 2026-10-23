"""只读、离线作物目录加载。"""

from importlib import resources
import json
from types import MappingProxyType

from .domain import FarmError, Plant, text


class Catalogue:
    def __init__(self, plants):
        items = tuple(plants)
        if not items or any(not isinstance(p, Plant) for p in items):
            raise FarmError("invalid_catalogue")
        if len({p.plant_id for p in items}) != len(items):
            raise FarmError("duplicate_plant")
        self._plants = MappingProxyType({p.plant_id: p for p in items})
        names = {}
        for plant in items:
            names.setdefault(plant.name, []).append(plant)
        self._names = MappingProxyType({k: tuple(v) for k, v in names.items()})

    def get(self, name: str) -> Plant:
        text(name)
        if name.startswith("#") and name[1:].isascii() and name[1:].isdigit():
            return self.get_by_id(int(name[1:]))
        matches = self._names.get(name, ())
        if not matches:
            raise FarmError("unknown_plant")
        if len(matches) != 1:
            raise FarmError("ambiguous_plant")
        return matches[0]

    def get_by_id(self, plant_id: int) -> Plant:
        if type(plant_id) is not int or plant_id not in self._plants:
            raise FarmError("unknown_plant")
        return self._plants[plant_id]

    def __iter__(self):
        return iter(self._plants.values())

    def __len__(self):
        return len(self._plants)

    @classmethod
    def loads(cls, content: str | bytes) -> "Catalogue":
        try:
            data = json.loads(content)
            if type(data["schema"]) is not int or data["schema"] != 1:
                raise FarmError("invalid_catalogue")
            if not isinstance(data["plants"], list):
                raise FarmError("invalid_catalogue")
            return cls(Plant.from_legacy(row) for row in data["plants"])
        except (KeyError, TypeError, ValueError, UnicodeError) as exc:
            raise FarmError("invalid_catalogue") from exc

    @classmethod
    def bundled(cls) -> "Catalogue":
        content = resources.files(__package__).joinpath(
            "data", "plants.json"
        ).read_bytes()
        return cls.loads(content)
