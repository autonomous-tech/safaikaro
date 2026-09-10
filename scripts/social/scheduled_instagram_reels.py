#!/usr/bin/env python3
"""Fail-closed, one-post-per-day Instagram Reel scheduler.

Validation performs GETs only.  Execution is intended for a scheduled GitHub
Actions run and never retries a POST after an exception or timeout.
"""
import argparse
import hashlib
import ipaddress
import json
import os
import re
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, HTTPRedirectHandler, build_opener


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def urlopen(request, timeout):
    # Never forward a credential-bearing request across a redirect.
    return build_opener(_NoRedirect()).open(request, timeout=timeout)


class RunnerError(RuntimeError):
    pass


def _parse_time(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise RunnerError("scheduled_at must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise RunnerError("scheduled_at must include a timezone")
    return parsed.astimezone(timezone.utc)


def _public_https(value):
    parsed = urlparse(value or "")
    if parsed.scheme != "https" or not parsed.hostname:
        return False
    try:
        address = ipaddress.ip_address(parsed.hostname)
        return not (address.is_private or address.is_loopback or address.is_link_local)
    except ValueError:
        return parsed.hostname.lower() not in {"localhost", "localhost.localdomain"}


def _native_audio(value):
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) - {"audio_id", "id", "audio_volume", "video_volume"}:
        raise RunnerError("native_audio fields are invalid")
    audio_id = value.get("audio_id", value.get("id"))
    if not isinstance(audio_id, str) or not audio_id.isdigit():
        raise RunnerError("native_audio id is invalid")
    result = {"audio_id": audio_id}
    for key in ("audio_volume", "video_volume"):
        volume = value.get(key, 100)
        if isinstance(volume, bool) or not isinstance(volume, int) or not 1 <= volume <= 100:
            raise RunnerError("native_audio volume is invalid")
        result[key] = volume
    return result


def _real_http(token, version, github_token=None):
    graph_base = f"https://graph.facebook.com/{version.strip('/')}"
    max_media_bytes = 250 * 1024 * 1024

    def request(method, path, params=None):
        params = dict(params or {})
        parsed = urlparse(path)
        absolute = bool(parsed.scheme and parsed.netloc)
        url = path if absolute else graph_base + path
        if method == "GET":
            if params:
                url += ("&" if "?" in url else "?") + urlencode(params)
            body = None
        else:
            body = urlencode({key: json.dumps(value) if isinstance(value, (dict, list)) else value for key, value in params.items()}).encode()
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        if absolute and parsed.hostname == "api.github.com" and github_token:
            headers["Authorization"] = f"Bearer {github_token}"
        elif not absolute:
            headers["Authorization"] = f"Bearer {token}"
        request_obj = Request(url, data=body, method=method, headers=headers)
        try:
            with urlopen(request_obj, timeout=45) as response:
                payload = response.read(max_media_bytes + 1)
                if absolute and parsed.hostname != "api.github.com":
                    if len(payload) > max_media_bytes:
                        raise RunnerError("remote media exceeds size limit")
                    digest = hashlib.sha256(payload).hexdigest()
                    return {"status": response.status, "content_type": response.headers.get("Content-Type", ""), "sha256": digest}
                parsed = json.loads(payload.decode()) if payload else {}
                if not isinstance(parsed, dict):
                    raise RunnerError("Meta returned an invalid response")
                return parsed
        except RunnerError:
            raise
        except Exception as exc:
            raise RunnerError(f"Meta {method} request failed") from exc

    return request


def _config(env):
    values = {
        "ig_id": env.get("SOCIAL_INSTAGRAM_USER_ID") or env.get("META_INSTAGRAM_USER_ID"),
        "version": env.get("SOCIAL_META_API_VERSION") or env.get("META_GRAPH_API_VERSION"),
        "token": env.get("SOCIAL_META_PAGE_TOKEN") or env.get("META_ACCESS_TOKEN"),
    }
    if not all(values.values()):
        raise RunnerError("Meta account configuration is incomplete")
    if not re.fullmatch(r"v\d+(?:\.\d+)?", values["version"]):
        raise RunnerError("Meta API version is invalid")
    return values


def _call(http, method, url, params=None):
    try:
        result = http(method, url, params or {})
    except RunnerError:
        raise
    except Exception as exc:
        raise RunnerError(f"HTTP {method} request failed") from exc
    if not isinstance(result, dict):
        raise RunnerError("Meta returned an invalid response")
    if result.get("error") or result.get("success") is False:
        raise RunnerError(f"Meta {method} request was rejected")
    return result


def _validate_account(plan, config, http):
    account = _call(http, "GET", f"/{config['ig_id']}", {"fields": "id,username"})
    if account.get("id") != config["ig_id"] or account.get("username") != plan.get("instagram_username", "safaikaro.pk"):
        raise RunnerError("Instagram account identity does not match the plan")


def _validate_track(job, http):
    audio = job.get("native_audio")
    if not audio:
        raise RunnerError("native_audio is required for scheduled Reels")
    audio_id = audio["audio_id"]
    track = _call(http, "GET", f"/{audio_id}?user_id={quote(job['_ig_id'])}")
    if track.get("audio_id") != audio_id or not track.get("title") or not track.get("display_artist"):
        raise RunnerError("native audio track could not be verified")


def validate_plan(plan, config, http, now=None):
    if not isinstance(plan, dict) or not isinstance(plan.get("jobs"), list) or not plan["jobs"]:
        raise RunnerError("plan must contain jobs")
    if not isinstance(plan.get("authorized"), bool):
        raise RunnerError("plan authorization must be explicit")
    if not config.get("ig_id") or not config.get("version") or not config.get("token"):
        raise RunnerError("Meta account configuration is incomplete")
    _validate_account(plan, config, http)
    seen_dates = set()
    valid = []
    for job in plan["jobs"]:
        if not isinstance(job, dict) or job.get("platform", "instagram") != "instagram" or job.get("format", "reel") != "reel":
            raise RunnerError("only Instagram Reel jobs are allowed")
        scheduled = _parse_time(job.get("scheduled_at"))
        if scheduled.date() in seen_dates:
            raise RunnerError("only one Reel may be planned per UTC date")
        seen_dates.add(scheduled.date())
        if not _public_https(job.get("video_url")):
            raise RunnerError("video_url must be public HTTPS")
        if not re.fullmatch(r"[0-9a-fA-F]{64}", job.get("sha256", "")):
            raise RunnerError("sha256 must be a 64-character digest")
        if not isinstance(job.get("caption"), str) or not job["caption"].strip():
            raise RunnerError("caption is required")
        job["native_audio"] = _native_audio(job.get("native_audio"))
        job["_ig_id"] = config["ig_id"]
        _validate_track(job, http)
        track = _call(http, "GET", job["video_url"])
        if track.get("status") not in (200, 206) or "video" not in str(track.get("content_type", "")).lower():
            raise RunnerError("video_url did not return a video track")
        if track.get("sha256", "").lower() != job["sha256"].lower():
            raise RunnerError("remote media hash does not match the plan")
        job.pop("_ig_id", None)
        valid.append(job)
    return valid


def _sha256(path):
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise RunnerError("local media could not be read") from exc
    return digest.hexdigest()


def _atomic_write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _guard_prior_run(env, http, target):
    repository = env.get("GITHUB_REPOSITORY")
    workflow = env.get("SAFAIKARO_WORKFLOW_FILE") or env.get("GITHUB_WORKFLOW_FILE") or env.get("GITHUB_WORKFLOW_ID")
    run_id = env.get("GITHUB_RUN_ID")
    token = env.get("GITHUB_TOKEN") or env.get("GH_TOKEN")
    api = env.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")
    if not all((repository, workflow, run_id, token)):
        raise RunnerError("GitHub run identity is incomplete")
    url = f"{api}/repos/{quote(repository, safe='/')}/actions/workflows/{quote(workflow, safe='')}/runs?event=schedule&per_page=100"
    result = _call(http, "GET", url)
    runs = result.get("workflow_runs")
    if not isinstance(runs, list):
        raise RunnerError("GitHub workflow history is unavailable")
    for run in runs:
        if not isinstance(run, dict):
            raise RunnerError("GitHub workflow history is malformed")
        if str(run.get("id")) == str(run_id):
            continue
        stamp = run.get("run_started_at") or run.get("created_at")
        if stamp and _parse_time(stamp).date() == target.date():
            raise RunnerError("a prior scheduled workflow run already exists for this UTC date")


def _recent_duplicate(env, config, http, caption):
    result = _call(http, "GET", f"/{config['ig_id']}/media?fields=id,caption,permalink,timestamp&limit=100")
    media = result.get("data")
    if not isinstance(media, list):
        raise RunnerError("Instagram media history is unavailable")
    if any(isinstance(item, dict) and item.get("caption") == caption for item in media):
        raise RunnerError("duplicate Instagram caption already exists")


def _poll(http, config, container_id, sleep, clock):
    deadline = clock() + 900
    while True:
        result = _call(http, "GET", f"/{container_id}", {"fields": "status_code"})
        status = result.get("status_code")
        if status == "FINISHED":
            return
        if status in {"ERROR", "EXPIRED"}:
            raise RunnerError("Instagram media container failed")
        if clock() >= deadline:
            raise RunnerError("Instagram media container timed out")
        sleep(min(30, max(1, deadline - clock())))


def execute(plan, env, http, now=None, receipt_path=None, sleep=time.sleep, now_fn=None):
    if env.get("GITHUB_EVENT_NAME") != "schedule":
        raise RunnerError("execution is allowed only for schedule events")
    if env.get("GITHUB_RUN_ATTEMPT", "1") != "1":
        raise RunnerError("scheduled attempt is not the first attempt")
    if not plan.get("authorized"):
        raise RunnerError("plan is not authorized for execution")
    config = _config(env)
    http = http or _real_http(config["token"], config["version"], env.get("GITHUB_TOKEN") or env.get("GH_TOKEN"))
    jobs = validate_plan(plan, config, http, now)
    current = now or datetime.now(timezone.utc)
    today = [job for job in jobs if _parse_time(job["scheduled_at"]).date() == current.astimezone(timezone.utc).date()]
    if len(today) != 1:
        raise RunnerError("execution requires exactly one job for today's UTC date")
    job = today[0]
    target = _parse_time(job["scheduled_at"])
    if current < target - timedelta(minutes=10):
        raise RunnerError("execution started too early")
    if current > target + timedelta(hours=2):
        raise RunnerError("scheduled job is beyond its lateness window")
    media_path = job.get("video_path") or env.get("SCHEDULED_MEDIA_PATH")
    if media_path and _sha256(media_path).lower() != job["sha256"].lower():
        raise RunnerError("local media hash does not match the plan")
    _guard_prior_run(env, http, target)
    _recent_duplicate(env, config, http, job["caption"])
    if not receipt_path:
        raise RunnerError("receipt path is required")
    receipt = {"job_id": job["id"], "sha256": job["sha256"], "native_audio_attribution": "unverified", "history": []}
    _atomic_write(receipt_path, {**receipt, "phase": "create"})
    params = {"media_type": "REELS", "video_url": job["video_url"], "caption": job["caption"], "share_to_feed": True, "is_ai_generated": True}
    if job.get("native_audio"):
        params["audio_configuration"] = job["native_audio"]
    created = _call(http, "POST", f"/{config['ig_id']}/media", params)
    container_id = created.get("id")
    if not container_id:
        raise RunnerError("Instagram did not return a media container")
    receipt["history"].append({"phase": "create", "container_id": container_id})
    _atomic_write(receipt_path, {**receipt, "phase": "created"})
    _poll(http, config, container_id, sleep, time.monotonic)
    wall_clock = now_fn or ((lambda: now) if now is not None else (lambda: datetime.now(timezone.utc)))
    while wall_clock() < target:
        sleep(min(30, max(1, (target - wall_clock()).total_seconds())))
    check = wall_clock()
    if check > target + timedelta(hours=2):
        raise RunnerError("scheduled job passed its lateness window before publish")
    receipt["phase"] = "publish"
    _atomic_write(receipt_path, receipt)
    published = _call(http, "POST", f"/{config['ig_id']}/media_publish", {"creation_id": container_id})
    published_id = published.get("id")
    if not published_id:
        raise RunnerError("Instagram publish returned no media id")
    receipt["history"].append({"phase": "publish", "id": published_id})
    _atomic_write(receipt_path, {**receipt, "phase": "published_pending_readback"})
    details = _call(http, "GET", f"/{published_id}", {"fields": "id,caption,permalink,timestamp"})
    if details.get("id") != published_id or details.get("caption") != job["caption"] or not details.get("permalink"):
        raise RunnerError("Instagram publish readback did not match the plan")
    receipt.update({"phase": "published", "id": published_id, "permalink": details.get("permalink")})
    _atomic_write(receipt_path, receipt)
    return {key: receipt.get(key) for key in ("id", "permalink", "phase")}


def main(argv=None):
    parser = argparse.ArgumentParser(description="validate or execute one scheduled Instagram Reel")
    parser.add_argument("--plan", required=True)
    parser.add_argument("--receipt", default=os.environ.get("SCHEDULED_RECEIPT_PATH"))
    parser.add_argument("--execute", action="store_true", help="execute only from an eligible scheduled workflow")
    parser.add_argument("--media-path")
    args = parser.parse_args(argv)
    with open(args.plan, encoding="utf-8") as stream:
        plan = json.load(stream)
    env = dict(os.environ)
    if args.media_path:
        env["SCHEDULED_MEDIA_PATH"] = args.media_path
    config = _config(env)
    http = _real_http(config["token"], config["version"], env.get("GITHUB_TOKEN") or env.get("GH_TOKEN"))
    if not args.execute:
        jobs = validate_plan(plan, config, http)
        if env.get("GITHUB_ACTIONS") == "true":
            for job in jobs:
                _guard_prior_run(env, http, _parse_time(job["scheduled_at"]))
        if args.receipt:
            _atomic_write(args.receipt, {"phase": "validated", "job_ids": [job["id"] for job in jobs]})
        print(json.dumps({"phase": "validated", "jobs": [job["id"] for job in jobs]}))
        return 0
    result = execute(plan, env, http, receipt_path=args.receipt)
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RunnerError as exc:
        print(json.dumps({"phase": "blocked", "error": str(exc)}))
        raise SystemExit(2)
