"""Publish chart PNGs to the Cloudflare R2 public bucket so email clients that strip SVG (Gmail) still show them.
Stdlib SigV4 PUT, no boto3. Keys carry a random segment so URLs are unguessable; nothing else links to them.
Env: CLOUDFLARE_R2_ACCESS_KEY_ID, CLOUDFLARE_R2_SECRET_ACCESS_KEY, CLOUDFLARE_R2_ENDPOINT_URL, CLOUDFLARE_R2_BUCKET
(local dry runs read credentials/cloudflare-r2.env). Public base: R2_PUBLIC_BASE. Without them, send.py falls back to
data URIs (fine in a browser, blocked by Gmail)."""
import datetime as dt, hashlib, hmac, os, secrets as _secrets, urllib.parse, urllib.request
from pathlib import Path

ENV_FILE = Path(os.environ.get("R2_ENV_FILE", Path.home() / "Work/autonomous/credentials/cloudflare-r2.env"))
PUBLIC_BASE = os.environ.get("R2_PUBLIC_BASE", "https://pub-a735af451a3944e69779dde0547bc0b9.r2.dev")


def _env():
    e = {k: os.environ.get(k) for k in ("CLOUDFLARE_R2_ACCESS_KEY_ID", "CLOUDFLARE_R2_SECRET_ACCESS_KEY", "CLOUDFLARE_R2_ENDPOINT_URL", "CLOUDFLARE_R2_BUCKET", "CLOUDFLARE_R2_VSL_BUCKET")}
    if not e["CLOUDFLARE_R2_ACCESS_KEY_ID"] and ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                e.setdefault(k.strip(), None)
                if e.get(k.strip()) is None:
                    e[k.strip()] = v.strip().strip('"').strip("'")
    e["bucket"] = e.get("CLOUDFLARE_R2_BUCKET") or e.get("CLOUDFLARE_R2_VSL_BUCKET")
    return e


def available():
    e = _env()
    return bool(e.get("CLOUDFLARE_R2_ACCESS_KEY_ID") and e.get("CLOUDFLARE_R2_SECRET_ACCESS_KEY") and e.get("CLOUDFLARE_R2_ENDPOINT_URL") and e.get("bucket"))


def _sign(key, msg):
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def put(key, body, content_type="image/png"):
    """PUT object via S3 SigV4 (region auto). Returns the public URL."""
    e = _env()
    endpoint = e["CLOUDFLARE_R2_ENDPOINT_URL"].rstrip("/")
    host = urllib.parse.urlparse(endpoint).netloc
    path = f"/{e['bucket']}/{urllib.parse.quote(key)}"
    now = dt.datetime.now(dt.timezone.utc)
    amz_date, date = now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y%m%d")
    payload_hash = hashlib.sha256(body).hexdigest()
    headers = {"host": host, "x-amz-content-sha256": payload_hash, "x-amz-date": amz_date, "content-type": content_type}
    signed = ";".join(sorted(headers))
    canonical = "\n".join(["PUT", path, "", *(f"{k}:{headers[k]}" for k in sorted(headers)), "", signed, payload_hash])
    scope = f"{date}/auto/s3/aws4_request"
    sts = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical.encode()).hexdigest()])
    k = _sign(_sign(_sign(_sign(("AWS4" + e["CLOUDFLARE_R2_SECRET_ACCESS_KEY"]).encode(), date), "auto"), "s3"), "aws4_request")
    sig = hmac.new(k, sts.encode(), hashlib.sha256).hexdigest()
    auth = f"AWS4-HMAC-SHA256 Credential={e['CLOUDFLARE_R2_ACCESS_KEY_ID']}/{scope}, SignedHeaders={signed}, Signature={sig}"
    req = urllib.request.Request(endpoint + path, data=body, method="PUT", headers={**{k: v for k, v in headers.items() if k != "host"}, "Authorization": auth})
    with urllib.request.urlopen(req, timeout=60) as r:
        r.read()
    return f"{PUBLIC_BASE}/{key}"


def publish_run(week):
    """Returns a function name -> url that uploads under one random run prefix."""
    prefix = f"safaikaro-weekly/{week}/{_secrets.token_urlsafe(12)}"
    return lambda name, png: put(f"{prefix}/{name}.png", png)
