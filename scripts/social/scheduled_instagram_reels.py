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


_FACEBOOK_UPLOAD_HOSTS = {"rupload.facebook.com"}


def _upload_url_allowed(value):
    parsed = urlparse(value or "")
    return parsed.scheme == "https" and (parsed.hostname or "").lower().rstrip(".") in _FACEBOOK_UPLOAD_HOSTS


def _facebook(value):
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) - {"video_path", "sha256", "caption"}:
        raise RunnerError("facebook fields are invalid")
    if not isinstance(value.get("video_path"), str) or not value["video_path"].strip():
        raise RunnerError("facebook video_path is required")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", value.get("sha256", "")):
        raise RunnerError("facebook sha256 must be a 64-character digest")
    if not isinstance(value.get("caption"), str) or not value["caption"].strip():
        raise RunnerError("facebook caption is required")
    if not Path(value["video_path"]).is_file():
        raise RunnerError("facebook media file does not exist")
    if _sha256(value["video_path"]).lower() != value["sha256"].lower():
        raise RunnerError("facebook media hash does not match the plan")
    return {"video_path": value["video_path"], "sha256": value["sha256"], "caption": value["caption"]}


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

    def raw_post(url, headers, body):
        # Reel bytes go to a non-graph Meta upload host; never follow a redirect with the token.
        if not _upload_url_allowed(url):
            raise RunnerError("Meta upload URL is not an approved host")
        request_obj = Request(url, data=body, method="POST", headers=dict(headers))
        try:
            with urlopen(request_obj, timeout=120) as response:
                payload = response.read(max_media_bytes + 1)
                parsed_body = json.loads(payload.decode()) if payload else {}
        except Exception as exc:
            raise RunnerError("Meta upload request failed") from exc
        if not isinstance(parsed_body, dict):
            raise RunnerError("Meta returned an invalid response")
        return parsed_body

    request.raw_post = raw_post
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


def _upload(http, url, headers, body):
    raw_post = getattr(http, "raw_post", None)
    if raw_post is None:
        raise RunnerError("HTTP transport cannot upload raw media")
    if not _upload_url_allowed(url):
        raise RunnerError("Meta upload URL is not an approved host")
    try:
        result = raw_post(url, headers, body)
    except RunnerError:
        raise
    except Exception as exc:
        raise RunnerError("Meta upload request failed") from exc
    if not isinstance(result, dict):
        raise RunnerError("Meta returned an invalid response")
    if result.get("error") or result.get("success") is False:
        raise RunnerError("Meta upload was rejected")
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
        if job.get("facebook") is not None:
            job["facebook"] = _facebook(job["facebook"])
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


def _facebook_page(env):
    page_id = str(env.get("SOCIAL_FACEBOOK_PAGE_ID") or "")
    if not page_id.isdigit():
        raise RunnerError("Facebook Page id is missing or invalid")
    return page_id


def _facebook_duplicate(http, page_id, caption):
    result = _call(http, "GET", f"/{page_id}/video_reels?fields=id,description&limit=100")
    reels = result.get("data")
    if not isinstance(reels, list):
        raise RunnerError("Facebook Reel history is unavailable")
    if any(isinstance(item, dict) and item.get("description") == caption for item in reels):
        raise RunnerError("duplicate Facebook caption already exists")


def _facebook_finish(http, page_id, video_id, caption):
    # The finish POST publishes server-side even when its body is an unexpected
    # shape, so it is issued exactly once and the reconcile GET is the authority.
    params = {"upload_phase": "finish", "video_state": "PUBLISHED", "video_id": video_id, "description": caption, "is_ai_generated": "true"}
    try:
        result = http("POST", f"/{page_id}/video_reels", params)
    except Exception:
        return {"parsed": False}
    return result if isinstance(result, dict) else {"parsed": False}


def _facebook_published(details):
    status = details.get("status")
    phase = status.get("publishing_phase") if isinstance(status, dict) else None
    return isinstance(phase, dict) and phase.get("publish_status") == "published"


def _publish_facebook(env, config, http, job, receipt, receipt_path):
    facebook = job["facebook"]
    page_id = _facebook_page(env)
    state = {"phase": "facebook_preflight", "page_id": page_id, "sha256": facebook["sha256"]}
    receipt["facebook"] = state
    _atomic_write(receipt_path, receipt)
    try:
        _facebook_duplicate(http, page_id, facebook["caption"])
    except RunnerError:
        state["phase"] = "facebook_refused"
        _atomic_write(receipt_path, receipt)
        raise
    state["phase"] = "facebook_start"
    _atomic_write(receipt_path, receipt)
    video_id = None
    try:
        started = _call(http, "POST", f"/{page_id}/video_reels", {"upload_phase": "start", "is_ai_generated": "true"})
        video_id = started.get("video_id") or started.get("id")
        upload_url = started.get("upload_url")
        if not video_id or not isinstance(upload_url, str) or not _upload_url_allowed(upload_url):
            raise RunnerError("Facebook start response was incomplete")
        video_id = str(video_id)
        state.update({"phase": "facebook_uploading", "video_id": video_id})
        _atomic_write(receipt_path, receipt)
        body = Path(facebook["video_path"]).read_bytes()
        headers = {"Authorization": f"OAuth {config['token']}", "Content-Type": "video/mp4", "offset": "0", "file_size": str(len(body))}
        _upload(http, upload_url, headers, body)
        state["phase"] = "facebook_finishing"
        _atomic_write(receipt_path, receipt)
        finished = _facebook_finish(http, page_id, video_id, facebook["caption"])
        state.update({"phase": "facebook_reconciling", "finish_keys": sorted(str(key) for key in finished)})
        _atomic_write(receipt_path, receipt)
        details = _call(http, "GET", f"/{video_id}", {"fields": "status,published,permalink_url"})
        if not _facebook_published(details):
            raise RunnerError("Facebook Reel did not reconcile as published")
        state.update({"phase": "facebook_published", "video_id": video_id, "permalink_url": details.get("permalink_url")})
        _atomic_write(receipt_path, receipt)
    except Exception as exc:
        state.update({"phase": "facebook_uncertain", "video_id": video_id})
        _atomic_write(receipt_path, receipt)
        if isinstance(exc, RunnerError):
            raise
        raise RunnerError("Facebook delivery is uncertain; reconcile before retrying") from exc
    return state


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
    if job.get("facebook"):
        _publish_facebook(env, config, http, job, receipt, receipt_path)
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
