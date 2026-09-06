#!/usr/bin/env python3
"""hog.py: HogQL CLI for the analyst loop. Read-only. Every query is logged to output/analyst_queries.jsonl
with an id the agent cites as evidence_ref (e.g. "hog:q07"). Capped per run (config posthog.analyst_query_cap).

Usage: python tools/weekly/hog.py "SELECT event, count() FROM events WHERE timestamp > now() - INTERVAL 7 DAY GROUP BY event"
Rules enforced: SELECT only, LIMIT <= 200 added if missing, 28-day lookback is the agent's responsibility.
"""
import json, re, sys, datetime as dt

from common import CONFIG, OUT, PostHog, log

LOG = OUT / "analyst_queries.jsonl"


def main():
    if len(sys.argv) < 2:
        print(__doc__); return 2
    sql = " ".join(sys.argv[1:]).strip().rstrip(";")
    if not re.match(r"^\s*(SELECT|WITH)\b", sql, re.I):
        print("only SELECT/WITH queries", file=sys.stderr); return 2
    if not re.search(r"\bLIMIT\s+\d+", sql, re.I):
        sql += " LIMIT 200"
    else:
        sql = re.sub(r"\bLIMIT\s+(\d+)", lambda m: f"LIMIT {min(int(m.group(1)), 200)}", sql, flags=re.I)
    OUT.mkdir(exist_ok=True)
    n = sum(1 for _ in LOG.open()) if LOG.exists() else 0
    cap = CONFIG["posthog"]["analyst_query_cap"]
    if n >= cap:
        print(f"query cap {cap} reached for this run", file=sys.stderr); return 3
    qid = f"hog:q{n + 1:02d}"
    ph = PostHog()
    try:
        rows, cols = ph.q(sql)
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        with LOG.open("a") as f:
            f.write(json.dumps({"id": qid, "sql": sql, "error": str(e)[:300], "at": dt.datetime.now(dt.timezone.utc).isoformat()}) + "\n")
        return 1
    with LOG.open("a") as f:
        f.write(json.dumps({"id": qid, "sql": sql, "rows": len(rows), "at": dt.datetime.now(dt.timezone.utc).isoformat()}) + "\n")
    print(json.dumps({"id": qid, "columns": cols, "rows": rows}, default=str, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
