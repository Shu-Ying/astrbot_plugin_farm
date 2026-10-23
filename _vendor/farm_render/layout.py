"""从一次快照与统一时间构造可缓存场景；不访问存储。"""

import hashlib

from ..farm_core.domain import Identity, Snapshot, integer
from ..farm_core.pests import advance_plot

from .models import PlotView, Scene


def pest_frames(scope, plot, frames):
    available = list(frames)
    chosen = []
    for index in range(plot.pest_count):
        seed = (
            f"{scope}:{plot.slot}:{plot.plant.plant_id}:"
            f"{plot.harvest_count}:{index}"
        )
        number = int.from_bytes(hashlib.sha256(seed.encode()).digest(), "big")
        chosen.append(available.pop(number % len(available)))
    return tuple(chosen)


def scene_from_snapshot(identity, snapshot, now, metadata):
    if not isinstance(identity, Identity) or not isinstance(snapshot, Snapshot):
        raise ValueError("Identity and snapshot are required")
    integer(now)
    slots = [p.slot for p in snapshot.plots]
    if len(set(slots)) != len(slots) or any(
        type(slot) is not int or not 1 <= slot <= 30 for slot in slots
    ):
        raise ValueError("Invalid plot slots")
    views = []
    scope = hashlib.sha256(identity.key.encode()).hexdigest()
    for plot in sorted(snapshot.plots, key=lambda p: p.slot):
        plot = advance_plot(plot, now)
        if plot.plant is None:
            views.append(PlotView(plot.slot, "empty"))
            continue
        if plot.withered:
            views.append(PlotView(
                plot.slot, "withered", "webgl/wither.png",
            ))
            continue
        integer(plot.mature_at)
        frames = pest_frames(scope, plot, metadata["pest"]["frames"])
        name = plot.plant.name
        info = metadata["plants"].get(name)
        if info is None:
            views.append(PlotView(
                plot.slot, "growing", "missing", pest_count=plot.pest_count,
                pest_frames=frames,
            ))
            continue
        phases = tuple(dict.fromkeys(int(p) for p in info["phase"].split(",")))
        duration = (plot.plant.growth_seconds if plot.harvest_count == 0
                    else plot.plant.regrowth_seconds)
        elapsed = max(0, now - (plot.mature_at - duration))
        work = (elapsed * 100 if plot.growth_remaining is None else
                duration * 100 - plot.growth_remaining)
        ripe = now >= plot.mature_at
        stage = len(phases) if ripe else sum(
            work * phases[-1] >= threshold * duration * 100
            for threshold in phases
        )
        sprite = f"plant/{name}/{stage}.png"
        if stage == 0:
            sprite = "webgl/seed.png"
        views.append(PlotView(
            plot.slot, "ripe" if ripe else "growing", sprite, stage,
            pest_count=plot.pest_count,
            pest_frames=frames,
        ))
    return Scene(
        scope, snapshot.account, tuple(views),
    )
