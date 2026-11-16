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

## Run B — weekly analysis + new content (Saturday 11:23 Baghdad)
1. Steps 1–2 of Run A, plus Windsor `get_data` on `facebook_organic` with fields `date, page_follows, page_daily_follows, page_impressions` (last_30dT) for follower growth.
2. `python3 autopilot/decide.py report --posts /tmp/posts.json --days 7` and `plan` (for slot_scores / theme_scores).
3. Write the weekly report **in Arabic (Iraqi, simple)**, short: followers now and gained this week, best post, best time slots, best themes, what changes next week. Send it with SendUserMessage / as the run result.
4. Refill the queue to 14 posts: new folders numbered after the highest id in `queue/` and `published/`. Lean towards the two best themes (about 60%), keep at least one `engagement` post (question for teachers, ends with `ask`) and one `teacher_tips` value post. Then `python3 autopilot/render_posts.py --sheet /tmp/sheet.png`, look at the sheet, and fix any text that wraps badly or overflows (shorten it), re-render, commit and push.
   - Install if missing: `pip install playwright pillow --break-system-packages && python3 -m playwright install chromium`.

## Content rules (for new posts)
- Facts you may use (nothing else; never invent prices, results, clients or numbers):
  interactive books for smart boards (Android): السادس العلمي كيمياء/فيزياء/أحياء/رياضيات، الإنكليزي للسادس الإعدادي، «قراءتي الجديدة» كتاب ناطق والعلوم للأول الابتدائي؛
  ملازم مطبوعة باسم المدرسة/المدرّس وشعارها (all stages and subjects, Iraqi curriculum)؛ offers for private (أهلية) schools؛
  lectures and presentations for postgraduate students, academics and teachers, all specialties, delivered as PowerPoint and PDF.
- Phone: 07746451098. Sign-off line: «أثر أكاديمي.. محتوى تعليمي يترك أثر». Iraqi dialect, short sentences, Western digits (0-9) everywhere.
- `post.json` keys: `theme` (interactive_books | talking_book | schools_offer | postgrad | mulzama | engagement | teacher_tips), `illus` (atom | wave | cell | letter | latin | book | slide | question | versus | list), `kicker`, `title` (max 2 short lines, `\n` between them, one `*accent*`), `sub` (one line), `bullets` (max 3 short chips; for `list` up to 5 items + `listTop`), `caption` (emoji allowed, ends with phone + sign-off + 4–7 hashtags), optional `ask` (replaces phone pill with a call to comment), `glyph`, `school`, `subject`, `grade`.
- No emoji inside the poster itself (only in captions). Any made-up number on a poster must say «مثال».
