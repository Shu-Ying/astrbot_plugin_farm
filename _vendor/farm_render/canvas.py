"""同步 Pillow 图片原语；调用方负责整次绘制的异步调度。"""

from functools import lru_cache
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont


@lru_cache(maxsize=32)
def font(path, size):
    return ImageFont.truetype(str(path), size=size)


class Canvas:
    def __init__(self, image):
        self.image = image.convert("RGBA")

    @classmethod
    def new(cls, size, color=(0, 0, 0, 0)):
        return cls(Image.new("RGBA", size, color))

    def copy(self):
        return Canvas(self.image.copy())

    def resize(self, size):
        return Canvas(self.image.resize(size, Image.Resampling.LANCZOS))

    def crop(self, box):
        return Canvas(self.image.crop(box))

    def paste(self, image, position):
        source = image.image if isinstance(image, Canvas) else image
        self.image.alpha_composite(source.convert("RGBA"), position)

    @staticmethod
    def measure_text(text, font_path, size):
        return font(font_path, size).getlength(text)

    @classmethod
    def fit_text(cls, text, font_path, size, width):
        text = " ".join(str(text).split())[:256]
        if cls.measure_text(text, font_path, size) <= width:
            return text
        suffix = "…"
        while text and cls.measure_text(
            text + suffix, font_path, size,
        ) > width:
            text = text[:-1]
        return text + suffix if cls.measure_text(
            suffix, font_path, size,
        ) <= width else ""

    def text(self, position, text, font_path, size, color):
        ImageDraw.Draw(self.image).text(
            position, text, font=font(font_path, size), fill=color,
        )

    def rectangle(self, box, color, radius=0):
        ImageDraw.Draw(self.image).rounded_rectangle(
            box, radius=radius, fill=color,
        )

    def encode(self, codec, quality=75, method=2):
        output = BytesIO()
        if codec == "JPEG":
            flattened = Image.new("RGB", self.image.size, "white")
            flattened.paste(self.image, mask=self.image.getchannel("A"))
            flattened.save(output, "JPEG", quality=quality)
        elif codec == "WEBP":
            self.image.save(
                output, "WEBP", quality=quality, method=method,
            )
        elif codec == "PNG":
            self.image.save(output, "PNG", compress_level=3)
        else:
            raise ValueError("Unsupported output codec")
        return output.getvalue()
