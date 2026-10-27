"""一次快照的分类仓库展示；不修改库存或资产。"""

from dataclasses import dataclass
import shlex

from PIL import Image

from ..farm_core.domain import FarmError, Plant

from .canvas import Canvas, font
from .models import RenderOptions
from .shop import duration

from astrbot.api import logger
PAGE_SIZE = 12


@dataclass(frozen=True)
class StockRow:
    plant_id: int  # 稳定本地作物编号。
    name: str  # 仓库存量名称。
    quantity: int  # 正库存数量，种子以粒计。
    group: str  # 可出售、已锁定、单季、多季或信息缺失。
    plant: Plant | None  # 当前目录规则；目录缺失时为None。


def warehouse_rows(snapshot, catalogue, kind):
    if kind not in ('crops', 'seeds'):
        raise ValueError('Invalid inventory kind')
    rows = []
    for item in snapshot.inventory:
        amount = getattr(item, kind)
        if amount <= 0:
            continue
        try:
            plant = catalogue.get_by_id(item.plant_id)
        except FarmError:
            plant = None
        if kind == 'crops':
            group = '已锁定' if item.locked else '可出售'
        else:
            group = ('信息缺失' if plant is None else
                     '多季种子' if plant.crop > 1 else '单季种子')
        rows.append(StockRow(item.plant_id, item.name, amount, group, plant))
    groups = ('可出售', '已锁定', '单季种子', '多季种子', '信息缺失')
    return tuple(sorted(rows, key=lambda r: (
        groups.index(r.group), r.plant_id,
    )))


def warehouse_page(rows, page):
    pages = max(1, (len(rows)+PAGE_SIZE-1)//PAGE_SIZE)
    if type(page) is not int or not 1 <= page <= pages:
        raise ValueError('Invalid inventory page')
    return rows[(page-1)*PAGE_SIZE:page*PAGE_SIZE], pages


def warehouse_text(rows, snapshot, kind, page, pages):
    title = '我的作物' if kind == 'crops' else '我的种子'
    unit = '个' if kind == 'crops' else '粒'
    lines = [f'{title} 第{page}/{pages}页',
             f'{len(rows)}种 · 共{sum(r.quantity for r in rows):,}{unit}']
    if kind == 'crops':
        value = sum(r.quantity*r.plant.price for r in rows
                    if r.group == '可出售' and r.plant is not None)
        note = '（不含目录缺失项）' if any(
            r.plant is None for r in rows if r.group == '可出售'
        ) else ''
        lines.append(f'可出售价值 {value:,} 农场币{note}')
    else:
        empty = sum(p.plant is None for p in snapshot.plots)
        lines.append(f'当前空地 {empty}/{len(snapshot.plots)}块')
    chunk, _ = warehouse_page(rows, page)
    group = None
    for row in chunk:
        if row.group != group:
            group = row.group
            count = sum(r.group == group for r in rows)
            suffix = ' · 出售时自动跳过' if group == '已锁定' else ''
            lines.append(f'{group}（{count}种）{suffix}')
        if row.plant is None:
            detail = '目录信息缺失'
        elif kind == 'crops':
            detail = (f'单价{row.plant.price} · '
                      f'价值{row.plant.price*row.quantity:,}农场币')
        else:
            detail = (f'首熟{duration(row.plant.growth_seconds)} / '
                      f'{row.plant.crop}季')
        lines.append(f'{row.name}（#{row.plant_id}） '
                     f'{row.quantity:,}{unit}｜{detail}')
    if not rows:
        lines.append('暂无作物，请播种并收获。' if kind == 'crops'
                     else '暂无种子，请发送「种子商店」选购。')
    example = next((r for r in chunk if r.plant is not None and (
        kind == 'seeds' or r.group == '可出售'
    )), None)
    if example:
        action = '出售作物' if kind == 'crops' else '播种'
        lines.append(f'按编号：{action} #{example.plant_id} 1')
        lines.append(f'按名称：{action} {shlex.quote(example.name)} 1')
    if kind == 'crops':
        lines.append('全部出售：出售作物（自动跳过已锁定作物）')
        lines.append('锁定/解锁：作物加锁 #编号 / 作物解锁 #编号')
    if page < pages:
        lines.append(f'下一页：{title} {page+1}')
    if page > 1:
        lines.append(f'上一页：{title} {page-1}')
    return '\n'.join(lines)


def render_warehouse(renderer, rows, snapshot, kind, page, pages,
                     image_format='AUTO', high=False, quality=75):
    options = RenderOptions(width=1024 if high else 768,
                            format=image_format,
                            quality=max(85, quality) if high else quality)
    codec = options.codec()
    scale = options.width/1024
    s = lambda n: round(n*scale)
    canvas = Canvas(renderer.assets.image('webgl/shop-board.png',
                                         (s(1024), s(1536))))
    patch = canvas.image.crop(tuple(s(n) for n in (300, 340, 880, 445)))
    canvas.image.paste(patch.resize((s(824), s(930))), (s(100), s(320)))

    def rectangle(box, color, radius):
        canvas.rectangle(tuple(s(n) for n in box), color, radius=s(radius))

    rectangle((105, 322, 919, 1249), '#fff1cf', 15)
    def text(value, xy, size=26, color='#603817', width=760):
        size = max(1, s(size))
        xy = tuple(s(n) for n in xy)
        width = s(width)
        value = canvas.fit_text(value, renderer.font_path, size, width)
        box = font(renderer.font_path, size).getbbox(value)
        canvas.text((xy[0], xy[1]-box[1]), value,
                    renderer.font_path, size, color)

    title = '我的作物' if kind == 'crops' else '我的种子'
    text(title, (385, 60), 62, '#fff4cb')
    text('分类仓库 · 发送文字指令操作', (310, 178), 27, '#7e653a')
    summary = warehouse_text(rows, snapshot, kind, page, pages).splitlines()
    text('  ·  '.join(summary[1:3]), (138, 248), 26, '#607d30', 750)
    chunk, _ = warehouse_page(rows, page)
    group = None
    y = 336
    unit = '个' if kind == 'crops' else '粒'
    for index, row in enumerate(chunk):
        if row.group != group:
            group = row.group
            rectangle((123, y, 899, y+43), '#d8e5b6', 7)
            count = sum(r.group == group for r in rows)
            label = f'{group}（{count}种）'
            if group == '已锁定':
                label += ' · 出售时自动跳过'
            text(label, (140, y+8), 24, '#607d30')
            y += 49
        if index % 2 == 0:
            rectangle((123, y, 899, y+55), '#fff8e4', 5)
        icon = f'plant/{row.name}/icon.png'
        if icon in renderer.assets.metadata['images']:
            image = renderer.assets.image(icon)
            image.thumbnail((s(44), s(46)), Image.Resampling.LANCZOS)
            canvas.paste(image, (s(158)-image.width//2,
                                 s(y+27)-image.height//2))
        else:
            text('?', (149, y+15), 26)
        text(f'#{row.plant_id}', (193, y+19), 21, '#607d30', 82)
        text(row.name, (283, y+15), 26, width=250)
        text(f'{row.quantity:,}{unit}', (550, y+16), 25, '#b86d22', 152)
        if row.plant is None:
            detail = '目录缺失'
        elif kind == 'crops':
            detail = f'{row.quantity*row.plant.price:,} 币'
        else:
            detail = (f'{duration(row.plant.growth_seconds)} / '
                      f'{row.plant.crop}季')
        text(detail, (714, y+19), 20, width=174)
        y += 60
    if not rows:
        text('暂无作物，请播种并收获。' if kind == 'crops' else
             '暂无种子，请发送「种子商店」选购。', (235, 675), 30, width=620)
    if kind == 'crops':
        footer = ['全部出售：出售作物（自动跳过已锁定作物）',
                  '指定出售：出售作物 #编号 数量（也支持作物名）',
                  '锁定/解锁：作物加锁 #编号 / 作物解锁 #编号']
    else:
        footer = ['按编号：播种 #编号 数量  ｜  按名称：播种 作物名 数量',
                  '每块地消耗1粒；不填数量时自动播种到可用空地。',
                  '表内时间为首熟时间，季数为最多可收获季数。']
    for y, line in zip((1278, 1318, 1358), footer):
        text(line, (142, y), 24, width=745)
    nav = f'第 {page}/{pages} 页'
    if page < pages:
        nav += f'  下一页：{title} {page+1}'
    if page > 1:
        nav += f'  上一页：{title} {page-1}'
    nav = canvas.fit_text(nav, renderer.font_path, 23, 510)
    x = round((1024-canvas.measure_text(nav, renderer.font_path, 23))/2)
    text(nav, (x, 1424), 23, width=510)
    content = canvas.encode(codec, options.quality, options.method)
    logger.info('farm warehouse kind=%s page=%s bytes=%s codec=%s width=%s '
                'quality=%s', kind, page, len(content), codec,
                options.width, options.quality)
    return content
