"""Compose app icons (dark & light) from the traced mark and export PNG sizes for web/PWA/Flutter."""
import re, os, cairosvg
here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def inner(path):
    s = open(path).read()
    vb = [float(x) for x in re.search(r'viewBox="([^"]+)"', s).group(1).split()]
    body = re.search(r'<svg[^>]*>(.*)</svg>', s, re.S).group(1)
    return vb, body
def icon(markfile, bg, rounded=True, pad=0.17):
    (x, y, w, h), body = inner(markfile)
    S = 1024; inner_s = S * (1 - 2 * pad); k = inner_s / max(w, h)
    tx = (S - w * k) / 2; ty = (S - h * k) / 2
    rx = 230 if rounded else 0
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {S} {S}">'
            f'<rect width="{S}" height="{S}" rx="{rx}" fill="{bg}"/>'
            f'<g transform="translate({tx:.1f},{ty:.1f}) scale({k:.5f})">{body}</g></svg>\n')
os.makedirs(f"{here}/svg", exist_ok=True); os.makedirs(f"{here}/png", exist_ok=True)
variants = {
    "app-icon-dark": icon(f"{here}/svg/aawen-mark-on-dark.svg", "#123F46"),
    "app-icon-light": icon(f"{here}/svg/aawen-mark.svg", "#F6F3EC"),
    "app-icon-dark-square": icon(f"{here}/svg/aawen-mark-on-dark.svg", "#123F46", rounded=False),  # stores apply their own mask
    "maskable-icon": icon(f"{here}/svg/aawen-mark-on-dark.svg", "#123F46", rounded=False, pad=0.24),
}
for name, svg in variants.items():
    open(f"{here}/svg/{name}.svg", "w").write(svg)
for size in (1024, 512, 192, 180, 96, 48, 32):
    cairosvg.svg2png(bytestring=variants["app-icon-dark"].encode(), write_to=f"{here}/png/app-icon-dark-{size}.png", output_width=size, output_height=size)
for size in (1024, 512, 192):
    cairosvg.svg2png(bytestring=variants["maskable-icon"].encode(), write_to=f"{here}/png/maskable-{size}.png", output_width=size, output_height=size)
cairosvg.svg2png(bytestring=variants["app-icon-dark-square"].encode(), write_to=f"{here}/png/store-icon-1024.png", output_width=1024, output_height=1024)
cairosvg.svg2png(bytestring=variants["app-icon-light"].encode(), write_to=f"{here}/png/app-icon-light-512.png", output_width=512, output_height=512)
cairosvg.svg2png(url=f"{here}/svg/aawen-lockup.svg", write_to=f"{here}/png/aawen-lockup-1200.png", output_width=1200)
print("icons ok")
