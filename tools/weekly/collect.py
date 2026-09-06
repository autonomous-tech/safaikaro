#!/usr/bin/env python3
"""collect.py: PostHog + GSC + Ahrefs + site health -> output/report_data.json.

Deterministic. Every number the weekly email shows comes from this file.
Each source is isolated: a failure lands in report_data["errors"], the rest still runs.
Usage: python tools/weekly/collect.py [--skip ahrefs,gsc,posthog,health] [--ref YYYY-MM-DD]
"""
import argparse, datetime as dt, json, re, subprocess, sys, time, urllib.parse, urllib.request
from collections import defaultdict
from pathlib import Path

from common import (CONFIG, OUT, ROOT, HERE, PostHog, git, google_creds, http_json, iso_week_label, log,
                    pct_delta, safe_rate, secret, today, windows)

T = CONFIG["thresholds"]
AREA_RE = re.compile(r"^/pest-control-(.+)-karachi$")


# ───────────────────────── PostHog ─────────────────────────
def collect_posthog(W):
    ph = PostHog()
    out = {"windows": {k: [str(a), str(b)] for k, (a, b) in W.items()}}
    LEAD = ph.lead
    base = f"{ph.excl} AND {ph.karachi}"

    def funnel(win):
        sql = f"""SELECT coalesce(properties.$device_type,'Other') AS device,
          count(DISTINCT if(event='$pageview',person_id,NULL)) AS visitors,
          countIf(event='$pageview') AS pageviews,
          count(DISTINCT if(event='booking_quote_started',person_id,NULL)) AS booking_started,
          count(DISTINCT if(event='booking_area_selected',person_id,NULL)) AS area_selected,
          count(DISTINCT if(event='booking_quote_handoff_started',person_id,NULL)) AS handoff,
          count(DISTINCT if({LEAD},person_id,NULL)) AS lead_persons,
          countIf(event='whatsapp_click') AS wa_clicks, countIf(event='book_click') AS book_clicks,
          countIf(event='call_click') AS call_clicks
          FROM events WHERE {ph.between(win)} AND {base} GROUP BY device"""
        rows = {r["device"]: r for r in ph.rows(sql)}
        res = {}
        for dev in ("Mobile", "Desktop", "Tablet", "Other"):
            r = rows.get(dev)
            if r:
                r = dict(r); r["lead_rate"] = safe_rate(r["lead_persons"], r["visitors"]); res[dev.lower()] = r
        tot = {k: sum(v.get(k, 0) for v in res.values()) for k in
               ("visitors", "pageviews", "booking_started", "area_selected", "handoff", "lead_persons", "wa_clicks", "book_clicks", "call_clicks")}
        tot["lead_rate"] = safe_rate(tot["lead_persons"], tot["visitors"])
        res["total"] = tot
        return res

    out["funnel"] = {k: funnel(w) for k, w in W.items()}
    f = out["funnel"]
    out["funnel_deltas"] = {}
    for dev in ("mobile", "desktop", "total"):
        cur, last, m, pm = (f["this_week"].get(dev, {}), f["last_week"].get(dev, {}), f["last_28d"].get(dev, {}), f["prior_28d"].get(dev, {}))
        out["funnel_deltas"][dev] = {
            "lead_persons_wow": pct_delta(cur.get("lead_persons"), last.get("lead_persons")),
            "lead_persons_mom": pct_delta(m.get("lead_persons"), pm.get("lead_persons")),
            "visitors_wow": pct_delta(cur.get("visitors"), last.get("visitors")),
            "visitors_mom": pct_delta(m.get("visitors"), pm.get("visitors")),
            "lead_rate_wow_pts": (round((cur.get("lead_rate") or 0) * 100 - (last.get("lead_rate") or 0) * 100, 1) if cur.get("lead_rate") is not None and last.get("lead_rate") is not None else None),
            "lead_rate_mom_pts": (round((m.get("lead_rate") or 0) * 100 - (pm.get("lead_rate") or 0) * 100, 1) if m.get("lead_rate") is not None and pm.get("lead_rate") is not None else None),
        }

    # daily series, last 28d (for the sparkline)
    w28 = W["last_28d"]
    out["daily"] = ph.rows(f"""SELECT toString(toDate(toTimeZone(timestamp, 'Asia/Karachi'))) AS day,
        count(DISTINCT if(event='$pageview',person_id,NULL)) AS visitors,
        count(DISTINCT if({LEAD},person_id,NULL)) AS lead_persons
        FROM events WHERE {ph.between(w28)} AND {base} GROUP BY day ORDER BY day""")

    # areas: landing page (session entry), booking dropdown, WhatsApp prefill
    def areas(win):
        agg = defaultdict(lambda: {"landing_sessions": 0, "landing_lead_persons": 0, "area_selected": 0, "prefill_leads": 0})
        for r in ph.rows(f"""SELECT session.$entry_pathname AS lp, count(DISTINCT $session_id) AS s,
              count(DISTINCT if({LEAD},person_id,NULL)) AS leads
              FROM events WHERE {ph.between(win)} AND {base} AND session.$entry_pathname LIKE '/pest-control-%-karachi'
              GROUP BY lp"""):
            m = AREA_RE.match(r["lp"] or "")
            if not m or m.group(1) in ("karachi-areas", "price-list"):
                continue
            a = agg[m.group(1)]; a["landing_sessions"] += r["s"]; a["landing_lead_persons"] += r["leads"]
        for r in ph.rows(f"""SELECT lower(toString(properties.area)) AS area, count(DISTINCT person_id) AS p
              FROM events WHERE {ph.between(win)} AND {base} AND event='booking_area_selected' GROUP BY area"""):
            if r["area"]:
                agg[slug(r["area"])]["area_selected"] += r["p"]
        for r in ph.rows(f"""SELECT coalesce(nullIf(toString(properties.prefill),''), decodeURLComponent(coalesce(properties.href,''))) AS txt,
              count(DISTINCT person_id) AS p FROM events WHERE {ph.between(win)} AND {base} AND event='whatsapp_click' GROUP BY txt"""):
            a = prefill_area(r["txt"])
            if a:
                agg[a]["prefill_leads"] += r["p"]
        rows = []
        for k, v in agg.items():
            v = dict(v); v["area"] = k
            v["lead_persons"] = max(v["landing_lead_persons"], v["prefill_leads"])
            v["lead_rate"] = safe_rate(v["landing_lead_persons"], v["landing_sessions"])
            rows.append(v)
        return sorted(rows, key=lambda r: (-r["lead_persons"], -r["landing_sessions"]))

    out["areas"] = {k: areas(W[k]) for k in ("this_week", "last_week", "last_28d", "prior_28d")}
    last = {r["area"]: r for r in out["areas"]["last_week"]}
    for r in out["areas"]["this_week"]:
        r["lead_persons_wow"] = r["lead_persons"] - last.get(r["area"], {}).get("lead_persons", 0)
        r["landing_sessions_wow"] = r["landing_sessions"] - last.get(r["area"], {}).get("landing_sessions", 0)

    # pages: uv/pv/leads by pathname, scroll p50 via $prev_pageview_*, rageclicks
    def pages(win):
        rows = {r["path"]: r for r in ph.rows(f"""SELECT coalesce(properties.$pathname,'?') AS path,
            count(DISTINCT if(event='$pageview',person_id,NULL)) AS uv, countIf(event='$pageview') AS pv,
            count(DISTINCT if({LEAD},person_id,NULL)) AS lead_persons, countIf({LEAD}) AS lead_events,
            countIf(event='$rageclick') AS rageclicks
            FROM events WHERE {ph.between(win)} AND {base} GROUP BY path HAVING pv > 0 ORDER BY pv DESC LIMIT 120""")}
        for r in ph.rows(f"""SELECT coalesce(properties.$prev_pageview_pathname,'?') AS path,
            quantile(0.5)(toFloat(properties.$prev_pageview_max_scroll_percentage)) AS scroll_p50
            FROM events WHERE {ph.between(win)} AND {base} AND properties.$prev_pageview_max_scroll_percentage IS NOT NULL GROUP BY path"""):
            if r["path"] in rows and r["scroll_p50"] is not None:
                rows[r["path"]]["scroll_p50"] = round(r["scroll_p50"] * (100 if r["scroll_p50"] <= 1 else 1))
        for r in rows.values():
            r["lead_rate"] = safe_rate(r["lead_persons"], r["uv"])
        return list(rows.values())

    out["pages"] = {k: pages(W[k]) for k in ("this_week", "last_week", "last_28d")}
    site_rate = out["funnel"]["last_28d"]["total"]["lead_rate"] or 0
    for r in out["pages"]["last_28d"]:
        r["vs_site_avg"] = round(r["lead_rate"] / site_rate, 2) if r["lead_rate"] is not None and site_rate else None

    # booking chain by device (28d) and CTA placement x device (28d)
    out["booking_steps"] = ph.rows(f"""SELECT event, coalesce(properties.$device_type,'Other') AS device,
        coalesce(toString(properties.step), toString(properties.question), '') AS step,
        count() AS c, count(DISTINCT person_id) AS persons
        FROM events WHERE {ph.between(w28)} AND {base} AND event LIKE 'booking_%' GROUP BY event, device, step ORDER BY event, device, step""")
    out["cta_placement"] = ph.rows(f"""SELECT event, coalesce(nullIf(toString(properties.cta),''),'untagged') AS cta,
        coalesce(properties.$device_type,'Other') AS device, count() AS clicks, count(DISTINCT person_id) AS persons
        FROM events WHERE {ph.between(w28)} AND {base} AND {LEAD} GROUP BY event, cta, device ORDER BY clicks DESC""")
    out["micro"] = ph.rows(f"""SELECT event, coalesce(toString(properties.question), toString(properties.tab), toString(properties.symptom), '') AS k,
        count() AS c, count(DISTINCT person_id) AS persons
        FROM events WHERE {ph.between(W['this_week'])} AND {base} AND event IN ('faq_open','price_tab_change','nav_menu_open','khatmal_symptom_selected','pricing_selection_change')
        GROUP BY event, k ORDER BY c DESC LIMIT 40""")

    # event inventory: this week vs prior 4 weeks (new events / new property keys)
    tw, p4 = W["this_week"], (W["this_week"][0] - dt.timedelta(days=28), W["this_week"][0] - dt.timedelta(days=1))
    ev_now = {r["event"]: r for r in ph.rows(f"SELECT event, count() AS c, count(DISTINCT person_id) AS persons FROM events WHERE {ph.between(tw)} AND {ph.excl} GROUP BY event ORDER BY c DESC")}
    ev_prev = {r["event"] for r in ph.rows(f"SELECT event FROM events WHERE {ph.between(p4)} AND {ph.excl} GROUP BY event")}
    keys_now = {}
    try:
        for r in ph.rows(f"""SELECT event, arrayJoin(JSONExtractKeys(properties)) AS k, count() AS c FROM events
            WHERE {ph.between(tw)} AND {ph.excl} AND event NOT LIKE '$%' GROUP BY event, k"""):
            if not r["k"].startswith("$") and r["k"] not in ("token", "distinct_id"):
                keys_now.setdefault(r["event"], []).append(r["k"])
    except RuntimeError as e:
        log("property keys skipped:", e)
    out["events"] = {"mix_this_week": list(ev_now.values()), "new": [e for e in ev_now if e not in ev_prev],
                     "property_keys": keys_now}

    # data quality: burst ids, city split
    out["data_quality"] = {
        "burst_ids": ph.rows(f"""SELECT distinct_id, toString(toDate(toTimeZone(timestamp, 'Asia/Karachi'))) AS day, count() AS c
            FROM events WHERE {ph.between(w28)} AND {ph.excl} AND {LEAD} GROUP BY distinct_id, day HAVING c >= {T['burst_lead_events_per_day']} ORDER BY c DESC"""),
        "city_split_28d": ph.rows(f"""SELECT coalesce(properties.$geoip_city_name,'unknown') AS city, count(DISTINCT person_id) AS persons
            FROM events WHERE {ph.between(w28)} AND {ph.excl} AND event='$pageview' GROUP BY city ORDER BY persons DESC LIMIT 8"""),
        "sample_warning": (out["funnel"]["this_week"]["total"]["lead_persons"] or 0) < T["min_lead_persons_for_rates"],
    }

    # 13-week trend by device (Mon-start weeks, Asia/Karachi), ending with this_week
    start13 = W["this_week"][0] - dt.timedelta(weeks=12)
    trend = ph.rows(f"""SELECT toString(toStartOfWeek(toTimeZone(timestamp,'Asia/Karachi'), 1)) AS week_start,
        coalesce(properties.$device_type,'Other') AS device,
        count(DISTINCT if(event='$pageview',person_id,NULL)) AS visitors, countIf(event='$pageview') AS pageviews,
        count(DISTINCT if({LEAD},person_id,NULL)) AS lead_persons
        FROM events WHERE {ph.between((start13, W['this_week'][1]))} AND {base} GROUP BY week_start, device ORDER BY week_start""")
    weeks = [str(start13 + dt.timedelta(weeks=i)) for i in range(13)]
    by = {(r["week_start"], r["device"]): r for r in trend}
    out["trend"] = {"weeks": weeks, "mobile": [], "desktop": [], "total": []}
    for wk in weeks:
        m, d = by.get((wk, "Mobile"), {}), by.get((wk, "Desktop"), {})
        allv = [r for (w, _), r in by.items() if w == wk]
        out["trend"]["mobile"].append({"visitors": m.get("visitors", 0), "lead_persons": m.get("lead_persons", 0)})
        out["trend"]["desktop"].append({"visitors": d.get("visitors", 0), "lead_persons": d.get("lead_persons", 0)})
        tv, tl = sum(r["visitors"] for r in allv), sum(r["lead_persons"] for r in allv)
        out["trend"]["total"].append({"visitors": tv, "lead_persons": tl, "lead_rate": safe_rate(tl, tv)})

    # CRO ship ledger reads
    out["ledger_reads"] = ledger_reads(ph, base, LEAD)
    return out


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def prefill_area(txt):
    """Area from a WhatsApp prefill. Three live shapes: '... in Gulshan-e-Iqbal Karachi', '... in Karachi', commercial composer 'Area: X'."""
    if not txt:
        return None
    m = re.search(r"Area:\s*([^\n(]+)", txt)
    if m:
        return slug(m.group(1).split("&")[0])
    m = re.search(r"\bin ([A-Za-z0-9 \-]+?),? Karachi", txt)
    if m and m.group(1).strip().lower() not in ("", "karachi"):
        return slug(m.group(1))
    return None


def ledger_reads(ph, base, LEAD):
    """For each merged ledger entry: pre/post lead rate on its pages, by device. Same method as the 09-06 CRO read."""
    path = HERE / "ledger.json"
    entries = json.loads(path.read_text()) if path.exists() else []
    reads = []
    for e in entries:
        commit = e.get("commit")
        if not commit:
            continue
        ts = git("log", "-1", "--format=%cI", commit)
        if not ts:
            reads.append({"id": e["id"], "verdict": "not_on_main"}); continue
        ship = dt.datetime.fromisoformat(ts).astimezone(dt.timezone.utc)
        days = (dt.datetime.now(dt.timezone.utc) - ship).days
        if days < 7:
            reads.append({"id": e["id"], "days_live": days, "verdict": "too_early"}); continue
        span = min(days, 28)
        pages = ",".join(f"'{p}'" for p in e.get("pages", []))
        pfilter = f"AND coalesce(properties.$pathname,'') IN ({pages})" if pages else ""
        S = f"toDateTime('{ship.strftime('%Y-%m-%d %H:%M:%S')}')"
        rows = ph.rows(f"""SELECT if(timestamp >= {S}, 'post', 'pre') AS w, coalesce(properties.$device_type,'Other') AS device,
            count(DISTINCT if(event='$pageview',person_id,NULL)) AS visitors, count(DISTINCT if({LEAD},person_id,NULL)) AS leads
            FROM events WHERE timestamp >= {S} - INTERVAL {span} DAY AND timestamp < {S} + INTERVAL {span} DAY AND {base} {pfilter}
            GROUP BY w, device""")
        agg = {"pre": {"visitors": 0, "leads": 0}, "post": {"visitors": 0, "leads": 0}}
        dev = defaultdict(lambda: {"pre": {}, "post": {}})
        for r in rows:
            agg[r["w"]]["visitors"] += r["visitors"]; agg[r["w"]]["leads"] += r["leads"]
            dev[r["device"]][r["w"]] = {"visitors": r["visitors"], "leads": r["leads"], "rate": safe_rate(r["leads"], r["visitors"])}
        pre, post = safe_rate(agg["pre"]["leads"], agg["pre"]["visitors"]), safe_rate(agg["post"]["leads"], agg["post"]["visitors"])
        if agg["pre"]["leads"] + agg["post"]["leads"] < T["min_lead_persons_for_rates"] or pre is None or post is None:
            verdict = "too_early"
        elif post > pre * 1.15:
            verdict = "working"
        elif post < pre * 0.85:
            verdict = "worse"
        else:
            verdict = "flat"
        reads.append({"id": e["id"], "hypothesis": e.get("hypothesis"), "pages": e.get("pages"), "days_live": days, "window_days": span,
                      "pre": {**agg["pre"], "rate": pre}, "post": {**agg["post"], "rate": post}, "by_device": dev, "verdict": verdict})
    return reads


# ───────────────────────── GSC ─────────────────────────
def collect_gsc(W):
    from googleapiclient.discovery import build
    svc = build("searchconsole", "v1", credentials=google_creds(["https://www.googleapis.com/auth/webmasters.readonly"]), cache_discovery=False)
    site = CONFIG["gsc_site"]
    end = today() - dt.timedelta(days=CONFIG["gsc_lag_days"])
    G = {"this_week": (end - dt.timedelta(days=6), end), "last_week": (end - dt.timedelta(days=13), end - dt.timedelta(days=7)),
         "last_28d": (end - dt.timedelta(days=27), end), "prior_28d": (end - dt.timedelta(days=55), end - dt.timedelta(days=28))}

    def q(win, dims, limit=5000, extra=None):
        body = {"startDate": str(win[0]), "endDate": str(win[1]), "dimensions": dims, "rowLimit": limit, "dataState": "all", **(extra or {})}
        return svc.searchanalytics().query(siteUrl=site, body=body).execute().get("rows", [])

    def totals(win):
        r = q(win, [])
        if not r:
            return {"clicks": 0, "impressions": 0, "ctr": 0, "position": None}
        r = r[0]
        return {"clicks": r["clicks"], "impressions": r["impressions"], "ctr": round(r["ctr"], 4), "position": round(r["position"], 1)}

    out = {"windows": {k: [str(a), str(b)] for k, (a, b) in G.items()}, "totals": {k: totals(w) for k, w in G.items()}}
    t = out["totals"]
    out["deltas"] = {m: {"wow": pct_delta(t["this_week"][m], t["last_week"][m]), "mom": pct_delta(t["last_28d"][m], t["prior_28d"][m])} for m in ("clicks", "impressions")}
    out["deltas"]["position"] = {"wow": (round(t["this_week"]["position"] - t["last_week"]["position"], 1) if t["this_week"]["position"] and t["last_week"]["position"] else None),
                                 "mom": (round(t["last_28d"]["position"] - t["prior_28d"]["position"], 1) if t["last_28d"]["position"] and t["prior_28d"]["position"] else None)}
    out["by_device"] = {k: [{"device": r["keys"][0], "clicks": r["clicks"], "impressions": r["impressions"], "ctr": round(r["ctr"], 4), "position": round(r["position"], 1)} for r in q(w, ["device"])] for k, w in G.items()}

    def qp(win):
        return {(r["keys"][0], r["keys"][1]): {"query": r["keys"][0], "page": r["keys"][1].replace(CONFIG["site_url"], "") or "/", "clicks": r["clicks"],
                                              "impressions": r["impressions"], "ctr": round(r["ctr"], 4), "position": round(r["position"], 1)} for r in q(win, ["query", "page"])}
    cur, prev = qp(G["this_week"]), qp(G["last_week"])
    cur28, prev28 = qp(G["last_28d"]), qp(G["prior_28d"])
    movers = []
    for k, r in cur28.items():
        p = prev28.get(k)
        if not p:
            continue
        dpos, dclk = round(p["position"] - r["position"], 1), r["clicks"] - p["clicks"]
        if abs(dpos) >= T["mover_position_delta"] and r["impressions"] >= 10 or abs(dclk) >= T["mover_click_delta"]:
            movers.append({**r, "position_prev": p["position"], "position_delta": dpos, "clicks_prev": p["clicks"], "clicks_delta": dclk})
    out["movers_up"] = sorted([m for m in movers if m["position_delta"] > 0 or m["clicks_delta"] > 0], key=lambda m: (-m["clicks_delta"], -m["position_delta"]))[:15]
    out["movers_down"] = sorted([m for m in movers if m["position_delta"] < 0 or m["clicks_delta"] < 0], key=lambda m: (m["clicks_delta"], m["position_delta"]))[:15]

    def buckets(rows):
        b = {"p1_3": 0, "p4_10": 0, "p11_20": 0, "p21_plus": 0}
        for r in rows.values():
            pos = r["position"]
            b["p1_3" if pos <= 3 else "p4_10" if pos <= 10 else "p11_20" if pos <= 20 else "p21_plus"] += 1
        return b
    out["buckets"] = {"last_28d": buckets(cur28), "prior_28d": buckets(prev28), "this_week": buckets(cur), "last_week": buckets(prev)}
    out["low_ctr"] = sorted([r for r in cur28.values() if r["impressions"] >= T["low_ctr_min_impressions"] and r["ctr"] < T["low_ctr_max"]], key=lambda r: -r["impressions"])[:20]
    out["striking_distance"] = sorted([r for r in cur28.values() if 8 <= r["position"] <= 20 and r["impressions"] >= T["striking_min_impressions"]], key=lambda r: -r["impressions"])[:25]
    out["new_queries"] = sorted([r for k, r in cur.items() if k not in prev28 and r["impressions"] >= T["new_query_min_impressions"]], key=lambda r: -r["impressions"])[:20]
    out["top_queries_28d"] = sorted(cur28.values(), key=lambda r: -r["clicks"])[:25]
    pages = defaultdict(lambda: {"clicks": 0, "impressions": 0})
    pages_prev = defaultdict(lambda: {"clicks": 0, "impressions": 0})
    for r in cur28.values():
        pages[r["page"]]["clicks"] += r["clicks"]; pages[r["page"]]["impressions"] += r["impressions"]
    for r in prev28.values():
        pages_prev[r["page"]]["clicks"] += r["clicks"]; pages_prev[r["page"]]["impressions"] += r["impressions"]
    out["pages_28d"] = sorted([{"page": p, **v, "clicks_prev": pages_prev[p]["clicks"], "impressions_prev": pages_prev[p]["impressions"]} for p, v in pages.items()], key=lambda r: -r["clicks"])[:30]
    # 13-week trend from the date dimension (one call), weeks aligned to the GSC this_week end
    t_start = end - dt.timedelta(days=13 * 7 - 1)
    daily = {r["keys"][0]: r for r in q((t_start, end), ["date"], limit=100)}
    weeks = []
    for i in range(13):
        ws = t_start + dt.timedelta(days=7 * i)
        days = [daily.get(str(ws + dt.timedelta(days=j))) for j in range(7)]
        days = [d for d in days if d]
        clicks, impr = sum(d["clicks"] for d in days), sum(d["impressions"] for d in days)
        pos = round(sum(d["position"] * d["impressions"] for d in days) / impr, 1) if impr else None
        weeks.append({"week_start": str(ws), "clicks": clicks, "impressions": impr, "ctr": safe_rate(clicks, impr), "position": pos})
    out["trend"] = weeks
    return out


# ───────────────────────── Ahrefs ─────────────────────────
def collect_ahrefs(candidates):
    key = secret("AHREFS_API_KEY", "ahrefs-api-key.txt")
    if not key:
        raise RuntimeError("AHREFS_API_KEY missing")
    A = CONFIG["ahrefs"]; cc = A["country"]; date = str(today()); site = CONFIG["site"]
    calls = {"n": 0}

    def get(path, **params):
        calls["n"] += 1
        qs = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        req = urllib.request.Request(f"https://api.ahrefs.com/v3/{path}?{qs}", headers={"Authorization": f"Bearer {key}", "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            return {"_error": f"{e.code} {e.read().decode()[:200]}"}

    def overview(target):
        dr = get("site-explorer/domain-rating", target=target, date=date)
        bl = get("site-explorer/backlinks-stats", target=target, mode="subdomains", date=date)
        mt = get("site-explorer/metrics", target=target, country=cc, date=date, volume_mode="monthly")
        return {"domain": target, "dr": (dr.get("domain_rating") or {}).get("domain_rating"), "refdomains": (bl.get("metrics") or {}).get("live_refdomains"),
                "backlinks": (bl.get("metrics") or {}).get("live"), "org_keywords": (mt.get("metrics") or {}).get("org_keywords"), "org_traffic": (mt.get("metrics") or {}).get("org_traffic")}

    out = {"date": date, "site": overview(site)}
    prev = get("site-explorer/backlinks-stats", target=site, mode="subdomains", date=str(today() - dt.timedelta(days=7)))
    out["site"]["refdomains_prev_week"] = (prev.get("metrics") or {}).get("live_refdomains")
    rd = get("site-explorer/refdomains", target=site, mode="subdomains", date=date, select="domain,domain_rating,first_seen", order_by="first_seen:desc", limit=100)
    out["refdomains"] = rd.get("refdomains", []) if isinstance(rd, dict) else []
    ok = get("site-explorer/organic-keywords", target=site, country=cc, date=date, select="keyword,volume,keyword_difficulty,best_position,best_position_url,sum_traffic", order_by="sum_traffic:desc", limit=60)
    out["organic_keywords"] = ok.get("keywords", []) if isinstance(ok, dict) else []
    out["competitors"] = [overview(c) for c in CONFIG["competitors"]]
    ours = {k["keyword"].lower() for k in out["organic_keywords"]}
    gaps = []
    top3 = sorted([c for c in out["competitors"] if c.get("org_traffic")], key=lambda c: -(c["org_traffic"] or 0))[:A["competitor_top_pages"]]
    for c in top3:
        tp = get("site-explorer/top-pages", target=c["domain"], country=cc, date=date, select="url,sum_traffic,top_keyword,top_keyword_volume,top_keyword_best_position", order_by="sum_traffic:desc", limit=10)
        for p in tp.get("pages", []) if isinstance(tp, dict) else []:
            kw = (p.get("top_keyword") or "").lower()
            if kw and kw not in ours:
                gaps.append({"competitor": c["domain"], **p})
    out["competitor_gaps"] = sorted(gaps, key=lambda g: -(g.get("top_keyword_volume") or 0))[:20]
    cands = [c for c in dict.fromkeys([k.lower() for k in candidates]) if 3 <= len(c) <= 80][:A["keyword_candidates_max"]]
    if cands:
        kx = get("keywords-explorer/overview", country=cc, keywords=",".join(cands), select="keyword,volume,difficulty,cpc,clicks,parent_topic")
        out["keyword_candidates"] = kx.get("keywords", []) if isinstance(kx, dict) else [{"_error": kx}]
    else:
        out["keyword_candidates"] = []
    usage = get("subscription-info/limits-and-usage")
    out["units"] = usage.get("limits_and_usage", usage) if isinstance(usage, dict) else usage
    out["api_calls"] = calls["n"]
    return out


# ───────────────────────── Health ─────────────────────────
def collect_health():
    out = {}
    tok = secret("GH_TOKEN") or secret("GITHUB_TOKEN")
    try:
        if tok:
            b = http_json(f"https://api.github.com/repos/{CONFIG['repo']}/pages/builds/latest", {"Authorization": f"Bearer {tok}"})
        else:
            b = json.loads(subprocess.run(["gh", "api", f"repos/{CONFIG['repo']}/pages/builds/latest"], capture_output=True, text=True, check=True).stdout)
        built = b.get("commit") or ""
        head = git("rev-parse", "origin/main") or git("rev-parse", "HEAD")
        behind = git("rev-list", "--count", f"{built}..{head}") if built else ""
        out["pages_build"] = {"status": b.get("status"), "updated_at": b.get("updated_at"), "commit": built[:7], "error": (b.get("error") or {}).get("message"),
                              "commits_behind_main": int(behind) if behind.isdigit() else None}
    except Exception as e:
        out["pages_build"] = {"status": "unknown", "error": str(e)[:200]}
    try:
        live = urllib.request.urlopen(f"{CONFIG['site_url']}/sitemap.xml", timeout=30).read().decode()
        live_urls = set(re.findall(r"<loc>(.*?)</loc>", live))
    except Exception as e:
        live_urls, out["sitemap_error"] = set(), str(e)[:200]
    repo_urls = set(re.findall(r"<loc>(.*?)</loc>", (ROOT / "sitemap.xml").read_text())) if (ROOT / "sitemap.xml").exists() else set()
    out["sitemap"] = {"repo_urls": len(repo_urls), "live_urls": len(live_urls), "missing_live": sorted(repo_urls - live_urls)[:20], "extra_live": sorted(live_urls - repo_urls)[:20]}
    ct = ROOT / "tools/check-tracking.py"
    if ct.exists():
        r = subprocess.run([sys.executable, str(ct)], capture_output=True, text=True, cwd=ROOT)
        out["tracking"] = {"ok": r.returncode == 0, "output": r.stdout.strip()[-1500:]}
    schema_errors = []
    for p in sorted(ROOT.rglob("*.html")):
        if any(part in (".git", "tools", ".agents", ".github") for part in p.relative_to(ROOT).parts):
            continue
        for m in re.finditer(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', p.read_text(encoding="utf-8", errors="ignore"), re.S):
            try:
                json.loads(m.group(1))
            except json.JSONDecodeError as e:
                schema_errors.append({"page": p.relative_to(ROOT).as_posix(), "error": str(e)[:80]})
    out["schema_errors"] = schema_errors[:20]
    out["head_commit"] = git("log", "-1", "--format=%h %cs %s")
    # tracking-schema changes in the last 21 days: the report must say when numbers straddle a change
    out["instrumentation_commits"] = [l for l in git("log", "--since=21 days ago", "--format=%h %cs %s", "--", "prices.js", "wa-desktop.js", "book.html", "tools/check-tracking.py").splitlines() if l]
    return out


# ───────────────────────── CRO leaks + season ─────────────────────────
def cro_leaks(ph):
    if not ph:
        return []
    leaks = []
    f28 = ph["funnel"]["last_28d"]
    site_rate = f28["total"]["lead_rate"] or 0
    for r in ph["pages"]["last_28d"]:
        if r["path"] in CONFIG["money_pages"] and r["uv"] >= 15 and r["lead_rate"] is not None and site_rate and r["lead_rate"] < site_rate * T["leak_lead_rate_vs_site"]:
            leaks.append({"page": r["path"], "device": "all", "kind": "low_lead_rate", "lead_rate": r["lead_rate"], "site_rate": site_rate, "uv": r["uv"],
                          "lead_gap_persons": round(r["uv"] * site_rate - r["lead_persons"]), "evidence_ref": f"posthog.pages.last_28d[path={r['path']}]"})
        if r.get("scroll_p50") is not None and r["scroll_p50"] < T["low_scroll_pct"] and r["uv"] >= 15:
            leaks.append({"page": r["path"], "device": "all", "kind": "low_scroll", "scroll_p50": r["scroll_p50"], "uv": r["uv"], "evidence_ref": f"posthog.pages.last_28d[path={r['path']}].scroll_p50"})
        if r.get("rageclicks", 0) >= 3:
            leaks.append({"page": r["path"], "device": "all", "kind": "rageclicks", "rageclicks": r["rageclicks"], "evidence_ref": f"posthog.pages.last_28d[path={r['path']}].rageclicks"})
    for dev in ("mobile", "desktop"):
        d = f28.get(dev, {})
        if d.get("visitors", 0) >= 30 and site_rate and (d.get("lead_rate") or 0) < site_rate * T["leak_lead_rate_vs_site"]:
            leaks.append({"page": "site", "device": dev, "kind": "device_gap", "lead_rate": d["lead_rate"], "site_rate": site_rate, "visitors": d["visitors"],
                          "lead_gap_persons": round(d["visitors"] * site_rate - d["lead_persons"]), "evidence_ref": f"posthog.funnel.last_28d.{dev}"})
        if d.get("booking_started", 0) >= 10:
            leaks.append({"page": "/book", "device": dev, "kind": "booking_dropoff", "started": d["booking_started"], "handoff": d["handoff"],
                          "completion": safe_rate(d["handoff"], d["booking_started"]), "evidence_ref": f"posthog.funnel.last_28d.{dev}"})
    return sorted(leaks, key=lambda l: -(l.get("lead_gap_persons") or 0))


def season_now():
    m = today().month
    nxt = (today() + dt.timedelta(days=21)).month
    return {"active": [s for s in CONFIG["season"] if m in s["months"]], "opening_soon": [s for s in CONFIG["season"] if nxt in s["months"] and m not in s["months"]]}


# ───────────────────────── main ─────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip", default="")
    ap.add_argument("--ref", help="YYYY-MM-DD reference date (default today)")
    a = ap.parse_args()
    skip = set(filter(None, a.skip.split(",")))
    ref = dt.date.fromisoformat(a.ref) if a.ref else None
    W = windows(ref)
    OUT.mkdir(exist_ok=True)
    data = {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "week": iso_week_label(W["this_week"][0]),
            "windows": {k: [str(x), str(y)] for k, (x, y) in W.items()}, "site": CONFIG["site"], "errors": {}}
    if skip and (OUT / "report_data.json").exists():  # partial run: keep the sections we are not re-collecting
        old = json.loads((OUT / "report_data.json").read_text())
        data.update({k: old[k] for k in skip if k in old})
    for name, fn in (("posthog", lambda: collect_posthog(W)), ("gsc", lambda: collect_gsc(W))):
        if name in skip:
            continue
        t0 = time.time()
        try:
            data[name] = fn(); log(f"{name}: ok ({time.time() - t0:.0f}s)")
        except Exception as e:
            data["errors"][name] = str(e)[:500]; log(f"{name}: FAILED {e}")
    if "ahrefs" not in skip:
        g = data.get("gsc") or {}
        cands = [r["query"] for r in g.get("striking_distance", [])] + [r["query"] for r in g.get("new_queries", [])] + [r["query"] for r in g.get("low_ctr", [])]
        try:
            data["ahrefs"] = collect_ahrefs(cands); log("ahrefs: ok", data["ahrefs"].get("api_calls"), "calls")
        except Exception as e:
            data["errors"]["ahrefs"] = str(e)[:500]; log("ahrefs: FAILED", e)
    if "health" not in skip:
        try:
            data["health"] = collect_health(); log("health: ok")
        except Exception as e:
            data["errors"]["health"] = str(e)[:500]; log("health: FAILED", e)
    data["cro"] = {"leaks": cro_leaks(data.get("posthog")), "ledger_reads": (data.get("posthog") or {}).get("ledger_reads", [])}
    data["season"] = season_now()
    (OUT / "report_data.json").write_text(json.dumps(data, indent=1, default=str))
    log("wrote", OUT / "report_data.json", "errors:", data["errors"] or "none")
    return 1 if len(data["errors"]) >= 2 else 0


if __name__ == "__main__":
    sys.exit(main())
