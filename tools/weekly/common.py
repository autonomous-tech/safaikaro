"""Shared helpers for the weekly routine: config, credentials, windows, HogQL, HTTP."""
import base64, datetime as dt, json, os, subprocess, sys, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent          # site repo root
OUT = HERE / "output"
CONFIG = json.loads((HERE / "config.json").read_text())
TZ = ZoneInfo(CONFIG["timezone"])
# ponytail: local dry runs read the workspace credentials dir; the routine uses env vars.
CREDS_DIR = Path(os.environ.get("SAFAIKARO_CREDS_DIR", Path.home() / "Work/autonomous/credentials/safaikaro"))
WS_CREDS = CREDS_DIR.parent


def secret(env_name, filename=None, dir_=None):
    v = os.environ.get(env_name)
    if v:
        return v.strip()
    p = (dir_ or CREDS_DIR) / filename if filename else None
    if p and p.exists():
        return p.read_text().strip()
    return None


def google_creds(scopes):
    from google.oauth2 import service_account
    b64 = os.environ.get("GOOGLE_SERVICE_ACCOUNT_B64")
    if b64:
        info = json.loads(base64.b64decode(b64))
        return service_account.Credentials.from_service_account_info(info, scopes=scopes)
    f = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE") or str(CREDS_DIR / "google-service-account.json")
    return service_account.Credentials.from_service_account_file(f, scopes=scopes)


def today():
    return dt.datetime.now(TZ).date()


def windows(ref=None):
    """ISO-week windows (Mon..Sun) in Asia/Karachi. Run on Monday => this_week is the week that just ended.
    Also 28-day windows for the MoM read. Values are (start_date, end_date) inclusive."""
    d = ref or today()
    last_sun = d - dt.timedelta(days=d.weekday() + 1)
    this_mon = last_sun - dt.timedelta(days=6)
    w = {
        "this_week": (this_mon, last_sun),
        "last_week": (this_mon - dt.timedelta(days=7), last_sun - dt.timedelta(days=7)),
        "week_4_ago": (this_mon - dt.timedelta(days=28), last_sun - dt.timedelta(days=28)),
        "last_28d": (last_sun - dt.timedelta(days=27), last_sun),
        "prior_28d": (last_sun - dt.timedelta(days=55), last_sun - dt.timedelta(days=28)),
    }
    return w


def iso_week_label(d):
    y, wk, _ = d.isocalendar()
    return f"{y}-W{wk:02d}"


def pct_delta(cur, prev):
    if prev in (None, 0) or cur is None:
        return None
    return round((cur - prev) / prev * 100, 1)


def safe_rate(num, den):
    return round(num / den, 4) if den else None


def http_json(url, headers=None, data=None, method=None, timeout=90):
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, method=method or ("POST" if body else "GET"),
                                 headers={"Accept": "application/json", **(headers or {}),
                                          **({"Content-Type": "application/json"} if body else {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode() or "null")


class PostHog:
    def __init__(self):
        self.cfg = CONFIG["posthog"]
        self.key = secret("POSTHOG_API_KEY", "posthog-read-key.txt")
        if not self.key:
            raise RuntimeError("POSTHOG_API_KEY missing")
        ids = ",".join(f"'{i}'" for i in self.cfg["test_distinct_ids"])
        self.excl = (f"distinct_id NOT IN ({ids}) AND NOT match(coalesce(properties.$host,''), "
                     "'^(localhost|127\\\\.0\\\\.0\\\\.1)($|:)')")
        self.karachi = "coalesce(properties.$geoip_city_name,'') IN ('Karachi','')"
        self.lead = "event IN (" + ",".join(f"'{e}'" for e in self.cfg["lead_events"]) + ")"

    RETRY_CODES = (429, 502, 503, 504)

    def q(self, sql, attempts=3):
        """One HogQL query. Transient errors (429/5xx timeouts) are retried with backoff:
        a single 504 must not empty the whole PostHog section of the report."""
        url = f"{self.cfg['host']}/api/projects/{self.cfg['project_id']}/query/"
        for i in range(attempts):
            try:
                res = http_json(url, {"Authorization": f"Bearer {self.key}"}, {"query": {"kind": "HogQLQuery", "query": sql}}, timeout=180)
                return res.get("results", []), res.get("columns", [])
            except urllib.error.HTTPError as e:
                body = e.read().decode()[:300]
                if e.code in self.RETRY_CODES and i < attempts - 1:
                    log(f"HogQL {e.code}, retry {i + 1}/{attempts - 1} in {5 * (i + 1)}s")
                    time.sleep(5 * (i + 1))
                    continue
                raise RuntimeError(f"HogQL {e.code}: {body}\nSQL: {sql[:300]}")

    def rows(self, sql):
        rows, cols = self.q(sql)
        return [dict(zip(cols, r)) for r in rows]

    @staticmethod
    def between(win):
        s, e = win
        return f"timestamp >= toDateTime('{s} 00:00:00', 'Asia/Karachi') AND timestamp < toDateTime('{e + dt.timedelta(days=1)} 00:00:00', 'Asia/Karachi')"


def git(*args, cwd=None):
    return subprocess.run(["git", *args], cwd=cwd or ROOT, capture_output=True, text=True).stdout.strip()


def log(*a):
    print(*a, file=sys.stderr, flush=True)
