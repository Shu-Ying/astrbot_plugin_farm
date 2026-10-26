"""框架无关、不可变的渲染输入与输出。"""

from dataclasses import dataclass

from PIL import features

from ..farm_core.domain import Account


@dataclass(frozen=True)
class RenderOptions:
    width: int = 1024  # 目标宽度；从此尺寸开始合成。
    format: str = "AUTO"  # AUTO/WEBP/JPEG/PNG。
    quality: int = 75  # 有损编码质量，不代表分辨率。
    method: int = 2  # WebP 编码力度，0最快，6最慢。
    theme: str = "default"  # 显式主题，不读取隐含季节或全局配置。
    show_plot_ids: bool = False  # 编号图显示全部地块及开垦状态。

    def __post_init__(self):
        if type(self.show_plot_ids) is not bool:
            raise ValueError("Invalid plot ID option")
        for value, low, high in (
            (self.width, 256, 3072), (self.quality, 1, 95),
            (self.method, 0, 6),
        ):
            if type(value) is not int or not low <= value <= high:
                raise ValueError("Invalid render option")
        if self.format not in ("AUTO", "WEBP", "JPEG", "PNG"):
            raise ValueError("Unsupported output format")
        if self.theme not in ("default", "spring", "summer", "autumn",
                              "winter", "bee"):
            raise ValueError("Unsupported theme")

    @classmethod
    def high(cls, **kwargs):
        return cls(width=1536, quality=85, **kwargs)

    def codec(self, supported=("JPEG",)):
        if self.format == "AUTO":
            if "WEBP" in supported and features.check("webp"):
                return "WEBP"
            if "JPEG" in supported:
                return "JPEG"
            if "PNG" in supported:
                return "PNG"
            raise ValueError("No supported image codec")
        if self.format == "WEBP" and not features.check("webp"):
            raise ValueError("Pillow WebP support is unavailable")
        return self.format


@dataclass(frozen=True)
class PlotView:
    slot: int  # 1到30地块编号，对应统一位置表的slot-1项。
    state: str  # empty/growing/ripe/withered。
    sprite: str = ""  # 包内受控素材名，不来自用户路径。
    stage: int = 0  # 本季展示阶段。
    pest_count: int = 0  # 当前可见虫数；参与成图缓存键。
    pest_frames: tuple[str, ...] = ()  # 按虫序稳定选择的包内帧，参与缓存键。
    land_level: int = 0  # 土地等级；影响底图和成图缓存。


@dataclass(frozen=True)
class Scene:
    scope: str  # 完整身份的摘要，只用于缓存隔离。
    account: Account  # 一致快照中的可见账户。
    plots: tuple[PlotView, ...]  # 已解锁地块及统一时刻的阶段。


@dataclass(frozen=True)
class RenderResult:
    content: bytes  # 已编码图片，不携带用户对象。
    mime: str  # 与实际编码一致的媒体类型。
    width: int  # 实际宽度。
    height: int  # 实际高度。
    compose_ms: float  # 本次合成毫秒。
    encode_ms: float  # 本次编码毫秒。
    cache_hit: bool = False  # 成图缓存命中。
