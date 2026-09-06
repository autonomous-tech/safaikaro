#!/usr/bin/env python3
"""send.py: report_data.json + insights.json + changes.json -> output/report.html, and email it via Brevo.

Default is dry-run (writes the HTML only). `--send` posts through Brevo.
Every number rendered comes from report_data.json; insights/changes are the routine agent's JSON.
Design: Autonomous brand (Archivo/Inter/Source Code Pro, Cloud/Midnight/Cobalt/Sage/Gold/Red), email-safe tables,
one trace marker (the Cobalt decision bar), quiet reading pages.
"""
import argparse, datetime as dt, html, json, sys, urllib.error
from pathlib import Path

from common import CONFIG, OUT, HERE, http_json, log, secret

# ─── tokens (from docs/brand/tokens.css) ───
C = dict(cloud50="#fcfcfa", cloud100="#f3f5f6", cloud200="#e7ebed", cloud300="#d5dbdf", cloud500="#7d8996", cloud600="#5f6b7c", cloud700="#3f4a5b",
         cloud900="#111827", mid800="#0f1730", mid900="#0a1024", mid300="#8794ba", cobalt500="#3856e8", cobalt300="#9db9ff", cobalt700="#253b85",
         cobalt50="#eef1ff", sage500="#7ca982", sage50="#edf4ee", sage800="#234d2e", gold500="#d1a44c", gold50="#f9f3e6", gold900="#614815",
         red500="#b42318", red50="#fff0ef", red700="#742b26", white="#ffffff")
F_DISPLAY = "Archivo, 'Arial Narrow', Arial, Helvetica, sans-serif"
F_BODY = "Inter, -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"
F_CODE = "'Source Code Pro', Menlo, Consolas, monospace"


def esc(s):
    return html.escape("" if s is None else str(s))


def n(v, d=0):
    if v is None:
        return "n/a"
    return f"{v:,.{d}f}"


def pct(v, d=1):
    return "n/a" if v is None else f"{v * 100:.{d}f}%"


def pill(delta, unit="%", invert=False, noise=False):
    """Delta pill. invert=True means a negative delta is good (e.g. avg position)."""
    if delta is None:
        return f'<span style="font:600 11px/18px {F_CODE};color:{C["cloud600"]};background:{C["cloud100"]};padding:1px 7px;border-radius:999px;white-space:nowrap">n/a</span>'
    good = (delta < 0) if invert else (delta > 0)
    flat = abs(delta) < 0.05
    bg, fg = (C["cloud100"], C["cloud700"]) if flat else (C["sage50"], C["sage800"]) if good else (C["red50"], C["red700"])
    if noise:
        bg, fg = C["gold50"], C["gold900"]
    sign = "+" if delta > 0 else ""
    txt = f"{sign}{delta:.1f}{unit}" if unit != "pts" else f"{sign}{delta:.1f} pts"
    return f'<span style="font:600 11px/18px {F_CODE};color:{fg};background:{bg};padding:1px 7px;border-radius:999px;white-space:nowrap">{txt}</span>'


def badge(text, tone="cloud"):
    tones = {"cloud": (C["cloud100"], C["cloud700"]), "sage": (C["sage50"], C["sage800"]), "gold": (C["gold50"], C["gold900"]),
             "red": (C["red50"], C["red700"]), "cobalt": (C["cobalt50"], C["cobalt700"])}
    bg, fg = tones[tone]
    return f'<span style="display:inline-block;font:600 11px/18px {F_CODE};letter-spacing:.02em;color:{fg};background:{bg};padding:1px 8px;border-radius:999px;white-space:nowrap">{esc(text)}</span>'


def bar(value, max_value, color=None, width=120):
    w = 0 if not max_value or not value else max(2, round(width * min(value / max_value, 1)))
    color = color or C["cobalt500"]
    return (f'<table role="presentation" cellpadding="0" cellspacing="0" style="width:{width}px;border-collapse:collapse"><tr>'
            f'<td style="width:{w}px;height:8px;background:{color};border-radius:2px;font-size:0;line-height:0">&nbsp;</td>'
            f'<td style="height:8px;background:{C["cloud200"]};font-size:0;line-height:0">&nbsp;</td></tr></table>')


def section(eyebrow, title, body, note=None):
    note_html = f'<p style="margin:4px 0 0;font:400 13px/20px {F_BODY};color:{C["cloud600"]}">{note}</p>' if note else ""
    return f'''<tr><td style="padding:28px 32px 8px;border-top:1px solid {C["cloud200"]}">
      <p style="margin:0;font:600 11px/16px {F_BODY};letter-spacing:.08em;text-transform:uppercase;color:{C["cloud600"]}">{esc(eyebrow)}</p>
      <h2 style="margin:4px 0 0;font:700 20px/26px {F_DISPLAY};letter-spacing:-.01em;color:{C["mid800"]}">{esc(title)}</h2>{note_html}</td></tr>
      <tr><td style="padding:12px 32px 24px">{body}</td></tr>'''


def th(t, align="left"):
    return f'<th scope="col" style="text-align:{align};padding:6px 8px;font:600 11px/16px {F_BODY};letter-spacing:.04em;text-transform:uppercase;color:{C["cloud600"]};border-bottom:1px solid {C["cloud300"]}">{esc(t)}</th>'


def td(t, align="left", mono=False, strong=False, color=None):
    font = f"{'600' if strong else '400'} 13px/20px {F_CODE if mono else F_BODY}"
    st = f'text-align:{align};padding:7px 8px;font:{font};color:{color or C["cloud900"]};border-bottom:1px solid {C["cloud200"]};vertical-align:top;'
    if mono:
        st += "font-variant-numeric:tabular-nums;"
    return f'<td style="{st}">{t}</td>'


def table(head, rows, widths=None):
    hs = "".join(head)
    body = "".join(f"<tr>{''.join(r)}</tr>" for r in rows) or f'<tr><td colspan="{len(head)}" style="padding:12px 8px;font:400 13px/20px {F_BODY};color:{C["cloud600"]}">No rows this window.</td></tr>'
    return f'<table role="presentation" cellpadding="0" cellspacing="0" style="width:100%;border-collapse:collapse"><thead><tr>{hs}</tr></thead><tbody>{body}</tbody></table>'


def stat_tile(label, value, sub, delta_html):
    return f'''<td style="width:33%;padding:0 6px;vertical-align:top"><table role="presentation" cellpadding="0" cellspacing="0" style="width:100%;border-collapse:collapse;background:{C["cloud50"]};border:1px solid {C["cloud200"]};border-radius:12px"><tr><td style="padding:16px 16px 14px">
      <p style="margin:0;font:600 11px/16px {F_BODY};letter-spacing:.06em;text-transform:uppercase;color:{C["cloud600"]}">{esc(label)}</p>
      <p style="margin:6px 0 2px;font:800 30px/32px {F_DISPLAY};letter-spacing:-.03em;color:{C["mid800"]};font-variant-numeric:tabular-nums">{esc(value)}</p>
      <p style="margin:0;font:400 12px/18px {F_BODY};color:{C["cloud600"]}">{esc(sub)} {delta_html}</p></td></tr></table></td>'''


def para(t, size=14, color=None, weight=400, margin="0 0 10px"):
    return f'<p style="margin:{margin};font:{weight} {size}px/{round(size * 1.55)}px {F_BODY};color:{color or C["cloud900"]}">{t}</p>'


def mono(t, color=None):
    return f'<span style="font:400 11px/16px {F_CODE};color:{color or C["cloud600"]}">{esc(t)}</span>'


def sparkline(daily, key, color, width=536, height=36):
    """Inline SVG sparkline (renders in Apple Mail, Outlook for Mac, browsers; degrades to nothing elsewhere)."""
    vals = [d.get(key, 0) or 0 for d in daily]
    if len(vals) < 2:
        return ""
    mx = max(vals) or 1
    step = width / (len(vals) - 1)
    pts = " ".join(f"{i * step:.1f},{height - (v / mx) * (height - 4) - 2:.1f}" for i, v in enumerate(vals))
    return (f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" style="display:block;max-width:100%">'
            f'<polyline fill="none" stroke="{color}" stroke-width="2" stroke-linejoin="round" points="{pts}"/></svg>')


# ─── sections ───
def render(D, I, CH, pr_url=None):
    ph, g, a, h, cro = D.get("posthog") or {}, D.get("gsc") or {}, D.get("ahrefs") or {}, D.get("health") or {}, D.get("cro") or {}
    W = D["windows"]; tw = W["this_week"]
    noise = (ph.get("data_quality") or {}).get("sample_warning", True)
    fd = ph.get("funnel_deltas") or {}
    f = ph.get("funnel") or {}
    parts = []

    # header
    week_range = f"{dt.date.fromisoformat(tw[0]).strftime('%b %d')} to {dt.date.fromisoformat(tw[1]).strftime('%b %d, %Y')}"
    parts.append(f'''<tr><td style="background:{C["mid800"]};padding:28px 32px 22px">
      <table role="presentation" cellpadding="0" cellspacing="0" style="width:100%"><tr>
        <td style="vertical-align:bottom"><p style="margin:0;font:800 15px/18px {F_DISPLAY};letter-spacing:.14em;text-transform:uppercase;color:{C["white"]}">Autonomous</p>
          <p style="margin:10px 0 0;font:700 26px/30px {F_DISPLAY};letter-spacing:-.02em;color:{C["white"]}">SafaiKaro weekly growth report</p></td>
        <td style="vertical-align:bottom;text-align:right"><p style="margin:0;font:600 12px/16px {F_CODE};color:{C["cobalt300"]}">{esc(D["week"])}</p>
          <p style="margin:4px 0 0;font:400 12px/16px {F_CODE};color:{C["mid300"]}">{esc(week_range)}</p></td></tr></table></td></tr>
      <tr><td style="padding:0;font-size:0;line-height:0"><table role="presentation" cellpadding="0" cellspacing="0" style="width:100%;border-collapse:collapse"><tr>
        <td style="width:62%;height:5px;background:{C["cobalt500"]}"></td><td style="width:24%;height:5px;background:{C["cobalt300"]}"></td><td style="height:5px;background:{C["gold500"]}"></td></tr></table></td></tr>''')

    # verdict + headline tiles
    tot_tw, tot_lw = (f.get("this_week") or {}).get("total", {}), (f.get("last_week") or {}).get("total", {})
    gsc_tw, gsc_lw = (g.get("totals") or {}).get("this_week", {}), (g.get("totals") or {}).get("last_week", {})
    tiles = "".join([
        stat_tile("Lead persons", n(tot_tw.get("lead_persons")), f"vs {n(tot_lw.get('lead_persons'))} last week", pill((fd.get("total") or {}).get("lead_persons_wow"), noise=noise)),
        stat_tile("Visitor to lead", pct(tot_tw.get("lead_rate")), f"mobile {pct((f.get('this_week') or {}).get('mobile', {}).get('lead_rate'))} · desktop {pct((f.get('this_week') or {}).get('desktop', {}).get('lead_rate'))}", pill((fd.get("total") or {}).get("lead_rate_wow_pts"), "pts", noise=noise)),
        stat_tile("Organic clicks", n(gsc_tw.get("clicks")), f"{n(gsc_tw.get('impressions'))} impressions", pill((g.get("deltas") or {}).get("clicks", {}).get("wow"))),
    ])
    noise_line = para(f'{badge("inside noise", "gold")} Fewer than {CONFIG["thresholds"]["min_lead_persons_for_rates"]} lead persons this week. Rate deltas are shown but not trended.', 12, C["cloud600"], margin="10px 0 0") if noise else ""
    parts.append(f'''<tr><td style="padding:28px 32px 8px">
      <p style="margin:0;font:600 11px/16px {F_BODY};letter-spacing:.08em;text-transform:uppercase;color:{C["cobalt500"]}">Verdict</p>
      <p style="margin:8px 0 18px;font:600 19px/28px {F_DISPLAY};letter-spacing:-.01em;color:{C["mid800"]}">{esc(I.get("narrative", ""))}</p>
      <table role="presentation" cellpadding="0" cellspacing="0" style="width:100%;border-collapse:separate;border-spacing:0"><tr>{tiles}</tr></table>{noise_line}</td></tr>''')

    # approve PR block (top, so the action is one scroll away)
    parts.append(pr_block(CH, pr_url))

    # funnel by device
    steps = [("Visitors", "visitors"), ("Pageviews", "pageviews"), ("Booking started", "booking_started"), ("Area selected", "area_selected"), ("Handoff to WhatsApp", "handoff"), ("Lead persons", "lead_persons")]
    def funnel_col(dev, label):
        cur, prev = (f.get("this_week") or {}).get(dev, {}), (f.get("last_week") or {}).get(dev, {})
        m28, p28 = (f.get("last_28d") or {}).get(dev, {}), (f.get("prior_28d") or {}).get(dev, {})
        mx = cur.get("visitors") or 1
        rows = []
        for name, k in steps:
            v, pv = cur.get(k, 0), prev.get(k, 0)
            rows.append([td(esc(name)), td(bar(v, mx)), td(n(v), "right", mono=True, strong=True), td(n(pv), "right", mono=True, color=C["cloud600"]), td(pill(None if not pv else round((v - pv) / pv * 100, 1), noise=noise), "right")])
        rows.append([td("Lead rate", strong=True), td(""), td(pct(cur.get("lead_rate")), "right", mono=True, strong=True), td(pct(prev.get("lead_rate")), "right", mono=True, color=C["cloud600"]), td(pill((fd.get(dev) or {}).get("lead_rate_wow_pts"), "pts", noise=noise), "right")])
        rows.append([td("28d leads (MoM)", color=C["cloud600"]), td(""), td(n(m28.get("lead_persons")), "right", mono=True), td(n(p28.get("lead_persons")), "right", mono=True, color=C["cloud600"]), td(pill((fd.get(dev) or {}).get("lead_persons_mom")), "right")])
        return f'<p style="margin:0 0 6px;font:700 14px/20px {F_DISPLAY};color:{C["mid800"]}">{label} <span style="font:400 12px/20px {F_CODE};color:{C["cloud600"]}">{n(cur.get("visitors"))} visitors</span></p>' + table([th("Step"), th(""), th("This wk", "right"), th("Last wk", "right"), th("WoW", "right")], rows)
    clicks = f'WhatsApp {n(tot_tw.get("wa_clicks"))} · Book {n(tot_tw.get("book_clicks"))} · Call {n(tot_tw.get("call_clicks"))} clicks this week. Leads are persons who fired any lead event; clicks count events.'
    spark = sparkline(ph.get("daily") or [], "lead_persons", C["cobalt500"])
    parts.append(section("Funnel", "Web and mobile, separately", funnel_col("mobile", "Mobile") + '<div style="height:18px"></div>' + funnel_col("desktop", "Desktop") +
                         f'<div style="height:14px"></div>{para(clicks, 12, C["cloud600"])}<p style="margin:10px 0 2px;font:600 11px/16px {F_BODY};letter-spacing:.06em;text-transform:uppercase;color:{C["cloud600"]}">Lead persons per day, last 28 days</p>{spark}',
                         note=f'PostHog, Karachi visitors only, test IDs excluded. Windows {tw[0]} to {tw[1]} vs prior week.'))

    # areas: 28d set with a this-week column (a single week is usually too thin for area pages)
    ar28 = (ph.get("areas") or {}).get("last_28d", [])[:12]
    artw = {r["area"]: r for r in (ph.get("areas") or {}).get("this_week", [])}
    arp28 = {r["area"]: r for r in (ph.get("areas") or {}).get("prior_28d", [])}
    rows = [[td(esc(r["area"].replace("-", " ").title()), strong=True), td(n(r["landing_sessions"]), "right", mono=True), td(n(r["lead_persons"]), "right", mono=True, strong=True),
             td(pct(r.get("lead_rate")), "right", mono=True), td(n(r["area_selected"]), "right", mono=True), td(n(artw.get(r["area"], {}).get("lead_persons", 0)), "right", mono=True),
             td(pill(float(r["lead_persons"] - arp28.get(r["area"], {}).get("lead_persons", 0)), ""), "right")] for r in ar28]
    area_note = ("Area = the area page a session landed on, the booking dropdown choice, or the area in the WhatsApp prefill. PostHog geo stops at city, so this is intent by area, not location. "
                 f"Karachi vs other cities this month: {', '.join(f'{c['city']} {c['persons']}' for c in (ph.get('data_quality') or {}).get('city_split_28d', [])[:4])}.")
    parts.append(section("Karachi areas", "Traffic and leads by area, last 28 days", table([th("Area"), th("Sessions", "right"), th("Leads", "right"), th("Rate", "right"), th("Dropdown", "right"), th("This wk", "right"), th("MoM", "right")], rows), note=area_note))

    # pages
    pg = sorted((ph.get("pages") or {}).get("last_28d", []), key=lambda r: -(r.get("uv") or 0))[:12]
    rows = [[td(esc(r["path"]), mono=True), td(n(r["uv"]), "right", mono=True), td(n(r["lead_persons"]), "right", mono=True, strong=True), td(pct(r.get("lead_rate")), "right", mono=True),
             td((badge(f'{r["vs_site_avg"]}x', "sage" if r["vs_site_avg"] >= 1 else "red" if r["vs_site_avg"] < 0.7 else "cloud") if r.get("vs_site_avg") is not None else ""), "right"),
             td(n(r.get("scroll_p50")) + ("%" if r.get("scroll_p50") is not None else ""), "right", mono=True, color=C["cloud600"])] for r in pg]
    parts.append(section("Pages", "Where visitors convert, last 28 days", table([th("Page"), th("Visitors", "right"), th("Leads", "right"), th("Rate", "right"), th("vs site", "right"), th("Scroll p50", "right")], rows)))

    # SEO
    gt, gd = g.get("totals") or {}, g.get("deltas") or {}
    kpis = "".join([
        stat_tile("Clicks 28d", n(gt.get("last_28d", {}).get("clicks")), f"prior {n(gt.get('prior_28d', {}).get('clicks'))}", pill(gd.get("clicks", {}).get("mom"))),
        stat_tile("Impressions 28d", n(gt.get("last_28d", {}).get("impressions")), f"prior {n(gt.get('prior_28d', {}).get('impressions'))}", pill(gd.get("impressions", {}).get("mom"))),
        stat_tile("Avg position", n(gt.get("last_28d", {}).get("position"), 1), f"CTR {pct(gt.get('last_28d', {}).get('ctr'), 2)}", pill(gd.get("position", {}).get("mom"), "", invert=True)),
    ])
    b, bp = (g.get("buckets") or {}).get("last_28d", {}), (g.get("buckets") or {}).get("prior_28d", {})
    bmx = max([*b.values(), 1]) if b else 1
    brows = [[td(esc(lbl)), td(bar(b.get(k, 0), bmx, C["cobalt500"] if k in ("p1_3", "p4_10") else C["cloud500"])), td(n(b.get(k)), "right", mono=True, strong=True), td(n(bp.get(k)), "right", mono=True, color=C["cloud600"]), td(pill((b.get(k, 0) - bp.get(k, 0)) or 0.0, ""), "right")]
             for lbl, k in (("Positions 1 to 3", "p1_3"), ("Positions 4 to 10", "p4_10"), ("Positions 11 to 20", "p11_20"), ("Beyond 20", "p21_plus"))]
    def mover_rows(ms, up):
        return [[td(esc(m["query"]), strong=True), td(esc(m["page"]), mono=True, color=C["cloud600"]), td(f'{n(m["position_prev"], 1)} → {n(m["position"], 1)}', "right", mono=True),
                 td(pill(m["position_delta"], "", invert=False), "right"), td(pill(m["clicks_delta"], ""), "right")] for m in ms[:8]]
    movers = (f'<p style="margin:14px 0 4px;font:700 13px/18px {F_DISPLAY};color:{C["sage800"]}">Moving up</p>' + table([th("Query"), th("Page"), th("Position", "right"), th("Δ pos", "right"), th("Δ clicks", "right")], mover_rows(g.get("movers_up", []), True)) +
              f'<p style="margin:14px 0 4px;font:700 13px/18px {F_DISPLAY};color:{C["red700"]}">Slipping</p>' + table([th("Query"), th("Page"), th("Position", "right"), th("Δ pos", "right"), th("Δ clicks", "right")], mover_rows(g.get("movers_down", []), False)))
    sd = g.get("striking_distance", [])[:8]
    srows = [[td(esc(r["query"]), strong=True), td(esc(r["page"]), mono=True, color=C["cloud600"]), td(n(r["position"], 1), "right", mono=True), td(n(r["impressions"]), "right", mono=True), td(pct(r["ctr"], 2), "right", mono=True)] for r in sd]
    site_a = a.get("site") or {}
    comps = sorted([c for c in a.get("competitors", []) if c.get("dr") is not None], key=lambda c: -(c.get("refdomains") or 0))[:4]
    auth = (f'Refdomains <strong>{n(site_a.get("refdomains"))}</strong> (last week {n(site_a.get("refdomains_prev_week"))}), DR {n(site_a.get("dr"))}, '
            f'{n(site_a.get("org_keywords"))} organic keywords in Ahrefs. Competitors: ' + ", ".join(f'{c["domain"]} DR {n(c["dr"])} / {n(c["refdomains"])} refdomains' for c in comps) + ".")
    gaps = a.get("competitor_gaps", [])[:5]
    gap_rows = [[td(esc(x.get("top_keyword")), strong=True), td(n(x.get("top_keyword_volume")), "right", mono=True), td(esc(x.get("competitor")), mono=True, color=C["cloud600"]), td(n(x.get("top_keyword_best_position")), "right", mono=True)] for x in gaps]
    seo_body = (f'<table role="presentation" cellpadding="0" cellspacing="0" style="width:100%;border-collapse:separate;border-spacing:0"><tr>{kpis}</tr></table><div style="height:16px"></div>'
                f'<p style="margin:0 0 4px;font:700 13px/18px {F_DISPLAY};color:{C["mid800"]}">Position buckets, queries this 28d vs prior</p>' + table([th("Bucket"), th(""), th("Now", "right"), th("Prior", "right"), th("Δ", "right")], brows) + movers +
                f'<p style="margin:14px 0 4px;font:700 13px/18px {F_DISPLAY};color:{C["mid800"]}">Striking distance (positions 8 to 20, ≥{CONFIG["thresholds"]["striking_min_impressions"]} impressions)</p>' + table([th("Query"), th("Page"), th("Pos", "right"), th("Impr", "right"), th("CTR", "right")], srows) +
                f'<p style="margin:14px 0 4px;font:700 13px/18px {F_DISPLAY};color:{C["mid800"]}">Authority</p>{para(auth, 13)}' +
                (f'<p style="margin:14px 0 4px;font:700 13px/18px {F_DISPLAY};color:{C["mid800"]}">Competitor keyword gaps (Ahrefs, PK)</p>' + table([th("Keyword"), th("Volume", "right"), th("Who ranks"), th("Pos", "right")], gap_rows) if gap_rows else ""))
    gw = g.get("windows") or {}
    parts.append(section("SEO", "Positions, movers, authority", seo_body, note=f'Search Console {gw.get("this_week", ["", ""])[0]} to {gw.get("this_week", ["", ""])[1]} (3-day lag), Ahrefs as of {esc(a.get("date"))}. Δ pos positive = moved up.'))

    # CRO
    leaks = cro.get("leaks", [])[:6]
    kinds = {"low_lead_rate": "Lead rate below site", "low_scroll": "Low scroll depth", "rageclicks": "Rage clicks", "device_gap": "Device converting below site", "booking_dropoff": "Booking chain drop-off"}
    lrows = []
    for l in leaks:
        detail = {"low_lead_rate": f'{pct(l.get("lead_rate"))} vs site {pct(l.get("site_rate"))} on {n(l.get("uv"))} visitors', "low_scroll": f'median scroll {n(l.get("scroll_p50"))}% on {n(l.get("uv"))} visitors',
                  "rageclicks": f'{n(l.get("rageclicks"))} rage clicks', "device_gap": f'{pct(l.get("lead_rate"))} vs site {pct(l.get("site_rate"))} on {n(l.get("visitors"))} visitors',
                  "booking_dropoff": f'{n(l.get("started"))} started, {n(l.get("handoff"))} handed off ({pct(l.get("completion"))})'}[l["kind"]]
        lrows.append([td(esc(kinds[l["kind"]]), strong=True), td(esc(l["page"]) + (f' <span style="color:{C["cloud600"]}">({esc(l["device"])})</span>' if l.get("device") not in (None, "all") else ""), mono=True), td(esc(detail)), td(n(l.get("lead_gap_persons")) if l.get("lead_gap_persons") else "", "right", mono=True, strong=True)])
    reads = cro.get("ledger_reads", [])
    vtone = {"working": "sage", "flat": "cloud", "worse": "red", "too_early": "gold", "not_on_main": "cloud"}
    rrows = [[td(esc(r["id"]), mono=True), td(esc(r.get("hypothesis") or ""), color=C["cloud700"]), td(f'{n(r.get("days_live"))}d', "right", mono=True),
              td((f'{pct(r["pre"]["rate"])} → {pct(r["post"]["rate"])}' if r.get("pre") and r.get("post") else ""), "right", mono=True), td(badge(r["verdict"].replace("_", " "), vtone.get(r["verdict"], "cloud")), "right")] for r in reads]
    cro_body = (f'<p style="margin:0 0 4px;font:700 13px/18px {F_DISPLAY};color:{C["mid800"]}">Leaks, ranked by lead persons at stake (28d)</p>' + table([th("Leak"), th("Page"), th("Evidence"), th("At stake", "right")], lrows) +
                f'<p style="margin:16px 0 4px;font:700 13px/18px {F_DISPLAY};color:{C["mid800"]}">Ship ledger reads (pre vs post, same-length windows)</p>' + (table([th("Change"), th("Hypothesis"), th("Live", "right"), th("Lead rate", "right"), th("Verdict", "right")], rrows) if rrows else para("No CRO changes on the ledger yet. Every CRO change the routine ships adds one and is read at 7, 14 and 28 days.", 13, C["cloud600"])))
    parts.append(section("CRO", "Leaks and what shipped changes did", cro_body, note="Traffic is too small for split tests. Changes are read sequentially, one per money page in flight."))

    # analyst notes
    notes = I.get("analyst_notes", [])[:6]
    nrows = "".join(f'''<tr><td style="padding:10px 0;border-bottom:1px solid {C["cloud200"]}">
        <p style="margin:0;font:600 14px/20px {F_BODY};color:{C["mid800"]}">{i + 1}. {esc(x.get("observation"))}</p>
        <p style="margin:4px 0 0;font:400 13px/20px {F_BODY};color:{C["cloud700"]}">{esc(x.get("detail", ""))}</p>
        <p style="margin:4px 0 0">{mono(x.get("evidence_ref", ""))} {badge(x.get("action", "noted"), "cobalt" if "ship" in str(x.get("action", "")).lower() else "gold" if "instrument" in str(x.get("action", "")).lower() else "cloud")}</p></td></tr>''' for i, x in enumerate(notes))
    ev = ph.get("events") or {}
    ev_line = (f'New events this week: {", ".join(ev.get("new", [])) or "none"}. ' + (f'Tracking code changed in the last 3 weeks ({len(h.get("instrumentation_commits", []))} commits), so week-over-week event counts straddle a schema change.' if h.get("instrumentation_commits") else ""))
    parts.append(section("Analyst notes", "What the data said when pushed", (f'<table role="presentation" cellpadding="0" cellspacing="0" style="width:100%;border-collapse:collapse">{nrows}</table>' if nrows else para("No analyst notes this run.", 13, C["cloud600"])) + para(ev_line, 12, C["cloud600"], margin="12px 0 0")))

    # suggested changes (not shipped)
    sug = I.get("suggestions", [])[:8]
    srows = [[td(esc(s.get("title")), strong=True), td(esc(s.get("detail", "")), color=C["cloud700"]), td(badge(s.get("owner", "you"), "cobalt" if s.get("owner") == "routine" else "gold"), "right"), td(esc(s.get("effort", "")), "right", mono=True)] for s in sug]
    parts.append(section("Suggested changes", "Needs a human, not shipped", table([th("Change"), th("Why"), th("Owner", "right"), th("Effort", "right")], srows), note="Founder decisions, ops and instrumentation the routine cannot do alone."))

    # shipped this week (actual changes)
    shipped, dropped = CH.get("shipped", []), CH.get("dropped", [])
    shrows = [[td(badge(s.get("type", "change"), "cobalt")), td(esc(s.get("page", "")), mono=True), td(esc(s.get("reason", "")), color=C["cloud700"]), td(badge(s.get("critic", "passed"), "sage" if "pass" in str(s.get("critic", "")).lower() else "gold"), "right")] for s in shipped]
    drows = [[td(badge(s.get("type", "change"), "cloud")), td(esc(s.get("page", "")), mono=True), td(esc(s.get("reason", "")), color=C["cloud700"]), td(badge("dropped", "red"), "right")] for s in dropped]
    ship_body = table([th("Type"), th("Page"), th("Why this change"), th("Critic", "right")], shrows + drows)
    extra = []
    if CH.get("ledger_added"):
        extra.append(f'Ledger entries added: {", ".join(CH["ledger_added"])}.')
    if CH.get("instrumentation_added"):
        extra.append(f'Instrumentation added: {", ".join(CH["instrumentation_added"])}.')
    parts.append(section("Shipped this week", f"{len(shipped)} changes on the branch, {len(dropped)} dropped by the critic", ship_body + (para(" ".join(extra), 12, C["cloud600"], margin="10px 0 0") if extra else ""), note="Each artifact passed builder, critic and lint before entering the PR. Nothing is live until you merge."))

    # health
    hb, sm, tr = h.get("pages_build") or {}, h.get("sitemap") or {}, h.get("tracking") or {}
    behind = hb.get("commits_behind_main")
    chips = [badge(f'build {hb.get("status", "unknown")}', "sage" if hb.get("status") == "built" else "red"),
             badge("live = main" if behind == 0 else f'live is {behind} commits behind main' if behind else "live vs main unknown", "sage" if behind == 0 else "red" if behind else "gold"),
             badge(f'sitemap live {sm.get("live_urls", "?")}/{sm.get("repo_urls", "?")}', "sage" if sm.get("live_urls") == sm.get("repo_urls") else "red"),
             badge("tracking ok" if tr.get("ok") else "tracking gaps", "sage" if tr.get("ok") else "red"),
             badge("schema ok" if not h.get("schema_errors") else f'{len(h["schema_errors"])} schema errors', "sage" if not h.get("schema_errors") else "red")]
    if D.get("errors"):
        chips.append(badge("collector errors: " + ", ".join(D["errors"]), "red"))
    units = ((a.get("units") or {}).get("units_usage_workspace"), (a.get("units") or {}).get("units_limit_workspace"))
    hl = " ".join(chips) + para(f'Head {esc(h.get("head_commit", ""))}. Ahrefs units {n(units[0])} of {n(units[1])} this cycle, {n(a.get("api_calls"))} calls this run.', 12, C["cloud600"], margin="10px 0 0")
    risks = I.get("risks", [])
    if risks:
        hl += para("Risks: " + " ".join(f"{esc(r)}" for r in risks), 13, C["red700"], margin="8px 0 0")
    parts.append(section("Health", "Deploy, tracking, schema", hl))

    # one move
    om = I.get("one_move") or {}
    if om:
        parts.append(f'''<tr><td style="padding:8px 32px 28px"><table role="presentation" cellpadding="0" cellspacing="0" style="width:100%;border-collapse:collapse;background:{C["mid800"]};border-radius:12px"><tr><td style="padding:22px 24px">
          <p style="margin:0;font:600 11px/16px {F_BODY};letter-spacing:.08em;text-transform:uppercase;color:{C["gold500"]}">The one move this week</p>
          <p style="margin:8px 0 6px;font:700 20px/26px {F_DISPLAY};letter-spacing:-.01em;color:{C["white"]}">{esc(om.get("title"))}</p>
          <p style="margin:0;font:400 14px/22px {F_BODY};color:{C["cobalt300"]}">{esc(om.get("detail"))}</p>
          <p style="margin:10px 0 0">{mono(om.get("evidence_ref", ""), C["mid300"])}</p></td></tr></table></td></tr>''')

    # footer
    parts.append(f'''<tr><td style="padding:18px 32px 28px;border-top:1px solid {C["cloud200"]}">
      <p style="margin:0;font:400 11px/17px {F_CODE};color:{C["cloud600"]}">Generated {esc(D.get("generated_at"))} · PostHog project {CONFIG["posthog"]["project_id"]} · {esc(CONFIG["gsc_site"])} · Ahrefs Lite<br>
      Every number in this email exists in report_data.json. Metrics never enter the public site repo or the PR.</p></td></tr>''')

    body = "".join(parts)
    return f'''<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SafaiKaro weekly {esc(D["week"])}</title>
<link href="https://fonts.googleapis.com/css2?family=Archivo:wght@700;800&family=Inter:wght@400;600&family=Source+Code+Pro:wght@400;600&display=swap" rel="stylesheet">
<style>body{{margin:0;padding:0;background:{C["cloud100"]}}} table{{border-collapse:collapse}} a{{color:{C["cobalt500"]}}} @media (max-width:640px){{.wrap{{width:100%!important}} .pad{{padding-left:16px!important;padding-right:16px!important}}}}</style></head>
<body style="margin:0;padding:0;background:{C["cloud100"]}"><table role="presentation" cellpadding="0" cellspacing="0" style="width:100%;background:{C["cloud100"]}"><tr><td style="padding:24px 12px">
<table role="presentation" class="wrap" cellpadding="0" cellspacing="0" align="center" style="width:680px;max-width:100%;background:{C["white"]};border-radius:12px;overflow:hidden;border:1px solid {C["cloud200"]}">{body}</table></td></tr></table></body></html>'''


def pr_block(CH, pr_url):
    url = pr_url or CH.get("pr_url")
    if not url:
        return f'''<tr><td style="padding:8px 32px 20px"><table role="presentation" cellpadding="0" cellspacing="0" style="width:100%;background:{C["gold50"]};border-radius:12px"><tr><td style="padding:16px 20px">
          <p style="margin:0;font:600 14px/20px {F_BODY};color:{C["gold900"]}">No PR this week.</p><p style="margin:4px 0 0;font:400 13px/20px {F_BODY};color:{C["gold900"]}">{esc(CH.get("no_pr_reason", "The growth loop produced nothing that passed the critic and lint."))}</p></td></tr></table></td></tr>'''
    num = url.rstrip("/").split("/")[-1]
    files = url.rstrip("/") + "/files"
    shipped = len(CH.get("shipped", []))
    return f'''<tr><td style="padding:8px 32px 20px"><table role="presentation" cellpadding="0" cellspacing="0" style="width:100%;background:{C["cobalt50"]};border:1px solid {C["cobalt300"]};border-radius:12px"><tr>
      <td style="padding:18px 20px;vertical-align:middle"><p style="margin:0;font:700 16px/22px {F_DISPLAY};color:{C["mid800"]}">PR #{esc(num)} is ready: {shipped} changes waiting for your approval</p>
        <p style="margin:4px 0 0;font:400 13px/20px {F_BODY};color:{C["cloud700"]}">Merge deploys to safaikaro.pk and pings IndexNow. Nothing is live until you merge. <a href="{esc(files)}" style="color:{C["cobalt500"]};font-weight:600">See the diff</a></p></td>
      <td style="padding:18px 20px 18px 0;vertical-align:middle;text-align:right;white-space:nowrap"><a href="{esc(url)}" style="display:inline-block;background:{C["cobalt500"]};color:{C["white"]};font:600 14px/48px {F_BODY};padding:0 22px;border-radius:8px;text-decoration:none">Review and approve PR</a></td></tr></table></td></tr>'''


def subject(D, I, CH, pr_url):
    ph = D.get("posthog") or {}
    tot = ((ph.get("funnel") or {}).get("this_week") or {}).get("total", {})
    d = ((ph.get("funnel_deltas") or {}).get("total") or {}).get("lead_persons_wow")
    dtxt = f" ({'+' if d and d > 0 else ''}{d:.0f}%)" if d is not None else ""
    url = pr_url or CH.get("pr_url")
    prtxt = f" · PR #{url.rstrip('/').split('/')[-1]}" if url else " · no PR"
    return f'{CONFIG["email"]["subject_prefix"]} {D["week"]}: {n(tot.get("lead_persons"))} leads{dtxt}{prtxt}'


def send_brevo(subj, html_body):
    key = secret("BREVO_API_KEY", "brevo-api-key.txt", HERE.parent.parent.parent.parent / "credentials") or secret("BREVO_API_KEY", "brevo-api-key.txt", Path.home() / "Work/autonomous/credentials")
    if not key:
        raise RuntimeError("BREVO_API_KEY missing")
    e = CONFIG["email"]
    payload = {"sender": {"email": e["from"], "name": e["from_name"]}, "to": [{"email": t} for t in e["to"]], "subject": subj, "htmlContent": html_body}
    try:
        r = http_json("https://api.brevo.com/v3/smtp/email", {"api-key": key}, payload)
    except urllib.error.HTTPError as ex:
        raise RuntimeError(f"Brevo {ex.code}: {ex.read().decode()[:300]}")
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--insights", default=str(OUT / "insights.json"))
    ap.add_argument("--changes", default=str(OUT / "changes.json"))
    ap.add_argument("--pr", help="PR url (overrides changes.json)")
    ap.add_argument("--send", action="store_true")
    ap.add_argument("--failure", help="Send a one-line failure note instead of the report")
    a = ap.parse_args()
    e = CONFIG["email"]
    if a.failure:
        subj = f'{e["subject_prefix"]}: collection failed'
        body = f'<p style="font:14px/22px {F_BODY}">{esc(a.failure)}</p>'
        if a.send:
            send_brevo(subj, body)
        log("failure note", "sent" if a.send else "(dry)", subj)
        return 0
    D = json.loads((OUT / "report_data.json").read_text())
    I = json.loads(Path(a.insights).read_text()) if Path(a.insights).exists() else {}
    CH = json.loads(Path(a.changes).read_text()) if Path(a.changes).exists() else {}
    html_body = render(D, I, CH, a.pr)
    (OUT / "report.html").write_text(html_body)
    subj = subject(D, I, CH, a.pr)
    log("wrote", OUT / "report.html", "|", subj)
    if a.send:
        r = send_brevo(subj, html_body)
        log("sent via Brevo:", r)
    return 0


if __name__ == "__main__":
    sys.exit(main())
