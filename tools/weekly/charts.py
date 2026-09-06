"""Inline SVG charts for the weekly email. Pure functions, no dependencies.
Render in browsers, Apple Mail, Outlook for Mac and the attached report.html; Gmail web drops SVG, which is why
send.py attaches the HTML as well. Palette from docs/brand/tokens.css (Cobalt for the primary series, Cobalt 300 for
the secondary, Cloud for prior periods, Sage for gains, Red for losses, Gold for attention).
"""
import html

COBALT, COBALT300, COBALT700, CLOUD300, CLOUD500, CLOUD600, CLOUD900 = "#3856e8", "#9db9ff", "#253b85", "#d5dbdf", "#7d8996", "#5f6b7c", "#111827"
SAGE, RED, GOLD, MID = "#7ca982", "#b42318", "#d1a44c", "#0f1730"
F_CODE = "'Source Code Pro', Menlo, Consolas, monospace"
F_BODY = "Inter, -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"


def _nice(v):
    """Round a top-of-axis value up to 1, 2, 2.5, 5 or 10 times a power of ten so gridlines land on clean numbers."""
    import math
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


def line_chart(series, labels, width=616, height=170, y_fmt=_fmt, invert=False, title=None, band_last=True):
    """series: [{"name","values":[...],"color","width"}]; labels: x labels (week starts). Last point is the current week.
    invert=True draws lower values higher (average position). Missing values (None) break the line."""
    pad_l, pad_r, pad_t, pad_b = 44, 14, 22 if title else 10, 26
    w, h = width - pad_l - pad_r, height - pad_t - pad_b
    vals = [v for s in series for v in s["values"] if v is not None]
    if not vals:
        return ""
    lo, hi = 0, max(vals) * (1.1 if invert else 1.15) or 1
    hi = _nice(hi)
    n = max(len(labels), 2)
    def x(i):
        return pad_l + i * w / (n - 1)
    def y(v):
        t = (v - lo) / (hi - lo) if hi != lo else 0.5
        return pad_t + (t * h if invert else (1 - t) * h)
    parts = [f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" style="display:block;max-width:100%;font-family:{F_CODE}">']
    if title:
        parts.append(f'<text x="{pad_l}" y="14" font-size="11" font-weight="600" fill="{CLOUD600}" font-family="{F_BODY}" letter-spacing=".06em">{html.escape(title.upper())}</text>')
    # gridlines: 3
    for k in range(4):
        gv = lo + (hi - lo) * k / 3
        gy = y(gv)
        parts.append(f'<line x1="{pad_l}" x2="{width - pad_r}" y1="{gy:.1f}" y2="{gy:.1f}" stroke="{CLOUD300}" stroke-width="1" stroke-dasharray="2 3"/>')
        parts.append(f'<text x="{pad_l - 6}" y="{gy + 3:.1f}" font-size="10" fill="{CLOUD500}" text-anchor="end">{html.escape(y_fmt(round(gv, 1)))}</text>')
    if band_last and n >= 2:
        parts.append(f'<rect x="{x(n - 2):.1f}" y="{pad_t}" width="{x(n - 1) - x(n - 2):.1f}" height="{h}" fill="{COBALT}" opacity="0.06"/>')
    for s in series:
        pts, segs = [], []
        for i, v in enumerate(s["values"][:n]):
            if v is None:
                if pts: segs.append(pts); pts = []
                continue
            pts.append(f"{x(i):.1f},{y(v):.1f}")
        if pts: segs.append(pts)
        for seg in segs:
            parts.append(f'<polyline fill="none" stroke="{s.get("color", COBALT)}" stroke-width="{s.get("width", 2)}" stroke-linejoin="round" stroke-linecap="round" points="{" ".join(seg)}"/>')
        last = [(i, v) for i, v in enumerate(s["values"][:n]) if v is not None]
        if last:
            i, v = last[-1]
            parts.append(f'<circle cx="{x(i):.1f}" cy="{y(v):.1f}" r="3.5" fill="{s.get("color", COBALT)}"/>')
            parts.append(f'<text x="{min(x(i) + 6, width - 2):.1f}" y="{y(v) - 6:.1f}" font-size="11" font-weight="600" fill="{s.get("color", COBALT)}" text-anchor="{"end" if i == n - 1 else "start"}">{html.escape(y_fmt(v))}</text>')
    for i, lab in enumerate(labels):
        if i % 2 == 0 or i == n - 1:
            anchor = "end" if i == n - 1 else "start" if i == 0 else "middle"
            parts.append(f'<text x="{x(i):.1f}" y="{height - 8}" font-size="10" fill="{CLOUD500}" text-anchor="{anchor}">{html.escape(lab)}</text>')
    parts.append("</svg>")
    legend = " ".join(f'<span style="display:inline-block;margin-right:14px;font:600 11px/16px {F_BODY};color:{CLOUD600}"><span style="display:inline-block;width:18px;height:3px;background:{s.get("color", COBALT)};vertical-align:middle;margin-right:6px"></span>{html.escape(s["name"])}</span>' for s in series)
    return "".join(parts) + f'<div style="margin:2px 0 0 44px">{legend}</div>'


def funnel_chart(steps, width=300, title="", color=COBALT):
    """steps: [(label, value)] top to bottom. Centered horizontal bars proportional to the first step, with step-to-step
    conversion written on the right. Reads as a funnel without needing a chart library."""
    if not steps or not steps[0][1]:
        return f'<p style="font:400 12px/18px {F_BODY};color:{CLOUD600}">No {html.escape(title.lower())} visitors this window.</p>'
    top = steps[0][1]
    row_h, gap, label_w, right_w = 30, 8, 118, 66
    bar_w = width - label_w - right_w
    height = len(steps) * (row_h + gap) + (24 if title else 4)
    parts = [f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" style="display:block;max-width:100%;font-family:{F_BODY}">']
    y0 = 20 if title else 0
    if title:
        parts.append(f'<text x="0" y="13" font-size="13" font-weight="700" fill="{MID}" font-family="Archivo, Arial, sans-serif">{html.escape(title)}</text>')
    for i, (lab, v) in enumerate(steps):
        y = y0 + i * (row_h + gap)
        frac = (v / top) if top else 0
        bw = max(3, bar_w * frac) if v else 0
        bx = label_w + (bar_w - bw) / 2
        parts.append(f'<text x="{label_w - 8}" y="{y + row_h / 2 + 4}" font-size="12" fill="{CLOUD900}" text-anchor="end">{html.escape(lab)}</text>')
        parts.append(f'<rect x="{label_w}" y="{y}" width="{bar_w}" height="{row_h}" rx="4" fill="#f3f5f6"/>')
        if v:
            parts.append(f'<rect x="{bx:.1f}" y="{y}" width="{bw:.1f}" height="{row_h}" rx="4" fill="{color}" opacity="{0.55 + 0.45 * frac:.2f}"/>')
        parts.append(f'<text x="{label_w + bar_w / 2}" y="{y + row_h / 2 + 4}" font-size="12" font-weight="700" fill="{"#ffffff" if frac > 0.45 else CLOUD900}" text-anchor="middle" font-family="{F_CODE}">{_fmt(v)}</text>')
        if i > 0:
            parts.append(f'<text x="{width - 2}" y="{y + row_h / 2 + 4}" font-size="11" fill="{CLOUD600}" text-anchor="end" font-family="{F_CODE}">{frac * 100:.0f}% of visitors</text>')
    parts.append("</svg>")
    return "".join(parts)


def bucket_bars(now, prior, labels, width=616):
    """Paired horizontal bars: prior (cloud) vs now (cobalt) per bucket, values at the end."""
    mx = max([*now, *prior, 1])
    row_h, gap, label_w, val_w = 12, 14, 130, 60
    bar_w = width - label_w - val_w
    height = len(labels) * (row_h * 2 + gap) + 6
    parts = [f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" style="display:block;max-width:100%;font-family:{F_BODY}">']
    for i, lab in enumerate(labels):
        y = i * (row_h * 2 + gap)
        parts.append(f'<text x="{label_w - 8}" y="{y + row_h + 4}" font-size="12" fill="{CLOUD900}" text-anchor="end">{html.escape(lab)}</text>')
        parts.append(f'<rect x="{label_w}" y="{y}" width="{bar_w * prior[i] / mx:.1f}" height="{row_h - 2}" rx="2" fill="{CLOUD300}"/>')
        parts.append(f'<rect x="{label_w}" y="{y + row_h}" width="{bar_w * now[i] / mx:.1f}" height="{row_h - 2}" rx="2" fill="{COBALT}"/>')
        d = now[i] - prior[i]
        parts.append(f'<text x="{label_w + bar_w * now[i] / mx + 6:.1f}" y="{y + row_h * 2 - 3}" font-size="11" font-weight="600" fill="{SAGE if d > 0 else RED if d < 0 else CLOUD600}" font-family="{F_CODE}">{_fmt(now[i])} ({"+" if d > 0 else ""}{d})</text>')
    parts.append("</svg>")
    parts.append(f'<div style="margin-left:{label_w}px;font:600 11px/16px {F_BODY};color:{CLOUD600}"><span style="display:inline-block;width:14px;height:8px;background:{CLOUD300};margin-right:6px"></span>prior 28d <span style="display:inline-block;width:14px;height:8px;background:{COBALT};margin:0 6px 0 14px"></span>last 28d</div>')
    return "".join(parts)
