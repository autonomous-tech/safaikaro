"""PNG charts for the weekly email, drawn with Pillow at 2x for retina, brand fonts bundled in fonts/.
Every function returns PNG bytes; send.py publishes them (R2) or inlines them (data URI) and writes the <img>.
Palette from docs/brand/tokens.css: Cobalt primary, Cobalt 300 secondary, Cloud for prior periods, Sage gains,
Red losses, Gold attention. Email clients render <img> everywhere; SVG did not survive Gmail.
"""
import io, math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONTS = Path(__file__).resolve().parent / "fonts"
COBALT, COBALT300, COBALT700, CLOUD100, CLOUD200, CLOUD300, CLOUD500, CLOUD600, CLOUD900 = "#3856e8", "#9db9ff", "#253b85", "#f3f5f6", "#e7ebed", "#d5dbdf", "#7d8996", "#5f6b7c", "#111827"
SAGE, RED, GOLD, MID, WHITE = "#7ca982", "#b42318", "#d1a44c", "#0f1730", "#ffffff"
S = 2  # supersampling scale


def _font(name, size):
    try:
        return ImageFont.truetype(str(FONTS / name), int(size * S))
    except OSError:
        return ImageFont.load_default()


F_BODY, F_BODY_B, F_HEAD, F_CODE = (lambda s: _font("Inter-Regular.ttf", s)), (lambda s: _font("Inter-Semibold.ttf", s)), (lambda s: _font("Archivo-Bold.ttf", s)), (lambda s: _font("SourceCodePro-Medium.ttf", s))


def _nice(v):
    if v <= 0:
        return 1
    mag = 10 ** math.floor(math.log10(v))
    for m in (1, 2, 2.5, 3, 4, 5, 6, 8, 10):
        if m * mag >= v:
            return m * mag
    return 10 * mag


def _fmt(v):
    if v is None:
        return ""
    if isinstance(v, float) and not v.is_integer():
        return f"{v:.1f}"
    return f"{int(v):,}"


def _png(im):
    im = im.resize((im.width // S, im.height // S), Image.LANCZOS)
    buf = io.BytesIO(); im.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def _text(d, xy, s, font, fill, anchor="la"):
    d.text((xy[0] * S, xy[1] * S), s, font=font, fill=fill, anchor=anchor)


def line_chart(series, labels, width=616, height=190, y_fmt=_fmt, invert=False, title=None, band_last=True):
    """series: [{"name","values":[...],"color"}]; labels: x labels. None values break the line. invert: lower is better."""
    pad_l, pad_r, pad_t, pad_b = 48, 16, 30 if title else 12, 44
    w, h = width - pad_l - pad_r, height - pad_t - pad_b
    vals = [v for s in series for v in s["values"] if v is not None]
    if not vals:
        return None
    lo, hi = 0, _nice(max(vals) * (1.1 if invert else 1.15) or 1)
    n = max(len(labels), 2)
    x = lambda i: pad_l + i * w / (n - 1)
    y = lambda v: pad_t + ((v - lo) / (hi - lo) * h if invert else (1 - (v - lo) / (hi - lo)) * h)
    im = Image.new("RGB", (width * S, height * S), WHITE); d = ImageDraw.Draw(im)
    if title:
        _text(d, (pad_l, 6), title.upper(), F_BODY_B(11), CLOUD600)
    for k in range(4):
        gv = lo + (hi - lo) * k / 3; gy = y(gv)
        for xx in range(int(pad_l * S), int((width - pad_r) * S), 8 * S):
            d.line([(xx, gy * S), (xx + 3 * S, gy * S)], fill=CLOUD300, width=S)
        _text(d, (pad_l - 8, gy), y_fmt(round(gv, 1)), F_CODE(10), CLOUD500, "rm")
    if band_last and n >= 2:
        d.rectangle([x(n - 2) * S, pad_t * S, x(n - 1) * S, (pad_t + h) * S], fill="#eef1ff")
    for s in series:
        col = s.get("color", COBALT); pts = []
        segs = []
        for i, v in enumerate(s["values"][:n]):
            if v is None:
                if pts: segs.append(pts); pts = []
                continue
            pts.append((x(i) * S, y(v) * S))
        if pts: segs.append(pts)
        for seg in segs:
            if len(seg) > 1:
                d.line(seg, fill=col, width=int(2.2 * S), joint="curve")
        last = [(i, v) for i, v in enumerate(s["values"][:n]) if v is not None]
        if last:
            i, v = last[-1]; cx, cy = x(i) * S, y(v) * S
            d.ellipse([cx - 4 * S, cy - 4 * S, cx + 4 * S, cy + 4 * S], fill=col)
            _text(d, (x(i) + (0 if i == n - 1 else 7), y(v) - 8), y_fmt(v), F_CODE(11), col, "rd" if i == n - 1 else "ld")
    for i, lab in enumerate(labels):
        if i % 2 == 0 or i == n - 1:
            _text(d, (x(i), height - pad_b + 10), lab, F_CODE(10), CLOUD500, "ra" if i == n - 1 else "la" if i == 0 else "ma")
    lx = pad_l
    for s in series:
        col = s.get("color", COBALT)
        d.line([(lx * S, (height - 12) * S), ((lx + 18) * S, (height - 12) * S)], fill=col, width=3 * S)
        _text(d, (lx + 24, height - 12), s["name"], F_BODY_B(11), CLOUD600, "lm")
        lx += 24 + int(d.textlength(s["name"], font=F_BODY_B(11)) / S) + 18
    return _png(im)


def funnel_chart(steps, width=300, title="", color=COBALT):
    """steps: [(label, value)] top to bottom; bars proportional to the first step, right column = share of the first."""
    if not steps or not steps[0][1]:
        return None
    top = steps[0][1]
    row_h, gap, label_w, right_w = 30, 8, 118, 74
    bar_w = width - label_w - right_w
    y0 = 26 if title else 2
    height = y0 + len(steps) * (row_h + gap)
    im = Image.new("RGB", (width * S, height * S), WHITE); d = ImageDraw.Draw(im)
    if title:
        _text(d, (0, 2), title, F_HEAD(13), MID)
    for i, (lab, v) in enumerate(steps):
        yy = y0 + i * (row_h + gap); frac = v / top if top else 0
        bw = max(3, bar_w * frac) if v else 0; bx = label_w + (bar_w - bw) / 2
        _text(d, (label_w - 8, yy + row_h / 2), lab, F_BODY(12), CLOUD900, "rm")
        d.rounded_rectangle([label_w * S, yy * S, (label_w + bar_w) * S, (yy + row_h) * S], radius=4 * S, fill=CLOUD100)
        if v:
            shade = Image.new("RGB", (1, 1), color).getpixel((0, 0))
            mix = tuple(int(c * (0.55 + 0.45 * frac) + 255 * (1 - (0.55 + 0.45 * frac))) for c in shade)
            d.rounded_rectangle([bx * S, yy * S, (bx + bw) * S, (yy + row_h) * S], radius=4 * S, fill=mix)
        _text(d, (label_w + bar_w / 2, yy + row_h / 2), _fmt(v), F_CODE(12), WHITE if frac > 0.45 else CLOUD900, "mm")
        if i > 0:
            _text(d, (width - 2, yy + row_h / 2), f"{frac * 100:.0f}% of visitors", F_CODE(10), CLOUD600, "rm")
    return _png(im)


def bucket_bars(now, prior, labels, width=616):
    mx = max([*now, *prior, 1])
    row_h, gap, label_w, val_w = 12, 14, 130, 90
    bar_w = width - label_w - val_w
    height = len(labels) * (row_h * 2 + gap) + 22
    im = Image.new("RGB", (width * S, height * S), WHITE); d = ImageDraw.Draw(im)
    for i, lab in enumerate(labels):
        yy = i * (row_h * 2 + gap)
        _text(d, (label_w - 8, yy + row_h), lab, F_BODY(12), CLOUD900, "rm")
        d.rounded_rectangle([label_w * S, yy * S, (label_w + bar_w * prior[i] / mx) * S, (yy + row_h - 2) * S], radius=2 * S, fill=CLOUD300)
        d.rounded_rectangle([label_w * S, (yy + row_h) * S, (label_w + bar_w * now[i] / mx) * S, (yy + row_h * 2 - 2) * S], radius=2 * S, fill=COBALT)
        dd = now[i] - prior[i]
        _text(d, (label_w + bar_w * now[i] / mx + 6, yy + row_h * 1.5 - 1), f"{_fmt(now[i])} ({'+' if dd > 0 else ''}{dd})", F_CODE(11), SAGE if dd > 0 else RED if dd < 0 else CLOUD600, "lm")
    ly = height - 8
    d.rectangle([label_w * S, (ly - 4) * S, (label_w + 14) * S, (ly + 4) * S], fill=CLOUD300); _text(d, (label_w + 20, ly), "prior 28d", F_BODY_B(11), CLOUD600, "lm")
    d.rectangle([(label_w + 90) * S, (ly - 4) * S, (label_w + 104) * S, (ly + 4) * S], fill=COBALT); _text(d, (label_w + 110, ly), "last 28d", F_BODY_B(11), CLOUD600, "lm")
    return _png(im)
