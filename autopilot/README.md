# Athar Academy autopilot (أثر أكاديمي — النشر الذكي)

Publishes photo posts to the Facebook Page **أثر اكاديمي - Athar Academy** (page id `1379414478591224`)
two times a day, choosing the hours and the topics from the page's own performance data.
Runs as two scheduled tasks. Everything a run needs is in this folder.

| file | role |
|---|---|
| `config.json` | page id, Baghdad offset, candidate slots, posts per day |
| `queue/<id>/post.json` + `post.jpg` | posts waiting to go out (theme, caption, poster) |
| `published/<id>/` | posts already published (moved here by `decide.py record`) |
| `log.csv` | what the autopilot published: queue id, theme, Facebook post id, time, slot |
| `decide.py` | the brain: `plan`, `record`, `report` (no network; data comes in as a JSON file) |
| `poster.html` + `render_posts.py` | poster template (1080x1350) and renderer |

## How it decides
- **Score of a post** = impressions + 3×clicks + 5×(reactions+comments) + 2×video views, counted once the post is 20h old. Profile/cover photo changes (no text) are ignored.
- **Time slots** (Baghdad): 10:00, 14:00, 17:00, 20:00, 22:00. Every page post (also manual reels) is scored against its nearest slot. While some slots are untried: one post goes to the best known slot and the other tries an untried slot. After that: UCB (average log score + exploration bonus) picks the top 2 slots each day.
- **Topics** (theme of each queued post): same UCB idea over the themes, never the same theme twice in a row.
- **Safety**: max 2 autopilot posts a day, never twice in one slot, never within 2h of any other page post.

## Run A — publisher (fires at 10:07, 14:07, 17:07, 20:07, 22:07 Baghdad)
1. Attach the repo with `add_repo` (owner `zraij`, repo `Athar-media-`, access `push`) and clone it to `/home/claude/athar-media-` (`git clone --depth 1 https://github.com/zraij/Athar-media- /home/claude/athar-media-`).
2. Windsor (`Windsor_ai_for_Social_Media`): `get_data` connector `facebook_organic`, accounts `["1379414478591224"]`, date_preset `last_30dT`, fields
   `post_id, post_created_time, post_message_oneline, post_impressions, post_engagements, post_reactions_total, post_comments_total, post_clicks, post_video_views`.
   Save the returned JSON exactly as returned to `/tmp/posts.json` (Write tool). If the call fails (trial ended, login expired, no access), stop and report it in Arabic as the run's result: say Windsor needs attention and nothing was published.
3. `python3 autopilot/decide.py plan --posts /tmp/posts.json` (from the repo root).
4. If `publish_now` is false: stop. Publish nothing and keep the result to one line. Exception: in the 22:07 run, if `queue_low` is true, say in Arabic that the queue is running low.
5. If `publish_now` is true:
   - `curl -sI <next_item.media_url>` must return 200. If not, stop and report.
   - Windsor `execute_action`: connector `facebook_organic`, action `create_photo_post`, account `1379414478591224`, params `{"image_url": next_item.media_url, "caption": next_item.caption}`. Use the caption exactly; do not edit it.
   - `python3 autopilot/decide.py record --id <next_item.id> --post-id <returned Post id> --slot <current_slot>`
   - `git add -A && git commit -m "autopilot: publish <id>" && git -c push.negotiate=true push origin main` (author name "Athar Autopilot", email noreply@athar.local).
   - Result in Arabic, 2 lines: what went out (title + theme), at which slot, and queue_left.
6. Publish at most one post per run. Never publish anything that is not in `queue/`. Never delete or edit page posts.

## Run C — Instagram reels (same 5 slots, right after Run A in the same session)
1. Windsor `get_connectors`: find the `instagram` account id. If there is none, skip Run C (one line: Instagram is not connected in Windsor).
2. Windsor `get_data` on `instagram` (accounts `["<instagram id>"]`, date_preset `last_30dT`) with fields
   `media_id, timestamp, media_caption, media_type, media_reach, media_views, media_like_count, media_comments_count, media_shares, media_saved`. Save the response to `/tmp/ig.json` (an empty `data` list is fine for a new account).
   Weekly run only: also read `followers_count` and the audience fields `audience_gender_age_name, audience_gender_age_size, city, audience_city_size` for the report (they stay empty until the account has enough followers). `decide.py` understands both Facebook and Instagram field names.
3. `python3 autopilot/decide.py --channel ig plan --posts /tmp/ig.json` (1 reel a day; slots learned from Instagram data only).
4. If `publish_now`:
   - The video is served by GitHub Pages. Do not curl zraij.github.io (the sandbox proxy blocks it). Instead check the API: `curl -s https://api.github.com/repos/zraij/Athar-media-` must show `"has_pages": true`, and the newest deployment in `https://api.github.com/repos/zraij/Athar-media-/deployments?per_page=1` must have a `success` status (its `statuses_url`). If Pages is off, stop and say in Arabic that Pages must be enabled (Settings → Pages → Branch main).
   - Windsor `execute_action`: connector `instagram`, action `create_video_post`, account <instagram id>, params `{"video_url": media_url, "caption": caption, "cover_url": cover_url, "share_to_feed": true}`.
   - `python3 autopilot/decide.py --channel ig record --id <id> --post-id <returned media id> --slot <current_slot>`, then commit and push (pull --rebase first if the push is rejected).
   - Result line in Arabic: which reel went out on Instagram.
   - Right after the reel (before `record`), share it as the evening story: Windsor `execute_action` connector `instagram`, action `create_story`, params `{"video_url": media_url}`.
5. At most one reel per run. Only from `vqueue/`.

## Run D — Instagram morning story (10:07 run)
1. `python3 autopilot/decide.py --channel igs plan --posts /tmp/ig.json` (fixed slot 10:00, today's dated item only).
2. If `publish_now`: Windsor `execute_action` connector `instagram`, action `create_story`, params `{"image_url": media_url}` (GitHub Pages, JPEG 1080x1920), then `decide.py --channel igs record --id <id> --post-id <media id> --slot 10:00`, commit, push.

## Run E — Instagram carousel (14:07 run, only on carousel days)
1. `python3 autopilot/decide.py --channel igc plan --posts /tmp/ig.json` (fixed slot 14:00).
2. If `publish_now`: Windsor `execute_action` connector `instagram`, action `create_carousel_post`, params `{"image_urls": next_item.media_urls, "caption": next_item.caption}`, then `decide.py --channel igc record ...`, commit, push.
   On the same day the Facebook queue item is that carousel's cover (`queue/<date>/post.jpg`), published by Run A.

## Content calendar
Every queue (`queue/`, `vqueue/`, `squeue/`, `cqueue/`) holds one folder per date (`YYYY-MM-DD`) with a `date` field: `decide.py` only offers today's item. The plan is the doc «خطة محتوى أثر أكاديمي — شهر كامل». Old undated items wait in `queue_extra/` and `vextra/` (unused). Music: one brand track (`reels_engine/theme_music.py`) for every reel; HD export 1080x1920, 30 fps, CRF 17.

## Run B — weekly analysis + new content (Saturday 11:23 Baghdad)
1. Steps 1–2 of Run A, plus Windsor `get_data` on `facebook_organic` with fields `date, page_follows, page_daily_follows, page_impressions` (last_30dT) for follower growth.
2. `python3 autopilot/decide.py report --posts /tmp/posts.json --days 7` and `plan` (for slot_scores / theme_scores).
3. Check whether Instagram reels also reached the Facebook Page: compare `log_ig.csv` times with Facebook posts that have `post_video_views` > 0 or a caption matching the reel within 30 minutes. Say in the report, in one line, whether reels are appearing on Facebook.
   Write the weekly report **in Arabic (Iraqi, simple)**, short: followers now and gained this week, best post, best time slots, best themes, what changes next week. Send it with SendUserMessage / as the run result.
4. When the dated calendar runs out (fewer than 7 future dates left), extend it a week at a time in the same pattern (see the weekly rhythm in the plan doc): reels in `vqueue/<date>/`, morning stories in `squeue/<date>/` (render_cards.py), carousels twice a week in `cqueue/<date>/`, and one Facebook post per day in `queue/<date>/`. Refill `vqueue/` to at least 7 reels: new folders numbered after the highest id in `vqueue/` and `vpublished/`, each with a `reel.json` (spec below), then `python3 autopilot/reels_engine/make_reel.py --sheet <ids>` to check the key frames (fix overflowing lines by lowering their `s` size or shortening), then `python3 autopilot/reels_engine/make_reel.py <ids>` to render `reel.mp4` + `cover.jpg`. Lean towards the best Instagram themes.
5. Refill the queue to 14 posts: new folders numbered after the highest id in `queue/` and `published/`. Lean towards the two best themes (about 60%), keep at least one `engagement` post (question for teachers, ends with `ask`) and one `teacher_tips` value post. Then `python3 autopilot/render_posts.py --sheet /tmp/sheet.png`, look at the sheet, and fix any text that wraps badly or overflows (shorten it), re-render, commit and push.
   - Install if missing: `pip install playwright pillow numpy --break-system-packages && python3 -m playwright install chromium`.

## Content rules (for new posts)
- Facts you may use (nothing else; never invent prices, results, clients or numbers):
  interactive books for smart boards (Android): السادس العلمي كيمياء/فيزياء/أحياء/رياضيات، الإنكليزي للسادس الإعدادي، «قراءتي الجديدة» كتاب ناطق والعلوم للأول الابتدائي؛
  ملازم مطبوعة باسم المدرسة/المدرّس وشعارها (all stages and subjects, Iraqi curriculum)؛ offers for private (أهلية) schools؛
  lectures and presentations for postgraduate students, academics and teachers, all specialties, delivered as PowerPoint and PDF.
- Phone: 07746451098. Sign-off line: «أثر أكاديمي.. محتوى تعليمي يترك أثر». Iraqi dialect, short sentences, Western digits (0-9) everywhere.
- `post.json` keys: `theme` (interactive_books | talking_book | schools_offer | postgrad | mulzama | engagement | teacher_tips), `illus` (atom | wave | cell | letter | latin | book | slide | question | versus | list), `kicker`, `title` (max 2 short lines, `\n` between them, one `*accent*`), `sub` (one line), `bullets` (max 3 short chips; for `list` up to 5 items + `listTop`), `caption` (emoji allowed, ends with phone + sign-off + 4–7 hashtags), optional `ask` (replaces phone pill with a call to comment), `glyph`, `school`, `subject`, `grade`.
- No emoji inside the poster itself (only in captions). Any made-up number on a poster must say «مثال».

## Reel spec (`vqueue/<id>/reel.json`, rendered by `reels_engine/make_reel.py`, 18 s, 1080x1920)
```json
{"theme":"interactive_books",
 "hook":[{"l":"الطالب|يحفظ|القانون…","s":92,"m":1},{"l":"بس|*ما يفهمه*؟","s":130}],
 "demo":{"lines":["خلّي|القانون","*يتحرك*|قدامه"],"illus":"wave"},
 "benefits":{"lines":[{"l":"الفيزياء|التفاعلية","s":84,"m":1},{"l":"للسادس|*العلمي*","s":120}],"chips":["...","...","..."]},
 "cta":{"lines":[{"l":"اطلب|نسخة|تجريبية","s":84,"m":1},{"l":"*لمدرستك*|هسه","s":124}]},
 "caption":"... ends with phone, sign-off and hashtags"}
```
- `|` separates words (each word animates in), `*word*` is the one gold accent, `s` = font px, `m:1` = muted smaller line. Keep each line ≤ about 900 px wide (3–4 short words at 110–130 px; long lines 74–92 px).
- `illus`: atom | wave | cell | letter (`glyph`) | latin | book (`school`,`subject`,`grade`) | slide | versus | question.
- Timeline is fixed: hook 0–2.8 s, demo 2.8–8.5 s (hero beat at 5.6 s), benefits 8.9–13 s, call to action + phone 13.2–18 s.
- `vqueue/001`–`005` are prebuilt reels (`"prebuilt": true`); never re-render those.
