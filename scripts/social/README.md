# Approved SafaiKaro Reel schedule

This finite queue publishes two existing, owner-approved Instagram Reels to `safaikaro.pk`: the midnight-kitchen Reel on 13 September 2026 and the revised natural chai/mosquitoes Reel on 14 September 2026, both targeting 12:30 pm Asia/Karachi. It does not generate content or publish Facebook, image, or carousel posts.

The workflow starts at 12:20 pm PKT to validate the account, track and exact hosted video bytes, prepare the Instagram container, and wait until 12:30 before publishing. GitHub Actions can delay or drop scheduled runs; this is a target time, not a guarantee of delivery at the exact minute. The runner refuses jobs beyond their allowed lateness window and prevents blind re-execution after a scheduled attempt. The full year/date in the plan prevents the cron expression from publishing again next year.

Music is attached through Meta's native `audio_configuration`, using the already verified Bird Watching track by Danny Peter Wolf. The hosted masters contain household ambience only. Container acceptance is not proof of final music attribution; the resulting public post must still be checked after it exists.

## Facebook Page cross-post

A job may carry an optional `facebook` block (`video_path`, `sha256`, `caption`). Jobs without one stay Instagram-only. Facebook has no native-music API, so the Facebook master is a separate MP4 with the licensed Bird Watching track mixed under the ambience; its bytes are uploaded from this checkout, so validation hashes the local file instead of a hosted URL.

Facebook runs only after the Instagram readback succeeds: a duplicate-description check against the Page's recent Reels, then start, raw byte upload, finish, and a reconcile `GET /{video_id}`. The finish response shape is not trusted; `publishing_phase.publish_status == "published"` on the reconcile is the only proof of publication.

Any failed or ambiguous Facebook step checkpoints `facebook_uncertain` with the video id and exits non-zero without retrying and without altering the recorded Instagram result. The Page id is the non-secret workflow env `SOCIAL_FACEBOOK_PAGE_ID`; the Page token is the same existing secret.

## Operation

- Scheduled workflow events execute the finite approved plan.
- Manual workflow dispatch performs read-only validation and cannot publish.
- The Meta credential is the encrypted repository secret `SAFAIKARO_SOCIAL_META_PAGE_TOKEN`. Never add a token to this directory or to workflow arguments.
- Runs retain a credential-free delivery checkpoint artifact. After an ambiguous create/publish failure, inspect the checkpoint and Instagram media before any recovery. Do not rerun a failed publication blindly.
- To pause the remaining queue, disable `safaikaro-daily-reels.yml` in GitHub Actions. To withdraw a future job permanently, edit the plan after confirming its current delivery state.

## Source to publication

Private social-app `tools/scheduled_instagram_reels.py` and its tests → this reviewed runner copy and finite JSON plan → `.github/workflows/safaikaro-daily-reels.yml` → hosted `social-media/` masters → Instagram's hosted-URL Reel flow with native music.

The original source media and generation receipts remain in the private SafaiKaro worktree. The website's other workflows and pages are separate from this queue.
