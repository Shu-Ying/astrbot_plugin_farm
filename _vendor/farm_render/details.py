"""一次快照生成农场全景和分页明细；不读取或修改数据库。"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from io import BytesIO

from astrbot.api import logger
from PIL import Image, ImageDraw

from ..farm_core.domain import boosted
from ..farm_core.pests import advance_plot
from .assets import Assets
from .canvas import Canvas, font
from .layout import scene_from_snapshot
from .models import RenderOptions

PAGE_SIZE = 10
BEIJING = timezone(timedelta(hours=8))


@dataclass(frozen=True)
class DetailRow:
    slot: int  # 与全景标号一致的本地地块编号。
    name: str  # 作物名称，空地显示空地。
    state: str  # 生长、成熟、枯萎或空地状态。
    stage: str  # 已验证资源中的阶段序号，不猜测开花等语义。
    season: str  # 当前待收获季数；枯萎时为已完成季数。
    amount: int | None  # 当前虫况预估或成熟后的确定产量。
    maturity: str  # 北京时间的预计成熟时间或可操作提示。
    pest_note: str  # 当前虫数及生长减速或成熟减产信息。


def detail_rows(renderer, identity, snapshot, now, page):
    plots = sorted(snapshot.plots, key=lambda p: p.slot)
    pages = max(1, (len(plots) + PAGE_SIZE - 1) // PAGE_SIZE)
    if type(page) is not int or not 1 <= page <= pages:
        raise ValueError("Invalid detail page")
    metadata = renderer.assets.metadata if renderer else Assets(0).metadata
    views = {
        v.slot: v
        for v in scene_from_snapshot(
            identity,
            snapshot,
            now,
            metadata,
        ).plots
    }
    rows = []
    for stored in plots[(page - 1) * PAGE_SIZE : page * PAGE_SIZE]:
        plot = advance_plot(stored, now)
        plant = plot.plant
        if plant is None:
            rows.append(
                DetailRow(
                    plot.slot, "空地", "空地", "—", "—", None, "可播种", ""
                )
            )
            continue
        if plot.withered:
            rows.append(
                DetailRow(
                    plot.slot,
                    plant.name,
                    "已枯萎",
                    "枯萎",
                    f"{plant.crop}/{plant.crop}季",
                    None,
                    "可铲除",
                    "",
                )
            )
            continue
        ripe = plot.mature_at is not None and plot.mature_at <= now
        pests = plot.maturity_pests if ripe else plot.pest_count
        amount = max(
            0,
            boosted(plant.harvest, plot.yield_bonus) * (100 - 5 * pests) // 100
            - plot.stolen_count,
        )
        info = metadata["plants"].get(plant.name)
        total = len(set(info["phase"].split(","))) if info else None
        stage = (
            "成熟"
            if ripe
            else f"阶段 {views[plot.slot].stage}/{total}"
            if total
            else "生长中"
        )
        maturity = (
            "可收获"
            if ripe
            else datetime.fromtimestamp(
                plot.mature_at,
                BEIJING,
            ).strftime("%m-%d %H:%M")
        )
        note = ""
        if ripe and (plot.pest_count or pests):
            note = (
                f"当前虫 {plot.pest_count}只 · 成熟时 {pests}只"
                f" · 本季减产 {5*pests}%"
            )
        elif plot.pest_count:
            note = (
                f"虫 {plot.pest_count}只 · 生长减速 {5*pests}%"
                f" · 预计减产 {5*pests}%"
            )
        rows.append(
            DetailRow(
                plot.slot,
                plant.name,
                "已成熟" if ripe else "生长中",
                stage,
                f"{plot.harvest_count+1}/{plant.crop}季",
                amount,
                maturity,
                note,
            )
        )
    return tuple(rows), pages


def details_text(rows, page, pages):
    lines = [f"农场详述 第{page}/{pages}页"]
    for row in rows:
        amount = (
            "—"
            if row.amount is None
            else f'{"当前" if row.state == "已成熟" else "预计"}'
            f'{row.amount}个'
        )
        lines.append(
            f"{row.slot}号地 {row.name}｜{row.stage}｜{row.season}"
            f"｜{amount}｜{row.maturity}"
        )
        if row.pest_note:
            lines.append("  " + row.pest_note)
    lines.append("时间为北京时间；生长中产量按当前虫况估算，后续变化会更新。")
    if page < pages:
        lines.append(f"下一页：农场详述 {page+1}")
    if page > 1:
        lines.append(f"上一页：农场详述 {page-1}")
    return "\n".join(lines)


def render_details(
    renderer,
    identity,
    snapshot,
    now,
    page,
    theme="default",
    image_format="AUTO",
    avatar=None,
    quality=75,
):
    rows, pages = detail_rows(renderer, identity, snapshot, now, page)
    options = RenderOptions(format=image_format, quality=quality, theme=theme)
    farm = renderer.render(identity, snapshot, now, options, avatar)
    height = 922 + max(1, len(rows)) * 92
    canvas = Canvas.new((1024, height), "#ac713c")
    draw = ImageDraw.Draw(canvas.image)
    draw.rounded_rectangle(
        (12, 12, 1012, height - 12),
        20,
        fill="#fff1d0",
        outline="#663e20",
        width=4,
    )

    def text(value, x, y, size=24, color="#58341c", width=970):
        value = canvas.fit_text(value, renderer.font_path, size, width)
        box = font(renderer.font_path, size).getbbox(value)
        canvas.text((x, y - box[1]), value, renderer.font_path, size, color)

    draw.rounded_rectangle(
        (24, 24, 1000, 82), 12, fill="#d98a32", outline="#a46325", width=2
    )
    text(
        snapshot.account.name + " · 农场详述", 44, 39, 30, "#fff5dd", width=690
    )
    text(f"第 {page}/{pages} 页", 802, 45, 23, "#fff5dd", width=180)
    with Image.open(BytesIO(farm.content)) as image:
        image = image.convert("RGBA").resize(
            (976, 595), Image.Resampling.LANCZOS
        )
    canvas.paste(image, (24, 96))
    soil_w, soil_h = renderer.assets.metadata["soil_size"]
    selected = {row.slot for row in rows}
    for plot in snapshot.plots:
        pos = renderer.assets.metadata["positions"][plot.slot - 1]
        x = round(24 + (pos["x"] + soil_w / 2) * 976 / 3072)
        y = round(96 + (pos["y"] + soil_h * 0.85) * 595 / 1872)
        fill = "#f8d85b" if plot.slot in selected else "#e8e2cc"
        draw.ellipse(
            (x - 14, y - 14, x + 14, y + 14),
            fill=fill,
            outline="#67431f",
            width=2,
        )
        label = str(plot.slot)
        box = font(renderer.font_path, 17).getbbox(label)
        text(label, x - (box[2] - box[0]) // 2, y - 9, 17, width=30)
    text(
        "黄色编号为本页地块 · 生长阶段与收获季数分别展示",
        40,
        711,
        22,
        "#7c704b",
    )
    text(
        "生长中按当前虫况估算；已成熟显示当前可收数量。", 40, 747, 20, "#7c704b"
    )
    columns = ((40, 238), (292, 146), (452, 126), (592, 138), (750, 228))
    draw.rounded_rectangle((24, 785, 1000, 833), 8, fill="#e5d09a")
    for label, (x, width) in zip(
        ("地块 / 作物", "生长阶段", "收获季数", "预计 / 可收", "成熟时间"),
        columns,
    ):
        text(label, x, 797, 22, width=width)
    for index, row in enumerate(rows):
        y = 843 + index * 92
        draw.rectangle(
            (24, y - 4, 1000, y + 82),
            fill="#fff8e5" if index % 2 == 0 else "#f7eac9",
        )
        values = (
            f"{row.slot}  {row.name}",
            row.stage,
            row.season,
            "—" if row.amount is None else f"{row.amount}个",
            row.maturity,
        )
        for value, (x, width) in zip(values, columns):
            text(value, x, y + 9, 23, width=width)
        if row.pest_note:
            text(row.pest_note, 60, y + 49, 19, "#9a682f", width=910)
    if not rows:
        text("暂无已解锁地块", 390, 870, 26)
    footer = 858 + max(1, len(rows)) * 92
    navigation = f"更新于 {datetime.fromtimestamp(now, BEIJING):%m-%d %H:%M:%S}"
    if page > 1:
        navigation += f"   上一页：农场详述 {page-1}"
    if page < pages:
        navigation += f"   下一页：农场详述 {page+1}"
    text(navigation, 40, footer, 22, width=940)
    codec = options.codec(("JPEG",))
    content = canvas.encode(codec, options.quality, options.method)
    logger.info(
        "farm details page=%s pages=%s rows=%s bytes=%s codec=%s " "quality=%s",
        page,
        pages,
        len(rows),
        len(content),
        codec,
        options.quality,
    )
    return content
