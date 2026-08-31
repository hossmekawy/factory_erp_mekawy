"""Convert an uploaded logo (any format) into a favicon.ico plus the PNG
sizes a PWA manifest and iOS home-screen icon need.
"""
from io import BytesIO

from django.core.files.base import ContentFile
from PIL import Image


def _square(img: Image.Image, size: int) -> Image.Image:
    """Center-crop to a square, then resize — avoids squashing non-square logos."""
    img = img.convert("RGBA")
    w, h = img.size
    if w != h:
        side = min(w, h)
        left = (w - side) // 2
        top = (h - side) // 2
        img = img.crop((left, top, left + side, top + side))
    return img.resize((size, size), Image.LANCZOS)


def generate_site_icons(settings_obj, uploaded_file) -> None:
    """Read `uploaded_file`, write favicon.ico + icon_192/512 + apple_touch_icon
    onto `settings_obj`'s ImageFields, and save it.
    """
    source = Image.open(uploaded_file)
    source.load()  # force-read now, before the temp upload file is cleaned up

    ico_buf = BytesIO()
    _square(source, 256).save(ico_buf, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
    settings_obj.favicon.save("favicon.ico", ContentFile(ico_buf.getvalue()), save=False)

    for field, size in (("icon_192", 192), ("icon_512", 512), ("apple_touch_icon", 180)):
        buf = BytesIO()
        _square(source, size).save(buf, format="PNG")
        getattr(settings_obj, field).save(f"{field}.png", ContentFile(buf.getvalue()), save=False)

    settings_obj.save()
