"""Builds the AAWEN mark as SVG from rounded polylines (reconstruction of the brand board mark)."""
import math, sys, json

PETROL, TEAL, YELLOW, IVORY = "#123F46", "#20B7A5", "#F4B544", "#F6F3EC"

def rounded(points, r):
    """Open polyline with circular-ish (quadratic) rounded corners of radius r."""
    d = f"M{points[0][0]:.1f},{points[0][1]:.1f}"
    for i in range(1, len(points) - 1):
        p0, p1, p2 = points[i - 1], points[i], points[i + 1]
        def towards(a, b, dist):
            l = math.dist(a, b); t = min(dist / l, 0.5)
            return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
        a = towards(p1, p0, r); b = towards(p1, p2, r)
        d += f" L{a[0]:.1f},{a[1]:.1f} Q{p1[0]:.1f},{p1[1]:.1f} {b[0]:.1f},{b[1]:.1f}"
    d += f" L{points[-1][0]:.1f},{points[-1][1]:.1f}"
    return d

P = json.loads(open(sys.argv[1]).read()) if len(sys.argv) > 1 else {
    "w": 74, "r": 95,
    "petrol": [[318, 300], [400, 168], [272, 52], [62, 258], [190, 402]],
    "teal":   [[178, 222], [355, 408], [552, 240], [462, 140]],
    "dot": [274, 188, 48],
}

def svg(bg=None, halo=IVORY, size=None, vb=(0, 0, 590, 530), mono=None):
    w, r = P["w"], P["r"]
    pp, tp = rounded(P["petrol"], r), rounded(P["teal"], r)
    pc, tc, dc = (mono, mono, mono) if mono else (PETROL, TEAL, YELLOW)
    hal = f'stroke="{halo}"' if halo else 'stroke="none"'
    parts = []
    if bg:
        parts.append(f'<rect x="{vb[0]}" y="{vb[1]}" width="{vb[2]}" height="{vb[3]}" fill="{bg}"/>')
    cap = P.get("cap", "butt")
    parts.append(f'<path d="{pp}" fill="none" stroke="{pc}" stroke-width="{w}" stroke-linecap="{cap}" stroke-linejoin="round"/>')
    if halo:
        parts.append(f'<path d="{tp}" fill="none" {hal} stroke-width="{w + P.get("gap", 24)}" stroke-linecap="{cap}" stroke-linejoin="round"/>')
    parts.append(f'<path d="{tp}" fill="none" stroke="{tc}" stroke-width="{w}" stroke-linecap="{cap}" stroke-linejoin="round"/>')
    x, y, rr = P["dot"]
    parts.append(f'<circle cx="{x}" cy="{y}" r="{rr}" fill="{dc}"/>')
    sz = f' width="{size}" height="{size*vb[3]/vb[2]:.0f}"' if size else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{" ".join(map(str, vb))}"{sz} role="img" aria-label="عاون">'
            + "".join(parts) + "</svg>")

if __name__ == "__main__":
    print(svg(bg=IVORY))
