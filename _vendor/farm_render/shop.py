"""文字指令使用的木质种子价目板；全部价格来自离线目录。"""

import logging
import shlex

from PIL import Image

from .canvas import Canvas, font
from .models import RenderOptions

logger = logging.getLogger(__name__)
PAGE_SIZE = 6


def shop_page(catalogue, page):
    plants = sorted((p for p in catalogue if p.buyable),
                    key=lambda p: p.plant_id)
    pages = max(1, (len(plants) + PAGE_SIZE - 1) // PAGE_SIZE)
    if type(page) is not int or not 1 <= page <= pages:
        raise ValueError('Invalid shop page')
    start = (page - 1) * PAGE_SIZE
    return tuple(plants[start:start + PAGE_SIZE]), pages


def duration(seconds):
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return ''.join(f'{value}{unit}' for value, unit in (
        (hours, '小时'), (minutes, '分'), (seconds, '秒'),
    ) if value) or '0秒'


def render_shop(renderer, plants, account, page, pages, image_format='AUTO',
                quality=75):
    options = RenderOptions(format=image_format, quality=quality)
    codec = options.codec()
    canvas = Canvas(renderer.assets.image('webgl/shop-board.png', (1024, 1536)))

    def text(value, xy, size=28, color='#5b3015', width=850):
        value = canvas.fit_text(value, renderer.font_path, size, width)
        box = font(renderer.font_path, size).getbbox(value)
        canvas.text((xy[0], xy[1]-box[1]), value,
                    renderer.font_path, size, color)

    def centered(value, y, size, color='#5b3015'):
        x = round((1024 - canvas.measure_text(
            value, renderer.font_path, size,
        )) / 2)
        text(value, (x, y), size, color)

    centered('种 子 商 店', 58, 54, '#fff5d3')
    centered('种子价目板 · 发送文字指令购买', 178, 25, '#7a6439')
    balances = ('未开通农场 · 可浏览种子，购买前请发送：开通农场'
                if account is None else
                f'Lv.{account.level}    农场币 {account.point:,}    '
                f'点券 {account.vip_point:,}')
    text(balances, (142, 248), 29, width=745)
    for index, plant in enumerate(plants):
        y = 326 + index * 156
        icon = f'plant/{plant.name}/icon.png'
        if icon in renderer.assets.metadata['images']:
            image = renderer.assets.image(icon)
            image.thumbnail((104, 110), Image.Resampling.LANCZOS)
            canvas.paste(image, (175-image.width//2, y+67-image.height//2))
        else:
            text('暂无图', (133, y+55), 23, '#8b8057', width=92)
            logger.info('farm shop packaged icon unavailable id=%s',
                        plant.plant_id)
        text(plant.name, (268, y+13), 34, width=490)
        text(f'#{plant.plant_id}', (774, y+17), 26, '#69783e', width=132)
        currency = '点券' if plant.is_vip else '农场币'
        text(f'{plant.cost:,} {currency} / 粒', (268, y+62), 32,
             '#b66522', width=480)
        locked = account is not None and account.level < plant.level
        text(f'{"需" if locked else "等级"} Lv.{plant.level}',
             (774, y+69), 23, '#ac542d' if locked else '#66733d', width=132)
        text(f'首熟 {duration(plant.growth_seconds)} · {plant.crop}季'
             f' · 每季{plant.harvest}个', (268, y+108), 23, width=635)
    if not plants:
        text('暂无出售中的种子', (340, 690), 34)
    example = plants[0] if plants else None
    if example:
        text(f'按编号：购买种子 #{example.plant_id} 5', (142, 1291), 27)
        name = example.name
        if any(c.isspace() for c in name) or any(c in name for c in '\"\''):
            name = shlex.quote(name)
        text(f'按名称：购买种子 {name} 5', (142, 1341), 27, width=750)
    else:
        text('购买种子 #编号 数量  或  购买种子 种子名 数量',
             (142, 1316), 25, width=750)
    navigation = f'第 {page} / {pages} 页'
    if page < pages:
        navigation += f'    下一页：种子商店 {page+1}'
    elif page > 1:
        navigation += f'    上一页：种子商店 {page-1}'
    text(navigation, (263, 1420), 23, width=510)
    content = canvas.encode(codec, options.quality, options.method)
    logger.info('farm shop render width=%s height=%s bytes=%s codec=%s '
                'quality=%s', *canvas.image.size, len(content), codec,
                options.quality)
    return content
