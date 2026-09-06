#!/usr/bin/env python3
"""send.py: report_data.json + insights.json + changes.json -> output/report.html, and email it via Brevo.

Default is dry-run (writes the HTML only). `--send` posts through Brevo with report.html attached (Gmail drops inline
SVG charts; the attachment opens in a browser with everything). Every number rendered comes from report_data.json;
insights/changes are the routine agent's JSON. Structure runs broad to specific: verdict, actions, 13-week trend,
funnel, where, SEO, CRO, analyst notes, suggestions, health, one move.
Design: Autonomous brand (Archivo/Inter/Source Code Pro; Cloud/Midnight/Cobalt/Sage/Gold/Red), email-safe tables,
one trace marker (the Cobalt decision bar), quiet reading pages.
"""
import argparse, base64, datetime as dt, html, json, sys, urllib.error
from pathlib import Path

import charts, r2
from common import CONFIG, OUT, HERE, http_json, log, secret

_PUBLISH = {"fn": None}


def img(name, png, width=616):
    """Chart bytes -> <img>. Published to R2 when configured (Gmail needs a real URL), else a data URI."""
    if not png:
        return ""
    if _PUBLISH["fn"]:
        try:
            src = _PUBLISH["fn"](name, png)
        except Exception as e:  # never lose the report over an upload
            log("r2 upload failed:", e); src = "data:image/png;base64," + base64.b64encode(png).decode()
    else:
        src = "data:image/png;base64," + base64.b64encode(png).decode()
    return f'<img src="{src}" width="{width}" alt="{esc(name.replace("-", " "))}" style="display:block;width:{width}px;max-width:100%;height:auto;border:0">'

C = dict(cloud50="#fcfcfa", cloud100="#f3f5f6", cloud200="#e7ebed", cloud300="#d5dbdf", cloud500="#7d8996", cloud600="#5f6b7c", cloud700="#3f4a5b",
         cloud900="#111827", mid800="#0f1730", mid300="#8794ba", cobalt500="#3856e8", cobalt300="#9db9ff", cobalt700="#253b85", cobalt50="#eef1ff",
         sage500="#7ca982", sage50="#edf4ee", sage800="#234d2e", gold500="#d1a44c", gold50="#f9f3e6", gold900="#614815", red500="#b42318",
         red50="#fff0ef", red700="#742b26", white="#ffffff")
F_DISPLAY = "Archivo, 'Arial Narrow', Arial, Helvetica, sans-serif"
F_BODY = "Inter, -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"
F_CODE = "'Source Code Pro', Menlo, Consolas, monospace"
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]


# ─── primitives ───
def esc(s):
    return html.escape("" if s is None else str(s))


def n(v, d=0):
    return "n/a" if v is None else f"{v:,.{d}f}"


def pct(v, d=1):
    return "n/a" if v is None else f"{v * 100:.{d}f}%"


def pill(delta, unit="%", invert=False, noise=False):
    if delta is None:
        return f'<span style="font:600 11px/18px {F_CODE};color:{C["cloud600"]};background:{C["cloud100"]};padding:1px 7px;border-radius:999px;white-space:nowrap">n/a</span>'
    good = (delta < 0) if invert else (delta > 0)
    flat = abs(delta) < 0.05
    bg, fg = (C["cloud100"], C["cloud700"]) if flat else (C["sage50"], C["sage800"]) if good else (C["red50"], C["red700"])
    if noise:
        bg, fg = C["gold50"], C["gold900"]
    sign = "+" if delta > 0 else ""
    txt = f"{sign}{delta:.1f} pts" if unit == "pts" else f"{sign}{delta:.1f}{unit}" if unit else f"{sign}{delta:.0f}"
    return f'<span style="font:600 11px/18px {F_CODE};color:{fg};background:{bg};padding:1px 7px;border-radius:999px;white-space:nowrap">{txt}</span>'


def badge(text, tone="cloud"):
    tones = {"cloud": (C["cloud100"], C["cloud700"]), "sage": (C["sage50"], C["sage800"]), "gold": (C["gold50"], C["gold900"]),
             "red": (C["red50"], C["red700"]), "cobalt": (C["cobalt50"], C["cobalt700"])}
    bg, fg = tones[tone]
    return f'<span style="display:inline-block;font:600 11px/18px {F_CODE};letter-spacing:.02em;color:{fg};background:{bg};padding:1px 8px;border-radius:999px;white-space:nowrap">{esc(text)}</span>'


def section(eyebrow, title, insight, body, note=None):
    """Every section opens with one insight line (the agent's read), then the evidence."""
    ins = f'<p style="margin:10px 0 0;padding:10px 14px;border-left:3px solid {C["cobalt500"]};background:{C["cloud50"]};font:600 14px/22px {F_BODY};color:{C["mid800"]}">{esc(insight)}</p>' if insight else ""
    note_html = f'<p style="margin:6px 0 0;font:400 12px/18px {F_BODY};color:{C["cloud600"]}">{note}</p>' if note else ""
    return f'''<tr><td style="padding:30px 32px 6px;border-top:1px solid {C["cloud200"]}">
      <p style="margin:0;font:600 11px/16px {F_BODY};letter-spacing:.08em;text-transform:uppercase;color:{C["cloud600"]}">{esc(eyebrow)}</p>
      <h2 style="margin:4px 0 0;font:700 22px/28px {F_DISPLAY};letter-spacing:-.01em;color:{C["mid800"]}">{esc(title)}</h2>{ins}{note_html}</td></tr>
      <tr><td style="padding:14px 32px 26px">{body}</td></tr>'''


def sub(t):
    return f'<p style="margin:18px 0 6px;font:700 14px/20px {F_DISPLAY};color:{C["mid800"]}">{t}</p>'


def th(t, align="left"):
    return f'<th scope="col" style="text-align:{align};padding:6px 8px;font:600 11px/16px {F_BODY};letter-spacing:.04em;text-transform:uppercase;color:{C["cloud600"]};border-bottom:1px solid {C["cloud300"]}">{esc(t)}</th>'


def td(t, align="left", mono=False, strong=False, color=None):
    font = f"{'600' if strong else '400'} 13px/20px {F_CODE if mono else F_BODY}"
    st = f'text-align:{align};padding:7px 8px;font:{font};color:{color or C["cloud900"]};border-bottom:1px solid {C["cloud200"]};vertical-align:top;'
    return f'<td style="{st}{"font-variant-numeric:tabular-nums;" if mono else ""}">{t}</td>'


def table(head, rows, empty="Nothing in this window."):
    body = "".join(f"<tr>{''.join(r)}</tr>" for r in rows) or f'<tr><td colspan="{len(head)}" style="padding:12px 8px;font:400 13px/20px {F_BODY};color:{C["cloud600"]}">{esc(empty)}</td></tr>'
    return f'<table role="presentation" cellpadding="0" cellspacing="0" style="width:100%;border-collapse:collapse"><thead><tr>{"".join(head)}</tr></thead><tbody>{body}</tbody></table>'


def stat_tile(label, value, sub_text, delta_html):
    return f'''<td style="width:33%;padding:0 6px;vertical-align:top"><table role="presentation" cellpadding="0" cellspacing="0" style="width:100%;border-collapse:collapse;background:{C["cloud50"]};border:1px solid {C["cloud200"]};border-radius:12px"><tr><td style="padding:16px 16px 14px;height:96px;vertical-align:top">
      <p style="margin:0;font:600 11px/16px {F_BODY};letter-spacing:.06em;text-transform:uppercase;color:{C["cloud600"]}">{esc(label)}</p>
      <p style="margin:6px 0 2px;font:800 30px/32px {F_DISPLAY};letter-spacing:-.03em;color:{C["mid800"]};font-variant-numeric:tabular-nums">{esc(value)}</p>
      <p style="margin:0;font:400 12px/18px {F_BODY};color:{C["cloud600"]}">{esc(sub_text)} {delta_html}</p></td></tr></table></td>'''


def para(t, size=14, color=None, weight=400, margin="0 0 10px"):
    return f'<p style="margin:{margin};font:{weight} {size}px/{round(size * 1.55)}px {F_BODY};color:{color or C["cloud900"]}">{t}</p>'


def mono(t, color=None):
    return f'<span style="font:400 11px/16px {F_CODE};color:{color or C["cloud600"]}">{esc(t)}</span>'


def week_label(ws):
    d = dt.date.fromisoformat(ws)
    return f"{d.day} {MONTHS[d.month - 1][:3]}"


# ─── plays: what next for a query, deterministic, agent can override via insights.plays ───
def play_for(m, gaining, plays):
    q, page, pos = m["query"], m["page"], m["position"]
    if q in plays:
        return plays[q]
    if page in CONFIG.get("freshness_pages", []) and not gaining:
        now = dt.date.today()
        return f"Refresh: put '{MONTHS[now.month - 1]} {now.year}' in the title and H1 and an Updated line under the H1 (monthly rule for price pages)."
    if gaining:
        if pos <= 3:
            return "Hold: add a FAQ pair in the query's words, link it from the homepage, leave the title alone."
        if pos <= 10:
            return "Push to top 3: put the exact phrase in the H1 lead, add a definition block, internal link from the hub."
        return "Keep climbing: a section that answers the query, links from two related pages, FAQ schema parity."
    if pos <= 3:
        return "Defend: refresh the date in title and copy, check whether a SERP feature or competitor took the slot, add proof."
    if pos <= 10:
        return "CTR: rewrite title and meta with a price anchor and the 90-day guarantee, exact phrase first."
    if pos <= 20:
        return "Relevance: add a section answering the query, internal links from hub and homepage, FAQ pair."
    return "Authority: this needs a link (citation or directory) or a dedicated page if the intent differs."


# ─── blocks ───
def pr_block(CH, pr_url):
    url = pr_url or CH.get("pr_url")
    if not url:
        return f'''<table role="presentation" cellpadding="0" cellspacing="0" style="width:100%;background:{C["gold50"]};border-radius:12px"><tr><td style="padding:16px 20px">
          <p style="margin:0;font:600 14px/20px {F_BODY};color:{C["gold900"]}">No PR this week.</p><p style="margin:4px 0 0;font:400 13px/20px {F_BODY};color:{C["gold900"]}">{esc(CH.get("no_pr_reason") or "The growth loop produced nothing that passed the critic and lint.")}</p></td></tr></table>'''
    num, files = url.rstrip("/").split("/")[-1], url.rstrip("/") + "/files"
    return f'''<table role="presentation" cellpadding="0" cellspacing="0" style="width:100%;background:{C["cobalt50"]};border:1px solid {C["cobalt300"]};border-radius:12px"><tr>
      <td style="padding:18px 20px;vertical-align:middle"><p style="margin:0;font:700 16px/22px {F_DISPLAY};color:{C["mid800"]}">PR #{esc(num)}: {len(CH.get("shipped", []))} changes waiting for your approval</p>
        <p style="margin:4px 0 0;font:400 13px/20px {F_BODY};color:{C["cloud700"]}">Merge deploys to safaikaro.pk and pings IndexNow. Nothing is live until you merge. <a href="{esc(files)}" style="color:{C["cobalt500"]};font-weight:600">See the diff</a></p></td>
      <td style="padding:18px 20px 18px 0;vertical-align:middle;text-align:right;white-space:nowrap"><a href="{esc(url)}" style="display:inline-block;background:{C["cobalt500"]};color:{C["white"]};font:600 14px/48px {F_BODY};padding:0 22px;border-radius:8px;text-decoration:none">Review and approve PR</a></td></tr></table>'''


TYPE_LABEL = {"blog": "Blog written", "page": "Page built", "meta": "Title and meta rewritten", "area": "Area page upgraded", "cro": "CRO change", "instrumentation": "Tracking added",
              "llms": "llms.txt refreshed", "tooling": "Tooling", "freshness": "Monthly refresh"}


def actions_block(I, CH, pr_url):
    shipped, dropped, planned = CH.get("shipped", []), CH.get("dropped", []), CH.get("planned", [])
    sug = I.get("suggestions", [])[:3]
    def li(tone, head, body):
        return f'<tr><td style="padding:6px 0;vertical-align:top;width:14px"><span style="display:inline-block;width:8px;height:8px;border-radius:99px;background:{tone};margin-top:6px"></span></td><td style="padding:6px 0 6px 8px;font:400 13px/20px {F_BODY};color:{C["cloud900"]}"><strong>{esc(head)}</strong> {esc(body)}</td></tr>'
    done = "".join(li(C["sage500"], TYPE_LABEL.get(s.get("type"), s.get("type", "Change")) + ":", f'{s.get("page", "")}. {s.get("reason", "")}') for s in shipped) or li(C["cloud300"], "Nothing shipped.", "")
    done += "".join(li(C["red500"], "Dropped by red team:", f'{s.get("page", "")}. {s.get("reason", "")}') for s in dropped)
    queued = "".join(li(C["cobalt500"], (TYPE_LABEL.get(p.get("type"), p.get("type", "Change")) + ":") if p.get("type") else "Next run:", f'{p.get("page", "")}. {p.get("reason", "")}') for p in planned) or li(C["cloud300"], "Queue is empty.", "The next run rebuilds it from fresh data.")
    needs = "".join(li(C["gold500"], s.get("title", "") + ":", f'{s.get("detail", "")} ({s.get("owner", "you")}, {s.get("effort", "")})') for s in sug) or li(C["cloud300"], "Nothing needs you this week.", "")
    col = lambda title, rows: f'<p style="margin:0 0 4px;font:700 13px/18px {F_DISPLAY};color:{C["mid800"]}">{title}</p><table role="presentation" cellpadding="0" cellspacing="0" style="width:100%;border-collapse:collapse">{rows}</table>'
    return (col("Done by the routine this week (each item red-teamed, then linted)", done) + '<div style="height:12px"></div>' + col("Queued for the next run (tools/weekly/queue.json, executed first next Monday)", queued) + '<div style="height:12px"></div>' +
            col("Needs you", needs) + '<div style="height:16px"></div>' + pr_block(CH, pr_url))


def play_status(m, CH, Q):
    """shipped / queued / needs you badge for a mover or leak, from changes.json and queue.json."""
    page, query = m.get("page"), m.get("query")
    for s in CH.get("shipped", []):
        if s.get("page") == page:
            return badge("shipped, red team passed", "sage")
    for it in Q:
        if it.get("status") == "queued" and (it.get("page") == page or (query and it.get("query") == query)):
            return badge("queued next run", "cobalt")
        if it.get("status") == "needs_human" and (it.get("page") == page or (query and it.get("query") == query)):
            return badge("needs you", "gold")
    return ""


def render(D, I, CH, pr_url=None):
    ph, g, a, h, cro = D.get("posthog") or {}, D.get("gsc") or {}, D.get("ahrefs") or {}, D.get("health") or {}, D.get("cro") or {}
    Q = json.loads((HERE / "queue.json").read_text()) if (HERE / "queue.json").exists() else []
    _PUBLISH["fn"] = r2.publish_run(D["week"]) if r2.available() else None
    tw = D["windows"]["this_week"]
    noise = (ph.get("data_quality") or {}).get("sample_warning", True)
    fd, f = ph.get("funnel_deltas") or {}, ph.get("funnel") or {}
    SI = I.get("section_insights") or {}
    plays = I.get("plays") or {}
    P = []

    # header
    week_range = f"{dt.date.fromisoformat(tw[0]).strftime('%b %d')} to {dt.date.fromisoformat(tw[1]).strftime('%b %d, %Y')}"
    P.append(f'''<tr><td style="background:{C["mid800"]};padding:28px 32px 22px"><table role="presentation" cellpadding="0" cellspacing="0" style="width:100%"><tr>
        <td style="vertical-align:bottom"><p style="margin:0;font:800 15px/18px {F_DISPLAY};letter-spacing:.14em;text-transform:uppercase;color:{C["white"]}">Autonomous</p>
          <p style="margin:10px 0 0;font:700 26px/30px {F_DISPLAY};letter-spacing:-.02em;color:{C["white"]}">SafaiKaro weekly growth report</p></td>
        <td style="vertical-align:bottom;text-align:right"><p style="margin:0;font:600 12px/16px {F_CODE};color:{C["cobalt300"]}">{esc(D["week"])}</p>
          <p style="margin:4px 0 0;font:400 12px/16px {F_CODE};color:{C["mid300"]}">{esc(week_range)}</p></td></tr></table></td></tr>
      <tr><td style="padding:0;font-size:0;line-height:0"><table role="presentation" cellpadding="0" cellspacing="0" style="width:100%;border-collapse:collapse"><tr>
        <td style="width:62%;height:5px;background:{C["cobalt500"]}"></td><td style="width:24%;height:5px;background:{C["cobalt300"]}"></td><td style="height:5px;background:{C["gold500"]}"></td></tr></table></td></tr>''')

    # 1. verdict
    tot_tw, tot_lw = (f.get("this_week") or {}).get("total", {}), (f.get("last_week") or {}).get("total", {})
    gsc_tw = (g.get("totals") or {}).get("this_week", {})
    m_rate, d_rate = (f.get("this_week") or {}).get("mobile", {}).get("lead_rate"), (f.get("this_week") or {}).get("desktop", {}).get("lead_rate")
    tiles = "".join([stat_tile("Lead persons", n(tot_tw.get("lead_persons")), f"vs {n(tot_lw.get('lead_persons'))} last week", pill((fd.get("total") or {}).get("lead_persons_wow"), noise=noise)),
                     stat_tile("Visitor to lead", pct(tot_tw.get("lead_rate")), f"mobile {pct(m_rate)}, desktop {pct(d_rate)}", pill((fd.get("total") or {}).get("lead_rate_wow_pts"), "pts", noise=noise)),
                     stat_tile("Organic clicks", n(gsc_tw.get("clicks")), f"{n(gsc_tw.get('impressions'))} impressions", pill((g.get("deltas") or {}).get("clicks", {}).get("wow")))])
    noise_line = para(f'{badge("inside noise", "gold")} Fewer than {CONFIG["thresholds"]["min_lead_persons_for_rates"]} lead persons this week. Rate deltas are shown but not trended.', 12, C["cloud600"], margin="10px 0 0") if noise else ""
    P.append(f'''<tr><td style="padding:28px 32px 10px"><p style="margin:0;font:600 11px/16px {F_BODY};letter-spacing:.08em;text-transform:uppercase;color:{C["cobalt500"]}">Verdict</p>
      <p style="margin:8px 0 18px;font:600 19px/28px {F_DISPLAY};letter-spacing:-.01em;color:{C["mid800"]}">{esc(I.get("narrative", ""))}</p>
      <table role="presentation" cellpadding="0" cellspacing="0" style="width:100%;border-collapse:separate;border-spacing:0"><tr>{tiles}</tr></table>{noise_line}</td></tr>''')

    # 2. actions
    P.append(section("Actions", "What was done, what is queued, what needs you", SI.get("actions"), actions_block(I, CH, pr_url)))

    # 3. trend, 13 weeks
    tr = ph.get("trend") or {}
    labels = [week_label(w) for w in tr.get("weeks", [])]
    trend_html = ""
    if labels:
        trend_html += img("visitors-per-week", charts.line_chart([{"name": "Mobile visitors", "values": [x["visitors"] for x in tr["mobile"]], "color": charts.COBALT},
                                         {"name": "Desktop visitors", "values": [x["visitors"] for x in tr["desktop"]], "color": charts.COBALT300}], labels, title="Karachi visitors per week"))
        trend_html += img("leads-per-week", charts.line_chart([{"name": "Lead persons", "values": [x["lead_persons"] for x in tr["total"]], "color": charts.COBALT700},
                                         {"name": "Mobile leads", "values": [x["lead_persons"] for x in tr["mobile"]], "color": charts.COBALT300}], labels, title="Lead persons per week"))
        trend_html += img("lead-rate-per-week", charts.line_chart([{"name": "Visitor to lead", "values": [round((x["lead_rate"] or 0) * 100, 1) if x["visitors"] >= 10 else None for x in tr["total"]], "color": charts.SAGE}], labels,
                                        y_fmt=lambda v: f"{v:.0f}%", title="Lead rate per week (weeks with 10+ visitors)"))
    gt = g.get("trend") or []
    if gt:
        gl = [week_label(w["week_start"]) for w in gt]
        trend_html += img("clicks-per-week", charts.line_chart([{"name": "Organic clicks", "values": [w["clicks"] for w in gt], "color": charts.COBALT}], gl, title="Search Console clicks per week"))
        trend_html += img("impressions-per-week", charts.line_chart([{"name": "Impressions", "values": [w["impressions"] for w in gt], "color": charts.COBALT300}], gl, title="Search Console impressions per week"))
        trend_html += img("position-per-week", charts.line_chart([{"name": "Avg position (lower is better)", "values": [w["position"] for w in gt], "color": charts.GOLD}], gl, invert=True, y_fmt=lambda v: f"{v:.1f}", title="Average position per week"))
    P.append(section("Trend", "The last 13 weeks", SI.get("trend"), trend_html or para("No trend data.", 13, C["cloud600"]), note="Shaded band is this week. Karachi visitors only, test IDs excluded. Search Console weeks end 3 days ago (data lag)."))

    # 4. funnel visual
    steps = [("Visitors", "visitors"), ("Lead persons", "lead_persons"), ("Booking started", "booking_started"), ("Booking handoff", "handoff")]
    def fun(dev, label):
        cur = (f.get("this_week") or {}).get(dev, {})
        return img(f"funnel-{dev}", charts.funnel_chart([(lab, cur.get(k, 0)) for lab, k in steps], title=f"{label}: {n(cur.get('visitors'))} visitors, {pct(cur.get('lead_rate'))} to lead"), 300) or para(f"No {dev} visitors this week.", 12, C["cloud600"])
    funnel_html = (f'<table role="presentation" cellpadding="0" cellspacing="0" style="width:100%;border-collapse:collapse"><tr><td style="width:50%;vertical-align:top;padding-right:8px">{fun("mobile", "Mobile")}</td>'
                   f'<td style="width:50%;vertical-align:top;padding-left:8px">{fun("desktop", "Desktop")}</td></tr></table>')
    rows = []
    for dev, label in (("mobile", "Mobile"), ("desktop", "Desktop"), ("total", "All")):
        cur, m28, p28 = ((f.get(k) or {}).get(dev, {}) for k in ("this_week", "last_28d", "prior_28d"))
        rows.append([td(esc(label), strong=True), td(n(cur.get("visitors")), "right", mono=True), td(n(cur.get("lead_persons")), "right", mono=True, strong=True), td(pct(cur.get("lead_rate")), "right", mono=True),
                     td(pill((fd.get(dev) or {}).get("lead_persons_wow"), noise=noise), "right"), td(n(m28.get("lead_persons")), "right", mono=True), td(n(p28.get("lead_persons")), "right", mono=True, color=C["cloud600"]), td(pill((fd.get(dev) or {}).get("lead_persons_mom")), "right")])
    clicks = f'WhatsApp {n(tot_tw.get("wa_clicks"))}, Book {n(tot_tw.get("book_clicks"))}, Call {n(tot_tw.get("call_clicks"))} clicks this week. Leads are persons who fired any lead event; clicks count events. Most leads tap WhatsApp directly from a page, so the booking steps stay small by design.'
    funnel_html += sub("This week vs last, and 28 days vs the prior 28") + table([th("Device"), th("Visitors", "right"), th("Leads", "right"), th("Rate", "right"), th("WoW", "right"), th("28d leads", "right"), th("Prior 28d", "right"), th("MoM", "right")], rows) + para(clicks, 12, C["cloud600"], margin="10px 0 0")
    P.append(section("Funnel", "Web and mobile, separately", SI.get("funnel"), funnel_html, note=f"Bars are proportional to visitors. Lead persons tap WhatsApp, Book or Call from any page; the booking wizard is the minority path and is shown as its own two steps. Window {tw[0]} to {tw[1]}."))

    # 5. where: areas + pages
    ar28 = (ph.get("areas") or {}).get("last_28d", [])[:10]
    artw = {r["area"]: r for r in (ph.get("areas") or {}).get("this_week", [])}
    arp28 = {r["area"]: r for r in (ph.get("areas") or {}).get("prior_28d", [])}
    arows = [[td(esc(r["area"].replace("-", " ").title()), strong=True), td(n(r["landing_sessions"]), "right", mono=True), td(n(r["lead_persons"]), "right", mono=True, strong=True), td(pct(r.get("lead_rate")), "right", mono=True),
              td(n(r["area_selected"]), "right", mono=True), td(n(artw.get(r["area"], {}).get("lead_persons", 0)), "right", mono=True), td(pill(float(r["lead_persons"] - arp28.get(r["area"], {}).get("lead_persons", 0)), ""), "right")] for r in ar28]
    cities = ", ".join(f'{c["city"]} {c["persons"]}' for c in (ph.get("data_quality") or {}).get("city_split_28d", [])[:4])
    pg = sorted((ph.get("pages") or {}).get("last_28d", []), key=lambda r: -(r.get("uv") or 0))[:12]
    prows = [[td(esc(r["path"]), mono=True), td(n(r["uv"]), "right", mono=True), td(n(r["lead_persons"]), "right", mono=True, strong=True), td(pct(r.get("lead_rate")), "right", mono=True),
              td((badge(f'{r["vs_site_avg"]}x', "sage" if r["vs_site_avg"] >= 1 else "red" if r["vs_site_avg"] < 0.7 else "cloud") if r.get("vs_site_avg") is not None else ""), "right"),
              td(n(r.get("scroll_p50")) + ("%" if r.get("scroll_p50") is not None else ""), "right", mono=True, color=C["cloud600"])] for r in pg]
    where = (sub("Karachi areas, last 28 days") + table([th("Area"), th("Sessions", "right"), th("Leads", "right"), th("Rate", "right"), th("Dropdown", "right"), th("This wk", "right"), th("MoM", "right")], arows, "No area-page landings yet. Area pages are days old in the index.") +
             para(f"Area = area page landed on, booking dropdown choice, or the area in the WhatsApp prefill. PostHog geo stops at city (this month: {cities}), so this is intent by area.", 12, C["cloud600"], margin="8px 0 0") +
             sub("Pages, last 28 days") + table([th("Page"), th("Visitors", "right"), th("Leads", "right"), th("Rate", "right"), th("vs site", "right"), th("Scroll p50", "right")], prows))
    P.append(section("Where", "Areas and pages", SI.get("where"), where))

    # 6. SEO
    gtot, gd = g.get("totals") or {}, g.get("deltas") or {}
    kpis = "".join([stat_tile("Clicks 28d", n(gtot.get("last_28d", {}).get("clicks")), f"prior {n(gtot.get('prior_28d', {}).get('clicks'))}", pill(gd.get("clicks", {}).get("mom"))),
                    stat_tile("Impressions 28d", n(gtot.get("last_28d", {}).get("impressions")), f"prior {n(gtot.get('prior_28d', {}).get('impressions'))}", pill(gd.get("impressions", {}).get("mom"))),
                    stat_tile("Avg position", n(gtot.get("last_28d", {}).get("position"), 1), f"CTR {pct(gtot.get('last_28d', {}).get('ctr'), 2)}", pill(gd.get("position", {}).get("mom"), "", invert=True))])
    b, bp = (g.get("buckets") or {}).get("last_28d", {}), (g.get("buckets") or {}).get("prior_28d", {})
    keys = [("Positions 1 to 3", "p1_3"), ("Positions 4 to 10", "p4_10"), ("Positions 11 to 20", "p11_20"), ("Beyond 20", "p21_plus")]
    buckets_svg = img("position-buckets", charts.bucket_bars([b.get(k, 0) for _, k in keys], [bp.get(k, 0) for _, k in keys], [l for l, _ in keys])) if b else ""
    def mover_rows(ms, gaining):
        return [[td(esc(m["query"]), strong=True), td(esc(m["page"]), mono=True, color=C["cloud600"]), td(f'{n(m["position_prev"], 1)} → {n(m["position"], 1)}', "right", mono=True),
                 td(pill(m["clicks_delta"], ""), "right"), td(esc(play_for(m, gaining, plays)) + " " + play_status(m, CH, Q), color=C["cloud700"])] for m in ms[:8]]
    head = [th("Query"), th("Page"), th("Position", "right"), th("Δ clicks", "right"), th("What next")]
    sd = g.get("striking_distance", [])[:8]
    srows = [[td(esc(r["query"]), strong=True), td(esc(r["page"]), mono=True, color=C["cloud600"]), td(n(r["position"], 1), "right", mono=True), td(n(r["impressions"]), "right", mono=True), td(esc(play_for(r, True, plays)) + " " + play_status(r, CH, Q), color=C["cloud700"])] for r in sd]
    site_a = a.get("site") or {}
    comps = sorted([c for c in a.get("competitors", []) if c.get("dr") is not None], key=lambda c: -(c.get("refdomains") or 0))[:4]
    auth = (f'Refdomains <strong>{n(site_a.get("refdomains"))}</strong> (last week {n(site_a.get("refdomains_prev_week"))}), DR {n(site_a.get("dr"))}, {n(site_a.get("org_keywords"))} organic keywords in Ahrefs. '
            f'Competitors: ' + ", ".join(f'{c["domain"]} DR {n(c["dr"])} with {n(c["refdomains"])} refdomains' for c in comps) + ".")
    gaps = a.get("competitor_gaps", [])[:5]
    grows = [[td(esc(x.get("top_keyword")), strong=True), td(n(x.get("top_keyword_volume")), "right", mono=True), td(esc(x.get("competitor")), mono=True, color=C["cloud600"]), td(n(x.get("top_keyword_best_position")), "right", mono=True)] for x in gaps]
    seo = (f'<table role="presentation" cellpadding="0" cellspacing="0" style="width:100%;border-collapse:separate;border-spacing:0"><tr>{kpis}</tr></table>' +
           sub("Where queries rank, last 28 days vs prior") + buckets_svg +
           f'<p style="margin:18px 0 6px;font:700 14px/20px {F_DISPLAY};color:{C["sage800"]}">Gaining</p>' + table(head, mover_rows(g.get("movers_up", []), True)) +
           f'<p style="margin:18px 0 6px;font:700 14px/20px {F_DISPLAY};color:{C["red700"]}">Slipping</p>' + table(head, mover_rows(g.get("movers_down", []), False)) +
           sub(f'Striking distance (positions 8 to 20, {CONFIG["thresholds"]["striking_min_impressions"]}+ impressions)') + table([th("Query"), th("Page"), th("Pos", "right"), th("Impr", "right"), th("What next")], srows) +
           sub("Authority") + para(auth, 13) + (sub("Competitor keyword gaps (Ahrefs, Pakistan)") + table([th("Keyword"), th("Volume", "right"), th("Who ranks"), th("Pos", "right")], grows) if grows else ""))
    gw = g.get("windows") or {}
    P.append(section("SEO", "Positions, movers, authority", SI.get("seo"), seo, note=f'Search Console {gw.get("this_week", ["", ""])[0]} to {gw.get("this_week", ["", ""])[1]} (3-day lag); Ahrefs as of {esc(a.get("date"))}. Movers compare 28 days vs the prior 28.'))

    # 7. CRO
    kinds = {"low_lead_rate": "Lead rate below site", "low_scroll": "Low scroll depth", "rageclicks": "Rage clicks", "device_gap": "Device converting below site", "booking_dropoff": "Booking chain drop-off"}
    plays_cro = {"low_lead_rate": "Move the price anchor and WhatsApp CTA above the fold; one change, read in 14 days.", "low_scroll": "Lead with the answer and the CTA in the first screen; shorten the hero.",
                 "rageclicks": "Check the element people hammer (replay); likely a dead tap target.", "device_gap": "Device-specific CTA: QR and copy-phone on desktop, sticky bar on mobile.", "booking_dropoff": "Cut a step or reorder: ask area before service, prefill from the page."}
    lrows = []
    for l in cro.get("leaks", [])[:6]:
        detail = {"low_lead_rate": f'{pct(l.get("lead_rate"))} vs site {pct(l.get("site_rate"))} on {n(l.get("uv"))} visitors', "low_scroll": f'median scroll {n(l.get("scroll_p50"))}% on {n(l.get("uv"))} visitors',
                  "rageclicks": f'{n(l.get("rageclicks"))} rage clicks', "device_gap": f'{pct(l.get("lead_rate"))} vs site {pct(l.get("site_rate"))} on {n(l.get("visitors"))} visitors',
                  "booking_dropoff": f'{n(l.get("started"))} started, {n(l.get("handoff"))} handed off'}[l["kind"]]
        lrows.append([td(esc(kinds[l["kind"]]), strong=True), td(esc(l["page"]) + (f' ({esc(l["device"])})' if l.get("device") not in (None, "all") else ""), mono=True), td(esc(detail)), td(n(l.get("lead_gap_persons")) if l.get("lead_gap_persons") else "", "right", mono=True, strong=True), td(esc(plays.get(l["page"], plays_cro[l["kind"]])) + " " + play_status(l, CH, Q), color=C["cloud700"])])
    vtone = {"working": "sage", "flat": "cloud", "worse": "red", "too_early": "gold", "not_on_main": "cloud"}
    rrows = [[td(esc(r["id"]), mono=True), td(esc(r.get("hypothesis") or ""), color=C["cloud700"]), td(f'{n(r.get("days_live"))}d', "right", mono=True), td((f'{pct(r["pre"]["rate"])} → {pct(r["post"]["rate"])}' if r.get("pre") and r.get("post") else ""), "right", mono=True), td(badge(r["verdict"].replace("_", " "), vtone.get(r["verdict"], "cloud")), "right")] for r in cro.get("ledger_reads", [])]
    cro_html = (sub("Leaks, ranked by lead persons at stake (28 days)") + table([th("Leak"), th("Page"), th("Evidence"), th("At stake", "right"), th("What next")], lrows, "No leaks above threshold.") +
                sub("Ship ledger reads (pre vs post, same-length windows)") + (table([th("Change"), th("Hypothesis"), th("Live", "right"), th("Lead rate", "right"), th("Verdict", "right")], rrows) if rrows else para("No CRO changes on the ledger yet. Every CRO change the routine ships adds one and is read at 7, 14 and 28 days.", 13, C["cloud600"])))
    P.append(section("CRO", "Leaks and what shipped changes did", SI.get("cro"), cro_html, note="Traffic is too small for split tests. Changes are read sequentially, one per money page in flight."))

    # 8. analyst notes
    notes = I.get("analyst_notes", [])[:6]
    nrows = "".join(f'''<tr><td style="padding:10px 0;border-bottom:1px solid {C["cloud200"]}"><p style="margin:0;font:600 14px/20px {F_BODY};color:{C["mid800"]}">{i + 1}. {esc(x.get("observation"))}</p>
        <p style="margin:4px 0 0;font:400 13px/20px {F_BODY};color:{C["cloud700"]}">{esc(x.get("detail", ""))}</p>
        <p style="margin:4px 0 0">{mono(x.get("evidence_ref", ""))} {badge(x.get("action", "noted"), "cobalt" if "ship" in str(x.get("action", "")).lower() else "gold" if "instrument" in str(x.get("action", "")).lower() else "cloud")}</p></td></tr>''' for i, x in enumerate(notes))
    ev = ph.get("events") or {}
    ev_line = f'New events this week: {", ".join(ev.get("new", [])) or "none"}. ' + (f'Tracking code changed in the last 3 weeks ({len(h.get("instrumentation_commits", []))} commits), so event counts straddle a schema change.' if h.get("instrumentation_commits") else "")
    P.append(section("Analyst notes", "What the data said when pushed", SI.get("analyst"), (f'<table role="presentation" cellpadding="0" cellspacing="0" style="width:100%;border-collapse:collapse">{nrows}</table>' if nrows else para("No analyst notes this run.", 13, C["cloud600"])) + para(ev_line, 12, C["cloud600"], margin="12px 0 0")))

    # 9. suggested changes, full list
    srows2 = [[td(esc(s.get("title")), strong=True), td(esc(s.get("detail", "")), color=C["cloud700"]), td(badge(s.get("owner", "you"), "cobalt" if s.get("owner") == "routine" else "gold"), "right"), td(esc(s.get("effort", "")), "right", mono=True)] for s in I.get("suggestions", [])[:8]]
    P.append(section("Suggested changes", "Needs a human, not shipped", None, table([th("Change"), th("Why"), th("Owner", "right"), th("Effort", "right")], srows2), note="Founder decisions, ops and instrumentation the routine cannot do alone."))

    # 10. health
    hb, sm, trk = h.get("pages_build") or {}, h.get("sitemap") or {}, h.get("tracking") or {}
    behind = hb.get("commits_behind_main")
    chips = [badge(f'build {hb.get("status", "unknown")}', "sage" if hb.get("status") == "built" else "red"),
             badge("live = main" if behind == 0 else f'live is {behind} commits behind main' if behind else "live vs main unknown", "sage" if behind == 0 else "red" if behind else "gold"),
             badge(f'sitemap live {sm.get("live_urls", "?")}/{sm.get("repo_urls", "?")}', "sage" if sm.get("live_urls") == sm.get("repo_urls") else "red"),
             badge("tracking ok" if trk.get("ok") else "tracking gaps", "sage" if trk.get("ok") else "red"),
             badge("schema ok" if not h.get("schema_errors") else f'{len(h["schema_errors"])} schema errors', "sage" if not h.get("schema_errors") else "red")]
    if D.get("errors"):
        chips.append(badge("collector errors: " + ", ".join(D["errors"]), "red"))
    u = a.get("units") or {}
    hl = " ".join(chips) + para(f'Head {esc(h.get("head_commit", ""))}. Ahrefs units {n(u.get("units_usage_workspace"))} of {n(u.get("units_limit_workspace"))} this cycle, {n(a.get("api_calls"))} calls this run.', 12, C["cloud600"], margin="10px 0 0")
    if I.get("risks"):
        hl += para("Risks: " + " ".join(esc(r) for r in I["risks"]), 13, C["red700"], margin="8px 0 0")
    P.append(section("Health", "Deploy, tracking, schema", None, hl))

    # 11. one move
    om = I.get("one_move") or {}
    if om:
        P.append(f'''<tr><td style="padding:8px 32px 28px"><table role="presentation" cellpadding="0" cellspacing="0" style="width:100%;border-collapse:collapse;background:{C["mid800"]};border-radius:12px"><tr><td style="padding:22px 24px">
          <p style="margin:0;font:600 11px/16px {F_BODY};letter-spacing:.08em;text-transform:uppercase;color:{C["gold500"]}">The one move this week</p>
          <p style="margin:8px 0 6px;font:700 20px/26px {F_DISPLAY};letter-spacing:-.01em;color:{C["white"]}">{esc(om.get("title"))}</p>
          <p style="margin:0;font:400 14px/22px {F_BODY};color:{C["cobalt300"]}">{esc(om.get("detail"))}</p>
          <p style="margin:10px 0 0">{mono(om.get("evidence_ref", ""), C["mid300"])}</p></td></tr></table></td></tr>''')

    P.append(f'''<tr><td style="padding:18px 32px 28px;border-top:1px solid {C["cloud200"]}"><p style="margin:0;font:400 11px/17px {F_CODE};color:{C["cloud600"]}">Generated {esc(D.get("generated_at"))} · PostHog project {CONFIG["posthog"]["project_id"]} · {esc(CONFIG["gsc_site"])} · Ahrefs Lite<br>
      Every number in this email exists in report_data.json. Metrics never enter the public site repo or the PR. Charts are hosted images; the attached report.html is the same report.</p></td></tr>''')

    return f'''<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SafaiKaro weekly {esc(D["week"])}</title>
<link href="https://fonts.googleapis.com/css2?family=Archivo:wght@700;800&family=Inter:wght@400;600&family=Source+Code+Pro:wght@400;600&display=swap" rel="stylesheet">
<style>body{{margin:0;padding:0;background:{C["cloud100"]}}} table{{border-collapse:collapse}} a{{color:{C["cobalt500"]}}} @media (max-width:640px){{.wrap{{width:100%!important}}}}</style></head>
<body style="margin:0;padding:0;background:{C["cloud100"]}"><table role="presentation" cellpadding="0" cellspacing="0" style="width:100%;background:{C["cloud100"]}"><tr><td style="padding:24px 12px">
<table role="presentation" class="wrap" cellpadding="0" cellspacing="0" align="center" style="width:680px;max-width:100%;background:{C["white"]};border-radius:12px;overflow:hidden;border:1px solid {C["cloud200"]}">{"".join(P)}</table></td></tr></table></body></html>'''


def subject(D, CH, pr_url):
    ph = D.get("posthog") or {}
    tot = ((ph.get("funnel") or {}).get("this_week") or {}).get("total", {})
    d = ((ph.get("funnel_deltas") or {}).get("total") or {}).get("lead_persons_wow")
    dtxt = f" ({'+' if d and d > 0 else ''}{d:.0f}%)" if d is not None else ""
    url = pr_url or CH.get("pr_url")
    prtxt = f" · PR #{url.rstrip('/').split('/')[-1]}" if url else " · no PR"
    return f'{CONFIG["email"]["subject_prefix"]} {D["week"]}: {n(tot.get("lead_persons"))} leads{dtxt}{prtxt}'


def send_brevo(subj, html_body, attach=None):
    key = secret("BREVO_API_KEY", "brevo-api-key.txt", Path.home() / "Work/autonomous/credentials")
    if not key:
        raise RuntimeError("BREVO_API_KEY missing")
    e = CONFIG["email"]
    payload = {"sender": {"email": e["from"], "name": e["from_name"]}, "to": [{"email": t} for t in e["to"]], "subject": subj, "htmlContent": html_body}
    if attach:
        payload["attachment"] = [{"name": attach.name, "content": base64.b64encode(attach.read_bytes()).decode()}]
    try:
        return http_json("https://api.brevo.com/v3/smtp/email", {"api-key": key}, payload)
    except urllib.error.HTTPError as ex:
        raise RuntimeError(f"Brevo {ex.code}: {ex.read().decode()[:300]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--insights", default=str(OUT / "insights.json"))
    ap.add_argument("--changes", default=str(OUT / "changes.json"))
    ap.add_argument("--pr")
    ap.add_argument("--send", action="store_true")
    ap.add_argument("--failure")
    a = ap.parse_args()
    if a.failure:
        subj = f'{CONFIG["email"]["subject_prefix"]}: collection failed'
        if a.send:
            send_brevo(subj, f'<p style="font:14px/22px {F_BODY}">{esc(a.failure)}</p>')
        log("failure note", "sent" if a.send else "(dry)", subj)
        return 0
    D = json.loads((OUT / "report_data.json").read_text())
    I = json.loads(Path(a.insights).read_text()) if Path(a.insights).exists() else {}
    CH = json.loads(Path(a.changes).read_text()) if Path(a.changes).exists() else {}
    html_body = render(D, I, CH, a.pr)
    out = OUT / "report.html"
    out.write_text(html_body)
    subj = subject(D, CH, a.pr)
    log("wrote", out, "|", subj)
    if a.send:
        log("sent via Brevo:", send_brevo(subj, html_body, attach=out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
