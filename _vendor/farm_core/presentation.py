"""仅渲染已提交结果，不发送框架消息或修改业务状态。"""

from .domain import Receipt, Snapshot


def receipt_text(receipt: Receipt) -> str:
    if receipt.action == 'steal':
        data = receipt.data
        items = data['items']
        lines = [f"偷菜成功：{len(items)}块地，共{data['quantity']}个。"
                 if items else '本次未偷到作物，不消耗次数。']
        grouped = {}
        for item in items:
            key = (item['plant_id'], item['name'])
            grouped[key] = grouped.get(key, 0)+item['quantity']
        lines.extend(f'{name}（#{pid}）×{amount}'
                     for (pid, name), amount in grouped.items())
        reasons = {'already_stolen': '本季已偷过',
                   'protected': '防偷保护', 'not_ripe': '无成熟作物'}
        notes = [f'{reasons[key]} {count}块'
                 for key, count in data['skipped'].items() if count]
        if notes:
            lines.append('跳过：'+'；'.join(notes))
        lines.append(f"今日剩余：{data['remaining_attempts']}/5次（北京时间）")
        return '\n'.join(lines)
    labels = {
        "register": "注册", "buy": "购买", "sow": "播种",
        "harvest": "收获", "eradicate": "铲除",
        "lock": "锁定设置", "sell": "出售",
        "clear_pests": "除虫", "reclaim": "开垦",
    }
    data = receipt.data
    account = data["account"]
    lines = [f"{labels[receipt.action]}已完成"]
    if "created" in data:
        lines.append("首次开通" if data["created"] else "农场已存在")
    if "quantity" in data:
        lines.append(f"实际数量：{data['quantity']}")
    if "proceeds" in data:
        lines.append(f"本次收入：{data['proceeds']}")
    if "experience" in data:
        lines.append(f"本次经验：+{data['experience']}")
    if receipt.action == 'reclaim':
        lines.append(f"新增地块：{data['slot']}号普通空地")
        lines.append(f"本次消耗：{data['cost']}农场币")
        lines.append(f"当前土地：{data['plot_count']}块")
    for item in data.get("harvested", ()):
        if item.get("yield_loss_percent", 0):
            lines.append(
                f"地块{item['slot']}：成熟时虫子{item['pests']}只，"
                f"本季减产{item['yield_loss_percent']}%"
            )
    lines.append(f"农场币：{account['point']}")
    lines.append(f"点券：{account['vip_point']}")
    lines.append(f"累计经验：{account['experience']}")
    return "\n".join(lines)


def plot_ids_text(snapshot: Snapshot) -> str:
    """无图片能力时按实际快照返回地块编号。"""
    owned = sorted(plot.slot for plot in snapshot.plots)
    remaining = sorted(set(range(1, 31)) - set(owned))
    return '\n'.join((
        '地块编号',
        f'已开垦（{len(owned)}块）：' + ('、'.join(map(str, owned)) or '无'),
        f'待开垦（{len(remaining)}块）：'
        + ('、'.join(map(str, remaining)) or '无'),
        '前两排交错编号，之后逐排推进。',
        '发送「农场详述」查看各地块的作物信息。',
    ))


def snapshot_text(snapshot: Snapshot) -> str:
    account = snapshot.account
    lines = [
        account.name, f"等级：{account.level}",
        f"农场币：{account.point}", f"点券：{account.vip_point}",
        f"累计经验：{account.experience}",
    ]
    for item in snapshot.inventory:
        lock = "锁定" if item.locked else "未锁定"
        lines.append(
            f"{item.name}（#{item.plant_id}）：种子{item.seeds}，"
            f"作物{item.crops}，{lock}"
        )
    for plot in snapshot.plots:
        state = "空地" if plot.plant is None else plot.plant.name
        if plot.withered:
            state += "（枯萎）"
        if plot.pest_count:
            state += f"，虫子{plot.pest_count}只"
            if plot.growth_remaining:
                state += f"，生长速度降低{plot.pest_count * 5}%"
        if plot.maturity_pests:
            state += f"，本季已确定减产{plot.maturity_pests * 5}%"
        lines.append(f"地块{plot.slot}：{state}")
    return "\n".join(lines)
