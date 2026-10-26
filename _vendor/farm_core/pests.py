"""离线虫害时间结算；只投影状态，不读写数据库或使用随机数。"""

from dataclasses import replace

from .domain import Plot, integer


def season_duration(plot: Plot) -> int:
    base = (plot.plant.growth_seconds if plot.harvest_count == 0
            else plot.plant.regrowth_seconds)
    return max(1, (base * (80 if plot.land_level >= 2 else 100) + 99) // 100)


def spawn_interval(plot: Plot) -> int:
    """至少留出两小时，每半个基础生长周期才发生一次虫害。"""
    return max(7200, (season_duration(plot) + 1) // 2)


def start_growth(plot: Plot, now: int) -> Plot:
    duration = season_duration(plot)
    return advance_plot(replace(
        plot, mature_at=integer(now + duration), pest_count=0, pest_spawned=0,
        growth_remaining=integer(duration * 100), growth_updated_at=now,
        next_pest_at=integer(now + spawn_interval(plot)), maturity_pests=0,
    ), now)


def _advance(remaining, cursor, pests, spawned, next_at, interval, now):
    while remaining:
        rate = 100 - pests * 5
        finish = integer(cursor + (remaining + rate - 1) // rate)
        if finish <= now and (next_at is None or finish <= next_at):
            return 0, finish, pests, spawned, None, finish
        end = min(now, next_at) if next_at is not None else now
        remaining -= (end - cursor) * rate
        cursor = end
        if next_at is None or cursor < next_at:
            break
        pests += 1
        spawned += 1
        next_at = integer(next_at + interval) if spawned < 3 else None
        if cursor == now:
            break
    return remaining, cursor, pests, spawned, next_at, None


def advance_plot(plot: Plot, now: int) -> Plot:
    integer(now)
    if (plot.plant is None or plot.withered
            or plot.growth_remaining is None or not plot.growth_remaining):
        return plot
    if now < plot.growth_updated_at:
        return plot
    interval = spawn_interval(plot)
    remaining, cursor, pests, spawned, next_at, finish = _advance(
        plot.growth_remaining, plot.growth_updated_at, plot.pest_count,
        plot.pest_spawned, plot.next_pest_at, interval, now,
    )
    if finish is None:
        finish = _advance(
            remaining, cursor, pests, spawned, next_at, interval,
            integer(cursor + (remaining + 84) // 85),
        )[-1]
    return replace(
        plot, mature_at=finish, pest_count=pests, pest_spawned=spawned,
        growth_remaining=remaining, growth_updated_at=cursor,
        next_pest_at=next_at,
        maturity_pests=pests if remaining == 0 else 0,
    )
