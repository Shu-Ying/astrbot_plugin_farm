"""把 Unity 局部坐标映射到本地地块；保留完整纹理及透明留白。"""

from math import ceil, floor

from PIL import Image


def ground_contact(image, centered=False, threshold=32, band_fraction=.2):
    alpha = image.convert('RGBA').getchannel('A')
    box = alpha.point(lambda value: 255 if value >= threshold else 0).getbbox()
    if box is None:
        return image.width/2, image.height/2
    left, top, right, bottom = box
    if centered:
        return (left+right)/2, (top+bottom)/2
    start = max(top, bottom-max(1, round((bottom-top)*band_fraction)))
    pixels = alpha.load()
    weight = x_sum = y_sum = 0
    for y in range(start, bottom):
        for x in range(left, right):
            value = pixels[x, y]
            if value >= threshold:
                weight += value
                x_sum += (x+.5)*value
                y_sum += (y+.5)*value
    return x_sum/weight, y_sum/weight


def place_sprite(image, center, offset, pivot, factor, transform, scale):
    (a, b), (c, d) = transform
    anchor_x = (center[0]+a*offset[0]+b*offset[1])*scale
    anchor_y = (center[1]+c*offset[0]+d*offset[1])*scale
    m00, m01 = a*factor*scale, -b*factor*scale
    m10, m11 = c*factor*scale, -d*factor*scale
    px, py = image.width*pivot[0], image.height*pivot[1]
    corners = [(
        anchor_x+m00*(x-px)+m01*(y-py),
        anchor_y+m10*(x-px)+m11*(y-py),
    ) for x, y in ((0, 0), (image.width, 0),
                   (0, image.height), image.size)]
    left = floor(min(x for x, _ in corners))
    top = floor(min(y for _, y in corners))
    width = max(1, ceil(max(x for x, _ in corners))-left)
    height = max(1, ceil(max(y for _, y in corners))-top)
    det = m00*m11-m01*m10
    if abs(det) < 1e-12:
        raise ValueError('Degenerate scene transform')
    i00, i01, i10, i11 = m11/det, -m01/det, -m10/det, m00/det
    dx, dy = left-anchor_x, top-anchor_y
    result = image.transform(
        (width, height), Image.Transform.AFFINE,
        (i00, i01, px+i00*dx+i01*dy,
         i10, i11, py+i10*dx+i11*dy), Image.Resampling.BICUBIC,
    )
    return result, (left, top)
