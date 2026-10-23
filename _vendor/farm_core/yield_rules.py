"""本季产量的唯一口径：土地加成、成熟虫害、实际偷取扣减。"""

from .domain import boosted


def season_yield(plot):
    return (boosted(plot.plant.harvest, plot.yield_bonus)
            * (100-5*plot.maturity_pests)//100)


def remaining_yield(plot):
    return max(0, season_yield(plot)-plot.stolen_count)
