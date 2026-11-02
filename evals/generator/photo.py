"""
A phone photo of a printed page, simulated: rendered, cut, placed on a table, tilted and shaded
"""

from io import BytesIO

import pypdfium2 as pdfium
from PIL import Image, ImageChops, ImageFilter

from evals.generator.spec import Photo

DPI = 200
PAPER = (247, 243, 233)
TABLE = (96, 80, 66)


def to_photo(pdf: bytes, photo: Photo) -> bytes:
    document = pdfium.PdfDocument(pdf)
    try:
        page: Image.Image = document[0].render(scale=DPI / 72).to_pil().convert("RGB")
    finally:
        document.close()
    # Thermal paper is not white
    page = ImageChops.multiply(page, Image.new("RGB", page.size, PAPER))

    margin = round(max(page.size) * 0.12)
    scene = Image.new("RGB", (page.width + 2 * margin, page.height + 2 * margin), TABLE)
    scene.paste(page, (margin, margin))
    scene = scene.rotate(photo.angle, resample=Image.Resampling.BICUBIC, fillcolor=TABLE)

    # Keystone: sample a quad whose top edge is narrower, so the top comes out wider
    width, height = scene.size
    inset = photo.skew * width
    scene = scene.transform(
        scene.size,
        Image.Transform.QUAD,
        (inset, 0, 0, height, width, height, width - inset, 0),
        resample=Image.Resampling.BICUBIC,
        fillcolor=TABLE,
    )

    # Uneven light: a diagonal shadow from one corner
    gradient = Image.linear_gradient("L").rotate(-40, expand=True)
    side = 181  # the largest square inside the rotated 256 px gradient, so no corners
    left = (gradient.width - side) // 2
    gradient = gradient.crop((left, left, left + side, left + side)).resize(scene.size)
    shade = gradient.point(lambda v: round(255 - photo.light * 150 * v / 255))
    scene = ImageChops.multiply(scene, Image.merge("RGB", (shade, shade, shade)))
    scene = scene.filter(ImageFilter.GaussianBlur(0.8))
    if photo.keep < 1:
        # The frame cuts the page: everything below `keep` of the page is outside the photo
        scene = scene.crop((0, 0, width, margin + round(page.height * photo.keep)))

    out = BytesIO()
    scene.save(out, "JPEG", quality=85)
    return out.getvalue()
