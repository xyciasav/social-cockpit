from collections import deque
from pathlib import Path
import xml.etree.ElementTree as ET

from PIL import Image, ImageFilter


def isolate_background(source, target, tolerance=38):
    """Remove border-connected pixels similar to sampled canvas corners."""
    image = Image.open(source).convert("RGBA")
    rgb = image.convert("RGB")
    width, height = image.size
    corners = [rgb.getpixel(point) for point in ((0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1))]
    background = tuple(sum(color[channel] for color in corners) // 4 for channel in range(3))
    pixels = rgb.load(); alpha = Image.new("L", image.size, 255); mask = alpha.load()
    queue = deque()
    seen = set()
    for x in range(width): queue.extend(((x, 0), (x, height - 1)))
    for y in range(height): queue.extend(((0, y), (width - 1, y)))
    while queue:
        x, y = queue.popleft()
        if (x, y) in seen: continue
        seen.add((x, y)); color = pixels[x, y]
        distance = sum((color[i] - background[i]) ** 2 for i in range(3)) ** .5
        if distance > tolerance: continue
        mask[x, y] = 0
        if x: queue.append((x - 1, y))
        if x + 1 < width: queue.append((x + 1, y))
        if y: queue.append((x, y - 1))
        if y + 1 < height: queue.append((x, y + 1))
    alpha = alpha.filter(ImageFilter.GaussianBlur(.6))
    image.putalpha(alpha)
    image.save(target, "PNG", optimize=True)
    extrema = alpha.getextrema()
    if extrema[0] == 255:
        raise ValueError("PNG still contains a background; automatic isolation found no removable canvas")
    if extrema[1] == 0:
        raise ValueError("Background removal produced an empty image")


def vectorize_png(source, target, max_size=384):
    """Create actual vector paths from an alpha-aware, posterized raster (never embeds PNG)."""
    image = Image.open(source).convert("RGBA")
    image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
    width, height = image.size
    colors = image.convert("RGB").quantize(colors=8, method=Image.Quantize.MEDIANCUT).convert("RGB")
    alpha = image.getchannel("A")
    buckets = {}
    for y in range(height):
        x = 0
        while x < width:
            if alpha.getpixel((x, y)) < 96: x += 1; continue
            color = colors.getpixel((x, y)); start = x; x += 1
            while x < width and alpha.getpixel((x, y)) >= 96 and colors.getpixel((x, y)) == color: x += 1
            buckets.setdefault(color, []).append((start, y, x - start))
    if not buckets: raise ValueError("No foreground paths were found")
    scale_x = Image.open(source).width / width; scale_y = Image.open(source).height / height
    svg = ET.Element("svg", {"xmlns":"http://www.w3.org/2000/svg", "viewBox":f"0 0 {Image.open(source).width} {Image.open(source).height}"})
    for color, runs in buckets.items():
        d = " ".join(f"M{x*scale_x:.2f},{y*scale_y:.2f}h{length*scale_x:.2f}v{scale_y:.2f}h{-length*scale_x:.2f}z" for x,y,length in runs)
        ET.SubElement(svg, "path", {"fill":"#%02x%02x%02x" % color, "d":d})
    ET.ElementTree(svg).write(target, encoding="utf-8", xml_declaration=True)
    validate_svg(target)


def validate_svg(path):
    root = ET.parse(path).getroot()
    tags = [node.tag.rsplit("}", 1)[-1] for node in root.iter()]
    if "image" in tags or not any(tag in ("path", "polygon", "circle", "ellipse") for tag in tags):
        raise ValueError("SVG is not real vector artwork")
    if "rect" in tags:
        raise ValueError("SVG contains a rectangular background")
    if Path(path).stat().st_size > 8 * 1024 * 1024:
        raise ValueError("SVG is too complex to be useful")
