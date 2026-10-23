"""命令注册与帮助共用的声明；平台接入不维护业务帮助副本。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class CommandSpec:
    name: str  # 注册的中文主命令。
    action: str  # 共享运行时动作。
    group: str  # 帮助中的分类。
    usage: str  # 完整调用语法。
    description: str  # 用户可读的简短说明。
    aliases: tuple[str, ...] = ()  # 同一动作的中文别名。
    platforms: tuple[str, ...] = ()  # 空表示所有框架，否则仅指定框架。
    extra: tuple[tuple[str, str], ...] = ()  # 同命令的附加用法及说明。


COMMAND_SPECS = (
    CommandSpec('开通农场', 'register', '开通与查看', '开通农场 [名称]',
                '首次开通获得6块土地，可指定农场名称。'),
    CommandSpec('我的农场', 'farm', '开通与查看', '我的农场 [高清]',
                '查看农场全景；仅我的农场支持高清。'),
    CommandSpec('农场详述', 'details', '开通与查看', '农场详述 [页码]',
                '查看各地块的作物、生长和虫害信息。'),
    CommandSpec('地块编号', 'plot_ids', '开通与查看', '地块编号',
                '查看已开垦土地编号及待开垦位置。'),
    CommandSpec('我的农场币', 'inventory', '开通与查看', '我的农场币',
                '查看农场币、点券等资产。'),
    CommandSpec('我的点券', 'inventory', '开通与查看', '我的点券',
                '查看点券等资产。'),
    CommandSpec('种子商店', 'shop', '种子与种植', '种子商店 [页码]',
                '查看种子价格、等级要求与作物编号。'),
    CommandSpec('购买种子', 'buy', '种子与种植', '购买种子 作物 数量',
                '购买指定数量的种子。'),
    CommandSpec('播种', 'sow', '种子与种植', '播种 作物 [数量]',
                '使用库存种子播种到空地。'),
    CommandSpec('收获', 'harvest', '田间管理与扩建', '收获',
                '收获成熟作物，获得作物与经验。'),
    CommandSpec('农场除虫', 'clear_pests', '田间管理与扩建', '农场除虫',
                '清除虫害；生长期间及时除虫。', aliases=('除虫',)),
    CommandSpec('铲除', 'eradicate', '田间管理与扩建', '铲除',
                '清理枯萎作物，腾出土地。'),
    CommandSpec('开垦', 'reclaim', '田间管理与扩建', '开垦',
                '满足等级和费用后，新增1块普通空地。',
                extra=(('开垦 条件', '查询下一块土地的等级及费用。'),)),
    CommandSpec('我的种子', 'seeds', '仓库与出售',
                '我的种子 [页码] [文字]',
                '查看种子库存；默认图片，追加「文字」切换。'),
    CommandSpec('我的作物', 'crops', '仓库与出售',
                '我的作物 [页码] [文字]',
                '查看作物库存；默认图片，追加「文字」切换。'),
    CommandSpec('出售作物', 'sell', '仓库与出售',
                '出售作物 [作物] [数量]',
                '出售作物获得农场币；省略作物时出售全部未锁定作物。'),
    CommandSpec('作物加锁', 'lock', '仓库与出售', '作物加锁 作物',
                '锁定作物，出售时自动跳过。'),
    CommandSpec('作物解锁', 'unlock', '仓库与出售', '作物解锁 作物',
                '解除指定作物的锁定。'),
    CommandSpec('偷菜', 'steal', '好友互动', '偷菜 @目标',
                '每日最多5次成功偷取，北京时间零点重置。'),
    CommandSpec('农场帮助', 'help', '使用帮助', '农场帮助 [文字]',
                '查看当前平台菜单；追加「文字」查看文字版。'),
)

HELP_NOTES = (
    '[参数] 表示可选；作物支持名称或 #编号，同名作物请使用编号。',
    '示例：我的种子 2 文字；购买种子 #编号 5；播种 #编号 3。',
    '仅我的农场支持高清；其他图片使用统一图片质量配置。',
    '新播种及下一季每半个基础生长周期生虫一次，间隔至少2小时。',
    '每只虫降低生长速度5%；成熟时每只虫使本季减产5%。',
    '成熟后除虫不能恢复本季减产，请在生长期间及时除虫。',
    '每播种1块地或铲除1块枯萎地获得2经验；每清除1只虫获得1经验。',
    '收获经验按作物结算；农场背景按北京时间自动切换季节。',
    '旧版数据首次使用时迁移，绑定当前机器人和平台。',
)


def command_specs(platform, specs=None):
    if platform not in ('zhenxun', 'nonebot', 'astrbot'):
        raise ValueError('Unknown farm framework')
    return tuple(spec for spec in (
        COMMAND_SPECS if specs is None else specs
    ) if not spec.platforms or platform in spec.platforms)


def command_map(platform, specs=None):
    result = {}
    for spec in command_specs(platform, specs):
        for name in (spec.name, *spec.aliases):
            if name in result:
                raise ValueError('Duplicate farm command')
            result[name] = spec.action
    return result


def help_groups(specs):
    groups = {}
    for spec in specs:
        description = spec.description
        if spec.aliases:
            description += ' 别名：' + '、'.join(spec.aliases) + '。'
        groups.setdefault(spec.group, []).extend((
            (spec.usage, description), *spec.extra,
        ))
    return tuple((title, tuple(rows)) for title, rows in groups.items())


def help_text(specs):
    lines = ['农场帮助']
    for title, rows in help_groups(specs):
        lines.append('\n【' + title + '】')
        for usage, description in rows:
            lines.extend((usage, '  ' + description))
    return '\n'.join((*lines, '\n【参数与玩法】', *HELP_NOTES))
