import hashlib
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from scheduled_instagram_reels import RunnerError, _real_http, execute, validate_plan


NOW = datetime.fromisoformat("2026-09-11T08:00:00+00:00")


class FakeHTTP:
    def __init__(self, video_url, media=None, prior_runs=None, account=None, statuses=None):
        self.video_url = video_url
        self.media = media if media is not None else []
        self.prior_runs = prior_runs if prior_runs is not None else []
        self.account = account or {"id": "ig-1", "username": "safaikaro.pk"}
        self.statuses = list(statuses or [])
        self.calls = []

    def __call__(self, method, url, params=None, headers=None):
        self.calls.append((method, url, params or {}))
        if method == "GET" and url == self.video_url:
            return {"status": 200, "content_type": "video/mp4", "sha256": hashlib.sha256(b"video").hexdigest()}
        if method == "GET" and url.endswith("/ig-1"):
            return self.account
        if method == "GET" and "1759672808494145" in url:
            return {"audio_id": "1759672808494145", "title": "BirdWatching", "display_artist": "Danny Peter Wolf"}
        if method == "GET" and url.endswith("/media-1"):
            return {"id": "media-1", "caption": getattr(self, "caption", "caption"), "permalink": "https://instagram.com/reel/media-1", "timestamp": "2026-09-11T08:00:00Z"}
        if method == "GET" and "/media?" in url:
            return {"data": self.media}
        if method == "GET" and "/actions/workflows/" in url:
            return {"workflow_runs": self.prior_runs}
        if method == "GET" and ("/media-container" in url or url.endswith("/container-1")):
            return {"status_code": self.statuses.pop(0) if self.statuses else "FINISHED"}
        if method == "POST" and url.endswith("/media"):
            self.caption = (params or {}).get("caption")
            return {"id": "container-1"}
        if method == "POST" and url.endswith("/media_publish"):
            return {"id": "media-1", "permalink": "https://instagram.com/reel/media-1"}
        raise AssertionError((method, url, params))


class URLResponse:
    def __init__(self, body, content_type="application/json", status=200):
        self.body = body
        self.status = status
        self.headers = {"Content-Type": content_type}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size=-1):
        return self.body[:size]


class ScheduledReelTests(unittest.TestCase):
    def make_plan(self, media_path, **job_changes):
        digest = hashlib.sha256(Path(media_path).read_bytes()).hexdigest()
        job = {
            "id": "mithai-reel",
            "scheduled_at": "2026-09-11T12:30:00+05:00",
            "video_url": "https://cdn.example/mithai.mp4",
            "video_path": str(media_path),
            "sha256": digest,
            "caption": "Mithai mehmaanon ke liye thi.\nWhatsApp: https://wa.me/923308652035",
            "native_audio": {"id": "1759672808494145", "audio_volume": 80, "video_volume": 20},
            **job_changes,
        }
        return {"authorized": True, "instagram_username": "safaikaro.pk", "jobs": [job]}

    def execution_env(self):
        return {"GITHUB_EVENT_NAME": "schedule", "GITHUB_RUN_ATTEMPT": "1", "GITHUB_WORKFLOW_ID": "77", "GITHUB_REPOSITORY": "org/repo", "GITHUB_RUN_ID": "99", "GITHUB_TOKEN": "token", "GITHUB_API_URL": "https://api.github.com", "SOCIAL_INSTAGRAM_USER_ID": "ig-1", "SOCIAL_META_API_VERSION": "v26", "SOCIAL_META_PAGE_TOKEN": "secret"}

    def test_validate_checks_account_video_and_sha(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reel.mp4"
            path.write_bytes(b"video")
            plan = self.make_plan(path)
            http = FakeHTTP(plan["jobs"][0]["video_url"])
            result = validate_plan(plan, {"ig_id": "ig-1", "version": "v26", "token": "secret"}, http, NOW)
            self.assertEqual(result[0]["id"], "mithai-reel")
            self.assertTrue(any(call[0] == "GET" and call[1] == plan["jobs"][0]["video_url"] for call in http.calls))
            self.assertTrue(any(call[0] == "GET" and call[1].endswith("/ig-1") for call in http.calls))

    def test_validate_rejects_wrong_format_and_invalid_sha(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reel.mp4"
            path.write_bytes(b"video")
            for changes in ({"format": "static"}, {"sha256": "bad"}, {"video_url": "http://cdn.example/reel.mp4"}):
                with self.subTest(changes=changes):
                    with self.assertRaises(RunnerError):
                        validate_plan(self.make_plan(path, **changes), {"ig_id": "ig-1", "version": "v26", "token": "secret"}, FakeHTTP("https://cdn.example/mithai.mp4"), NOW)

    def test_real_transport_routes_graph_github_and_media_without_leaking_tokens(self):
        responses = [URLResponse(b"{}"), URLResponse(b"{}"), URLResponse(b"video", "video/mp4")]
        captured = []

        def open_url(request, timeout):
            captured.append(request)
            return responses.pop(0)

        with patch("scheduled_instagram_reels.urlopen", side_effect=open_url):
            http = _real_http("graph-secret", "v26", "github-secret")
            http("GET", "/ig-1", {"fields": "id,username"})
            http("GET", "https://api.github.com/repos/org/repo/actions/runs")
            media = http("GET", "https://cdn.example/reel.mp4")
        self.assertTrue(captured[0].full_url.startswith("https://graph.facebook.com/v26/ig-1"))
        self.assertEqual(captured[0].get_header("Authorization"), "Bearer graph-secret")
        self.assertEqual(captured[1].full_url, "https://api.github.com/repos/org/repo/actions/runs")
        self.assertEqual(captured[1].get_header("Authorization"), "Bearer github-secret")
        self.assertIsNone(captured[2].get_header("Authorization"))
        self.assertEqual(media["sha256"], hashlib.sha256(b"video").hexdigest())

    def test_validate_requires_native_audio_for_scheduled_reels(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reel.mp4"
            path.write_bytes(b"video")
            plan = self.make_plan(path)
            plan["jobs"][0].pop("native_audio")
            with self.assertRaisesRegex(RunnerError, "native_audio"):
                validate_plan(plan, {"ig_id": "ig-1", "version": "v26", "token": "secret"}, FakeHTTP("https://cdn.example/mithai.mp4"), NOW)

    def test_execute_requires_schedule_first_attempt_authorization_and_today(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reel.mp4"
            path.write_bytes(b"video")
            plan = self.make_plan(path)
            env = self.execution_env()
            env["SAFAIKARO_WORKFLOW_FILE"] = "safaikaro-daily-reels.yml"
            env["GITHUB_EVENT_NAME"] = "workflow_dispatch"
            with self.assertRaisesRegex(RunnerError, "schedule"):
                execute(plan, env, FakeHTTP(plan["jobs"][0]["video_url"]), NOW, Path(directory) / "receipt.json")
            env.update(GITHUB_EVENT_NAME="schedule", GITHUB_RUN_ATTEMPT="2")
            with self.assertRaisesRegex(RunnerError, "attempt"):
                execute(plan, env, FakeHTTP(plan["jobs"][0]["video_url"]), NOW, Path(directory) / "receipt.json")

    def test_execute_blocks_duplicate_caption_and_prior_workflow_run(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reel.mp4"
            path.write_bytes(b"video")
            plan = self.make_plan(path)
            env = self.execution_env()
            env["SAFAIKARO_WORKFLOW_FILE"] = "safaikaro-daily-reels.yml"
            duplicate = FakeHTTP(plan["jobs"][0]["video_url"], media=[{"caption": plan["jobs"][0]["caption"]}])
            with self.assertRaisesRegex(RunnerError, "duplicate"):
                execute(plan, env, duplicate, NOW, Path(directory) / "receipt.json")
            prior = FakeHTTP(plan["jobs"][0]["video_url"], prior_runs=[{"id": 88, "run_started_at": "2026-09-11T07:00:00Z"}])
            with self.assertRaisesRegex(RunnerError, "prior"):
                execute(plan, env, prior, NOW, Path(directory) / "receipt.json")

    def test_execute_hashes_media_serializes_native_audio_and_checkpoints_before_posts(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reel.mp4"
            path.write_bytes(b"video")
            plan = self.make_plan(path)
            env = self.execution_env()
            env["SAFAIKARO_WORKFLOW_FILE"] = "safaikaro-daily-reels.yml"
            http = FakeHTTP(plan["jobs"][0]["video_url"], statuses=["FINISHED"])
            receipt = Path(directory) / "receipt.json"
            result = execute(plan, env, http, NOW, receipt)
            self.assertEqual(result["id"], "media-1")
            self.assertEqual(result["phase"], "published")
            posts = [call for call in http.calls if call[0] == "POST"]
            self.assertEqual(posts[0][2]["audio_configuration"], {"audio_id": "1759672808494145", "audio_volume": 80, "video_volume": 20})
            saved = json.loads(receipt.read_text())
            self.assertEqual(saved["phase"], "published")
            self.assertEqual(saved["history"][0]["phase"], "create")
            self.assertEqual(saved["history"][1]["phase"], "publish")
            self.assertEqual(saved["native_audio_attribution"], "unverified")
            prior_calls = [call for call in http.calls if "/actions/workflows/" in call[1]]
            self.assertEqual(prior_calls[0][2], {})

    def test_execute_rejects_local_hash_mismatch_without_post(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reel.mp4"
            path.write_bytes(b"changed")
            plan = self.make_plan(path, sha256="0" * 64)
            env = self.execution_env()
            env["SAFAIKARO_WORKFLOW_FILE"] = "safaikaro-daily-reels.yml"
            http = FakeHTTP(plan["jobs"][0]["video_url"])
            with self.assertRaisesRegex(RunnerError, "hash"):
                execute(plan, env, http, NOW, Path(directory) / "receipt.json")
            self.assertFalse(any(call[0] == "POST" for call in http.calls))


    def test_time_and_authorization_blocks_do_not_post(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reel.mp4"
            path.write_bytes(b"video")
            for stamp, authorized in [("2026-09-11T07:19:00Z", True), ("2026-09-11T09:31:00Z", True), ("2027-09-11T07:30:00Z", True), ("2026-09-11T07:30:00Z", False)]:
                with self.subTest(stamp=stamp, authorized=authorized):
                    plan = self.make_plan(path)
                    plan["authorized"] = authorized
                    http = FakeHTTP(plan["jobs"][0]["video_url"])
                    with self.assertRaises(RunnerError):
                        execute(plan, self.execution_env(), http, datetime.fromisoformat(stamp.replace("Z", "+00:00")), Path(directory) / "receipt.json")
                    self.assertFalse(any(c[0] == "POST" for c in http.calls))

    def test_early_preparation_waits_until_publish_time(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reel.mp4"
            path.write_bytes(b"video")
            plan = self.make_plan(path)
            http = FakeHTTP(plan["jobs"][0]["video_url"])
            current = [datetime.fromisoformat("2026-09-11T07:20:00+00:00")]
            from datetime import timedelta
            def sleep(seconds):
                current[0] += timedelta(seconds=seconds)
            def request(method, url, params=None):
                if method == "POST" and url.endswith("/media_publish"):
                    self.assertGreaterEqual(current[0], datetime.fromisoformat("2026-09-11T07:30:00+00:00"))
                return http(method, url, params)
            execute(plan, self.execution_env(), request, current[0], Path(directory) / "receipt.json", sleep=sleep, now_fn=lambda: current[0])
            self.assertEqual(current[0].hour, 7)
            self.assertEqual(current[0].minute, 30)

    def test_ambiguous_write_is_checkpointed_and_not_retried(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reel.mp4"
            path.write_bytes(b"video")
            for failing_edge, phase in [("/media", "create"), ("/media_publish", "publish")]:
                with self.subTest(edge=failing_edge):
                    plan = self.make_plan(path)
                    http = FakeHTTP(plan["jobs"][0]["video_url"])
                    receipt = Path(directory) / "receipt.json"
                    writes = []
                    def request(method, url, params=None):
                        if method == "POST":
                            writes.append(url)
                            self.assertEqual(json.loads(receipt.read_text())["phase"], "create" if url.endswith("/media") else "publish")
                            if url.endswith(failing_edge):
                                raise TimeoutError("uncertain")
                        return http(method, url, params)
                    with self.assertRaises(RunnerError):
                        execute(plan, self.execution_env(), request, NOW, receipt)
                    self.assertEqual(sum(url.endswith(failing_edge) for url in writes), 1)
                    self.assertEqual(json.loads(receipt.read_text())["phase"], phase)


if __name__ == "__main__":
    unittest.main()
