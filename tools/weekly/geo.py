#!/usr/bin/env python3
"""geo.py: monthly GEO (AI answer-engine visibility) observation CLI for the SafaiKaro weekly routine.

This file only validates, stores and aggregates observations the routine agent (or a human) supplies.
It never calls a model or a web-search API itself. Competitor names, response text and any other free
text stay in output/geo/, which is gitignored (tools/weekly/output/ in the repo .gitignore) -- the repo
is public, so nothing here is written to a tracked path.

Subcommands
  due                       Prints "due: <reason>" and exits 0 when the monthly sample should run today
                             (first Monday of the month, or the last recorded run is 28+ days old, or
                             there is no recorded run yet). Prints "not due: <reason>" and exits 1 otherwise.
  record --data '<json>'    Validates one observation object against the schema below and appends it to
                             output/geo/observations-YYYY-MM.csv (month taken from the row's run_date).
                             Reads the JSON object from stdin if --data is omitted or "-".
  summarize [--month] [--fix]
                             Reads output/geo/observations-YYYY-MM.csv (current month by default), computes
                             the unbranded mention/citation rate and the branded accuracy rate, overall and
                             per engine, and writes output/geo/summary.json. --fix stores one plain-text
                             proposed fix in that file (chosen by the agent from the observed answers; this
                             tool does not choose it). Also stamps output/geo/last-run.json so `due` knows
                             a round happened this month.

Observation schema (one JSON object per `record` call; all fields required):
  observation_id           unique id, e.g. GEO-2026-10-06-01
  run_date                 YYYY-MM-DD, the local date the observation was made
  prompt_id                a prompt_id from geo-prompts.csv
  group                    unbranded | branded (must match the prompt's group in geo-prompts.csv)
  engine                   claude-web-search | chatgpt | gemini | perplexity | unavailable
  model                    visible model name/version; "" if engine is unavailable
  search_mode              e.g. "web search enabled"; "" if engine is unavailable
  location                 e.g. "Karachi, Pakistan"
  language                 e.g. "en"
  prompt                   the exact prompt text actually sent; "" if engine is unavailable
  response_summary         plain-text summary of what the engine said; "" if engine is unavailable
                            (when engine is unavailable, note which engine was skipped and why here)
  brand_mentioned           yes | no | unavailable (unavailable only when engine is unavailable)
  citation_urls             semicolon-separated URLs, or ""
  competitors_named_count   integer >= 0 (competitor names themselves are not a field: keep names, if
                             recorded at all, only in response_summary -- never in a git-tracked file)
  accuracy_verdict          accurate | partial | inaccurate | unavailable (required for a completed
                             branded row; "unavailable" otherwise)
  accuracy_notes            free text; required for a completed branded row

Usage
  python3 tools/weekly/geo.py due
  python3 tools/weekly/geo.py record --data '{"observation_id": "...", ...}'
  echo '{"observation_id": "...", ...}' | python3 tools/weekly/geo.py record
  python3 tools/weekly/geo.py summarize --fix "One sentence: the concrete fix to make next"
"""
import argparse, csv, datetime as dt, json, sys

from common import HERE, OUT, TZ, today

GEO_OUT = OUT / "geo"
PROMPTS_CSV = HERE / "geo-prompts.csv"
LAST_RUN = GEO_OUT / "last-run.json"
SUMMARY = GEO_OUT / "summary.json"

ENGINES = ["claude-web-search", "chatgpt", "gemini", "perplexity", "unavailable"]
GROUPS = ["unbranded", "branded"]
BRAND_MENTIONED = ["yes", "no", "unavailable"]
ACCURACY_VERDICTS = ["accurate", "partial", "inaccurate", "unavailable"]

FIELDS = [
    "observation_id", "run_date", "prompt_id", "group", "engine", "model", "search_mode",
    "location", "language", "prompt", "response_summary", "brand_mentioned", "citation_urls",
    "competitors_named_count", "accuracy_verdict", "accuracy_notes",
]


def load_prompts():
    if not PROMPTS_CSV.exists():
        return {}
    with PROMPTS_CSV.open(newline="", encoding="utf-8") as f:
        return {r["prompt_id"]: r for r in csv.DictReader(f)}


def is_due(ref, last_run_date):
    """True on the first Monday of ref's month, or when last_run_date is missing or 28+ days old."""
    if ref.weekday() == 0 and ref.day <= 7:
        return True, "first Monday of the month"
    if last_run_date is None:
        return True, "no recorded run yet"
    age = (ref - last_run_date).days
    if age >= 28:
        return True, f"last run {age} days ago"
    return False, f"last run {age} days ago"


def read_last_run():
    if not LAST_RUN.exists():
        return None
    try:
        d = json.loads(LAST_RUN.read_text()).get("date")
        return dt.date.fromisoformat(d) if d else None
    except (json.JSONDecodeError, ValueError, OSError):
        return None


def cmd_due(_args):
    due, reason = is_due(today(), read_last_run())
    print(f"{'due' if due else 'not due'}: {reason}")
    return 0 if due else 1


def validate_observation(row, prompts):
    """Returns a list of error strings; empty means the row is valid. `prompts` is load_prompts()'s dict
    (an empty dict skips the register cross-check, e.g. in a unit test with no CSV on disk)."""
    errors = [f"missing field: {f}" for f in FIELDS if f not in row]
    if errors:
        return errors
    if not str(row["observation_id"]).strip():
        errors.append("observation_id is required")
    try:
        dt.date.fromisoformat(row["run_date"])
    except (ValueError, TypeError):
        errors.append("run_date must be YYYY-MM-DD")
    pid = row["prompt_id"]
    if prompts and pid not in prompts:
        errors.append(f"prompt_id '{pid}' not in geo-prompts.csv")
    if row["group"] not in GROUPS:
        errors.append(f"group must be one of {GROUPS}")
    if prompts and pid in prompts and row["group"] != prompts[pid]["group"]:
        errors.append(f"group '{row['group']}' does not match the register's group '{prompts[pid]['group']}' for {pid}")
    if row["engine"] not in ENGINES:
        errors.append(f"engine must be one of {ENGINES}")
    if row["brand_mentioned"] not in BRAND_MENTIONED:
        errors.append(f"brand_mentioned must be one of {BRAND_MENTIONED}")
    if row["accuracy_verdict"] not in ACCURACY_VERDICTS:
        errors.append(f"accuracy_verdict must be one of {ACCURACY_VERDICTS}")
    unavailable = row["engine"] == "unavailable"
    if not unavailable:
        if not str(row["prompt"]).strip():
            errors.append("prompt is required unless engine is unavailable")
        if not str(row["response_summary"]).strip():
            errors.append("response_summary is required unless engine is unavailable")
        if row["brand_mentioned"] == "unavailable":
            errors.append("brand_mentioned must be yes/no when engine is not unavailable")
    if row["group"] == "branded" and not unavailable:
        if row["accuracy_verdict"] == "unavailable":
            errors.append("accuracy_verdict is required for a completed branded observation")
        if not str(row["accuracy_notes"]).strip():
            errors.append("accuracy_notes is required for a completed branded observation")
    try:
        if int(row["competitors_named_count"]) < 0:
            errors.append("competitors_named_count must be >= 0")
    except (TypeError, ValueError):
        errors.append("competitors_named_count must be an integer")
    return errors


def cmd_record(args):
    raw = args.data if (args.data and args.data != "-") else sys.stdin.read()
    try:
        row = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"invalid JSON: {e}", file=sys.stderr)
        return 2
    if not isinstance(row, dict):
        print("observation must be a JSON object", file=sys.stderr)
        return 2
    errors = validate_observation(row, load_prompts())
    if errors:
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        return 1
    GEO_OUT.mkdir(parents=True, exist_ok=True)
    path = GEO_OUT / f"observations-{row['run_date'][:7]}.csv"
    is_new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if is_new:
            w.writeheader()
        w.writerow({k: row[k] for k in FIELDS})
    print(f"recorded {row['observation_id']} to {path.relative_to(HERE.parent.parent)}")
    return 0


def load_observations(month):
    path = GEO_OUT / f"observations-{month}.csv"
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _rate(rows, pred):
    return round(sum(1 for r in rows if pred(r)) / len(rows), 4) if rows else None


def _by_engine(rows, rate_fields):
    """rate_fields: {output_key: predicate(row) -> bool}. Skips the 'unavailable' engine (nothing completed)."""
    out = {}
    for e in sorted({r["engine"] for r in rows if r["engine"] != "unavailable"}):
        er = [r for r in rows if r["engine"] == e]
        out[e] = {"n": len(er), **{k: _rate(er, pred) for k, pred in rate_fields.items()}}
    return out


def summarize_rows(rows):
    unbranded = [r for r in rows if r["group"] == "unbranded"]
    branded = [r for r in rows if r["group"] == "branded"]
    unb_completed = [r for r in unbranded if r["engine"] != "unavailable"]
    br_completed = [r for r in branded if r["engine"] != "unavailable"]
    mentioned = lambda r: r["brand_mentioned"] == "yes"
    cited = lambda r: bool(r["citation_urls"].strip())
    accurate = lambda r: r["accuracy_verdict"] == "accurate"
    return {
        "observation_counts": {
            "total": len(rows),
            "unbranded_completed": len(unb_completed),
            "branded_completed": len(br_completed),
            "unavailable": sum(1 for r in rows if r["engine"] == "unavailable"),
        },
        "unbranded": {
            "mention_rate": _rate(unb_completed, mentioned),
            "citation_rate": _rate(unb_completed, cited),
            "by_engine": _by_engine(unb_completed, {"mention_rate": mentioned, "citation_rate": cited}),
        },
        "branded": {
            "accuracy_rate": _rate(br_completed, accurate),
            "by_engine": _by_engine(br_completed, {"accuracy_rate": accurate}),
        },
    }


def cmd_summarize(args):
    month = args.month or today().strftime("%Y-%m")
    rows = load_observations(month)
    if not rows:
        print(f"no observations recorded for {month} yet ({GEO_OUT / f'observations-{month}.csv'})", file=sys.stderr)
        return 1
    summary = summarize_rows(rows)
    summary["month"] = month
    summary["generated_at"] = dt.datetime.now(TZ).isoformat()
    summary["proposed_fix"] = args.fix or None
    GEO_OUT.mkdir(parents=True, exist_ok=True)
    SUMMARY.write_text(json.dumps(summary, indent=2) + "\n")
    LAST_RUN.write_text(json.dumps({"date": today().isoformat(), "month": month}, indent=2) + "\n")
    print(f"wrote {SUMMARY.relative_to(HERE.parent.parent)}")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("due")
    p_record = sub.add_parser("record")
    p_record.add_argument("--data", default=None, help="JSON object for one observation row; reads stdin if omitted or '-'")
    p_sum = sub.add_parser("summarize")
    p_sum.add_argument("--month", default=None, help="YYYY-MM, default: current month")
    p_sum.add_argument("--fix", default=None, help="one proposed fix, stored in summary.json")
    args = ap.parse_args()
    return {"due": cmd_due, "record": cmd_record, "summarize": cmd_summarize}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
