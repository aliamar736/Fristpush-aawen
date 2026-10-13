"""Trace brand assets from the reference board into clean vector SVG using potrace.
Classifies pixels to the nearest brand colour, traces each colour layer, and emits SVGs
filled with the exact brand palette.  Usage: python trace_brand.py <board.png> <outdir>"""
import sys, subprocess, tempfile, os, re
from PIL import Image, ImageFilter
import numpy as np

PAL = {"petrol": ((18, 63, 70), "#123F46"), "teal": ((32, 183, 165), "#20B7A5"),
       "yellow": ((244, 181, 68), "#F4B544"), "ivory": ((246, 243, 236), None)}
# extra reference shades observed on the board (gradient/shadow) mapped to their brand colour
EXTRA = [((4, 65, 73), "petrol"), ((10, 50, 58), "petrol"), ((16, 184, 174), "teal"),
         ((60, 200, 185), "teal"), ((242, 174, 69), "yellow"), ((255, 255, 255), "ivory"),
         ((230, 228, 222), "ivory")]

def classify(rgb):
    refs = [(c, k) for k, (c, _) in PAL.items()] + EXTRA
    cols = np.array([c for c, _ in refs], dtype=np.float32)
    names = [k for _, k in refs]
    d = ((rgb[:, :, None, :].astype(np.float32) - cols[None, None]) ** 2).sum(-1)
    idx = d.argmin(-1)
    return np.vectorize(lambda i: names[i])(idx)

def trace_layer(mask, scale, turd=40):
    with tempfile.TemporaryDirectory() as td:
        bmp = os.path.join(td, "m.pbm"); out = os.path.join(td, "o.svg")
        Image.fromarray(np.where(mask, 0, 255).astype(np.uint8)).convert("1").save(bmp)
        subprocess.check_call(["potrace", bmp, "-s", "-o", out, "-t", str(turd), "-a", "1.1",
                               "-O", "0.4", "--flat"])
        svg = open(out).read()
    g = re.search(r"<g transform=\"([^\"]+)\"[^>]*>(.*?)</g>", svg, re.S)
    return g.group(1), re.findall(r'd="([^"]+)"', g.group(2))

def build(board, box, scale, layers, out, blur=1.2):
    im = Image.open(board).convert("RGB").crop(box)
    im = im.resize((im.width * scale, im.height * scale), Image.LANCZOS).filter(ImageFilter.GaussianBlur(blur))
    cls = classify(np.asarray(im))
    w, h = im.width, im.height
    parts = []
    for name in layers:
        m = Image.fromarray(((cls == name) * 255).astype(np.uint8))
        k = max(3, (scale // 2) * 2 + 1)  # morphological opening removes anti-alias fringes
        m = m.filter(ImageFilter.MinFilter(k)).filter(ImageFilter.MaxFilter(k))
        tr, paths = trace_layer(np.asarray(m) > 127, scale)
        fill = PAL[name][1]
        parts.append(f'<g transform="{tr}" fill="{fill}">' + "".join(f'<path d="{p}"/>' for p in paths) + "</g>")
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" role="img" aria-label="عاون">'
           + "".join(parts) + "</svg>\n")
    open(out, "w").write(svg)
    return out

if __name__ == "__main__":
    board, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    # Primary mark (top-left of the board)
    build(board, (42, 58, 334, 318), 6, ["petrol", "teal", "yellow"], f"{outdir}/aawen-mark.svg")
    # Arabic wordmark + tagline + latin name
    build(board, (348, 88, 660, 318), 6, ["petrol", "teal"], f"{outdir}/aawen-wordmark.svg", blur=0.8)
    # Full horizontal lockup (mark + wordmark)
    build(board, (42, 58, 660, 318), 5, ["petrol", "teal", "yellow"], f"{outdir}/aawen-lockup.svg", blur=0.9)
    # Variants for dark backgrounds: petrol parts become ivory (as on the board's dark logo)
    for n in ["aawen-mark", "aawen-lockup", "aawen-wordmark"]:
        src = open(f"{outdir}/{n}.svg").read()
        open(f"{outdir}/{n}-on-dark.svg", "w").write(src.replace('fill="#123F46"', 'fill="#F6F3EC"'))
        open(f"{outdir}/{n}-mono-petrol.svg", "w").write(
            src.replace('fill="#20B7A5"', 'fill="#123F46"').replace('fill="#F4B544"', 'fill="#123F46"'))
    print("ok")
