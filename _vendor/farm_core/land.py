"""只读取已配置的开垦条件，不推算表外费用。"""

from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
import json
from types import MappingProxyType

from .domain import FarmError, integer


SUPPORTED_PLOTS = 30  # 当前布局支持的位置数，不代表永久土地总上限。
COMPENSATION_ID = 'initial-plots-3-to-6:v1'  # 每个账号唯一的补偿操作。
LAND_NAMES = ('普通土地', '红土地', '黑土地', '金土地')
LAND_TYPES = ('normal', 'red', 'black', 'gold')


@dataclass(frozen=True)
class ExpansionRule:
    ordinal: int  # 本次开垦后新增地块的实际编号。
    required_level: int  # 开垦所需最低等级。
    coin_cost: int  # 本次扣除的农场币。


@lru_cache(maxsize=1)
def expansion_rules():
    content = resources.files(__package__).joinpath(
        'data', 'land_rules.json',
    ).read_bytes()
    try:
        data = json.loads(content)
        integer(data['initial_plot_count'], 6, 6)
        rows = data['expansion']['rows']
        if not isinstance(rows, list) or not rows:
            raise ValueError('Missing expansion rules')
        rules = {}
        for row in rows:
            rule = ExpansionRule(
                integer(row['ordinal'], 7, SUPPORTED_PLOTS),
                integer(row['required_level']), integer(row['coin_cost'], 1),
            )
            if rule.ordinal in rules:
                raise ValueError('Duplicate expansion ordinal')
            rules[rule.ordinal] = rule
        return MappingProxyType(rules)
    except (KeyError, TypeError, ValueError) as error:
        raise FarmError('land_rules_invalid') from error


def owned_count(plots):
    slots = tuple(plot.slot for plot in plots)
    if not slots or slots != tuple(range(1, len(slots) + 1)):
        raise FarmError('land_layout_invalid')
    return len(slots)


def next_rule(plots):
    count = owned_count(plots)
    rule = expansion_rules().get(count + 1)
    if rule is None:
        raise FarmError('land_rule_unavailable')
    return rule


@lru_cache(maxsize=1)
def upgrade_rules():
    data = json.loads(resources.files(__package__).joinpath(
        'data', 'land_rules.json',
    ).read_bytes())
    rules = {}
    try:
        for entry in data['upgrades']:
            level = LAND_TYPES.index(entry['land_type'])
            if level == 0 or entry['from_land_type'] != LAND_TYPES[level-1]:
                raise ValueError('Invalid upgrade chain')
            for row in entry['rows']:
                rule = ExpansionRule(
                    integer(row['ordinal'], 1, SUPPORTED_PLOTS),
                    integer(row['required_level']),
                    integer(row['coin_cost'], 1),
                )
                key = (level, rule.ordinal)
                if key in rules:
                    raise ValueError('Duplicate upgrade ordinal')
                rules[key] = rule
        return MappingProxyType(rules)
    except (KeyError, TypeError, ValueError) as error:
        raise FarmError('land_rules_invalid') from error


def upgrade_rule(plots, slot):
    integer(slot, 1, SUPPORTED_PLOTS)
    plot = next((p for p in plots if p.slot == slot), None)
    if plot is None:
        raise FarmError('unknown_plot')
    level = plot.land_level + 1
    if level >= len(LAND_TYPES):
        raise FarmError('land_max_level')
    ordinal = 1 + sum(p.land_level >= level for p in plots)
    rule = upgrade_rules().get((level, ordinal))
    if rule is None:
        raise FarmError('land_rule_unavailable')
    return plot, level, rule
