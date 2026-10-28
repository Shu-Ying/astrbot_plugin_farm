"""单张动态帮助长图：实测换行、固定字号及内容驱动高度。"""

from PIL import Image

from ..farm_core.commands import HELP_NOTES, help_groups
from .canvas import Canvas, font
from .models import RenderOptions


def wrap_text(value, font_path, size, width):
    """按实际字宽换行，不截断命令、别名或说明。"""
    lines = []
    for paragraph in value.split("\n"):
        line = ""
        for char in paragraph:
            if (
                line
                and Canvas.measure_text(
                    line + char,
                    font_path,
                    size,
                )
                > width
            ):
                lines.append(line)
                line = ""
            line += char
        lines.append(line)
    return tuple(lines)


def help_layout(specs, font_path):
    groups = []
    for title, rows in help_groups(specs):
        title_lines = wrap_text(title, font_path, 30, 452)
        header = 26 + len(title_lines) * 42
        prepared = []
        height = header + 18
        for usage, description in rows:
            commands = wrap_text(usage, font_path, 28, 484)
            notes = wrap_text(description, font_path, 23, 484)
            row_height = len(commands) * 40 + len(notes) * 34 + 30
            prepared.append((commands, notes, row_height))
            height += row_height
        groups.append((title_lines, header, tuple(prepared), height))
    # 先分配较高分类，再恢复各列原有分类顺序，避免长列旁大块留白。
    buckets = [[], []]
    heights = [0, 0]
    for index in sorted(range(len(groups)), key=lambda i: -groups[i][3]):
        column = min(range(2), key=lambda i: heights[i])
        buckets[column].append(index)
        heights[column] += groups[index][3] + 24
    columns = tuple(
        tuple(groups[i] for i in sorted(bucket)) for bucket in buckets
    )
    body_height = max(sum(g[3] + 24 for g in col) for col in columns)
    tips = tuple(
        line
        for note in HELP_NOTES
        for line in wrap_text(
            note,
            font_path,
            23,
            1072,
        )
    )
    return columns, body_height, tips


def render_help(renderer, specs, platform, image_format="AUTO", quality=75):
    options = RenderOptions(width=1200, format=image_format, quality=quality)
    columns, body_height, tips = help_layout(specs, renderer.font_path)
    footer_y = 236 + body_height
    canvas = Canvas.new((1200, footer_y + 90 + len(tips) * 35 + 40), "#f5f3e6")

    # 使用包内现有农场背景，仅作小面积页眉，不在正文后叠加纹理。
    landscape = renderer.assets.image(
        "background/decorateIcon/decorate_default_1.jpg",
    )
    crop = landscape.crop((0, 0, landscape.width, landscape.height // 3))
    crop = crop.resize((1200, 200), Image.Resampling.LANCZOS)
    canvas.paste(crop, (0, 0))
    canvas.rectangle((340, 32, 860, 160), "#915d32", radius=18)
    canvas.rectangle((348, 38, 852, 154), "#f2d69b", radius=14)

    def text(value, x, y, size=23, color="#504a3d"):
        box = font(renderer.font_path, size).getbbox(value)
        canvas.text((x, y - box[1]), value, renderer.font_path, size, color)

    text("农场帮助", 478, 53, 52, "#382b19")
    label = {"zhenxun": "真寻", "nonebot": "NoneBot", "astrbot": "AstrBot"}
    subtitle = f"{label[platform]} · 常用指令与玩法"
    subtitle_width = canvas.measure_text(subtitle, renderer.font_path, 23)
    text(subtitle, round((1200 - subtitle_width) / 2), 118)
    for column, x in zip(columns, (36, 612)):
        y = 224
        for title_lines, header, rows, height in column:
            canvas.rectangle((x, y, x + 552, y + height), "#d1d7bc", radius=16)
            canvas.rectangle(
                (x + 1, y + 1, x + 551, y + height - 1), "#fffdf5", radius=15
            )
            canvas.rectangle((x, y, x + 552, y + header), "#4c7542", radius=15)
            canvas.rectangle(
                (x, y + header - 15, x + 552, y + header), "#4c7542"
            )
            # 小芽标记；不依赖 emoji 字体或生成图片内的文字。
            canvas.rectangle(
                (x + 22, y + 21, x + 29, y + 44), "#d7e8a0", radius=3
            )
            canvas.rectangle(
                (x + 10, y + 13, x + 26, y + 28), "#bad571", radius=7
            )
            canvas.rectangle(
                (x + 28, y + 9, x + 46, y + 24), "#e2ecac", radius=8
            )
            for index, line in enumerate(title_lines):
                text(line, x + 62, y + 16 + index * 42, 30, "#ffffff")
            yy = y + header + 18
            for index, (commands, notes, row_height) in enumerate(rows):
                for line in commands:
                    text(line, x + 28, yy, 28, "#342c20")
                    text(line, x + 29, yy, 28, "#342c20")
                    yy += 40
                for line in notes:
                    text(line, x + 28, yy + 2)
                    yy += 34
                yy += 30
                if index + 1 < len(rows):
                    canvas.rectangle(
                        (x + 28, yy - 15, x + 524, yy - 14), "#e4e3d3"
                    )
            y += height + 24
    canvas.rectangle(
        (36, footer_y, 1164, canvas.image.height - 36), "#e4ecd5", radius=16
    )
    text("参数与玩法提示", 64, footer_y + 20, 29, "#3f6437")
    for index, line in enumerate(tips):
        text(line, 64, footer_y + 70 + index * 35)
    return canvas.encode(options.codec(), options.quality, options.method)
