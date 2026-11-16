"""Athar autopilot decision engine (no network; the run passes Windsor data in as a JSON file).

python3 autopilot/decide.py [--channel fb|ig] plan   --posts posts.json [--now 2026-11-16T17:05:00Z]
python3 autopilot/decide.py record --id 003 --post-id <fb post id> --slot 20:00 [--now ...]
python3 autopilot/decide.py report --posts posts.json [--days 7]

posts.json = the "data" list (or the whole response) from Windsor get_data on facebook_organic with fields
post_id, post_created_time, post_impressions, post_engagements, post_reactions_total,
post_comments_total, post_clicks, post_video_views  (date_preset last_30dT).
"""
import argparse, csv, json, math, hashlib, pathlib, shutil, sys
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parent
CFG = json.loads((ROOT / 'config.json').read_text(encoding='utf-8'))
TZ = timezone(timedelta(hours=CFG['utc_offset_hours']))
CH = {}
LOG = QUEUE = DONE = None


def use_channel(name):
    global CH, LOG, QUEUE, DONE
    CH = CFG['channels'][name]; LOG = ROOT / CH['log']; QUEUE = ROOT / CH['queue']; DONE = ROOT / CH['done']

LOG_FIELDS = ['queue_id', 'theme', 'post_id', 'published_at_utc', 'slot']


def parse_time(s):
    s = s.strip().replace('Z', '+00:00')
    if len(s) >= 5 and (s[-5] in '+-') and s[-3] != ':':  # +0000 -> +00:00
        s = s[:-2] + ':' + s[-2:]
    d = datetime.fromisoformat(s)
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def slot_minutes(slot):
    h, m = slot.split(':'); return int(h) * 60 + int(m)


def nearest_slot(dt_local):
    mins = dt_local.hour * 60 + dt_local.minute
    best = min(CFG['slots'], key=lambda s: abs(slot_minutes(s) - mins))
    return best, abs(slot_minutes(best) - mins)


def load_posts(path):
    if not path: return []
    raw = json.loads(pathlib.Path(path).read_text(encoding='utf-8'))
    rows = raw.get('data', raw) if isinstance(raw, dict) else raw
    out = []
    def pick(r, keys):
        for k in keys:
            if r.get(k) not in (None, ''): return r[k]
        return None
    for r in rows:
        pid = pick(r, ['post_id', 'media_id', 'id']); ct = pick(r, ['post_created_time', 'timestamp', 'media_timestamp', 'created_time', 'media_created_time'])
        if not pid or not ct: continue
        g = lambda keys: float(pick(r, keys) or 0)
        imp = g(['post_impressions', 'media_reach', 'reach', 'media_impressions', 'impressions', 'media_views', 'views'])
        clk = g(['post_clicks']); rea = g(['post_reactions_total', 'media_like_count', 'like_count', 'likes'])
        com = g(['post_comments_total', 'media_comments_count', 'comments_count', 'comments'])
        vv = g(['post_video_views', 'media_plays', 'plays', 'video_views', 'media_video_views'])
        sav = g(['media_shares']) + g(['media_saved'])
        score = imp + 3 * clk + 5 * (rea + com + sav) + 2 * vv
        out.append({'post_id': str(pid), 'created': parse_time(str(ct)), 'score': score, 'impressions': imp, 'clicks': clk,
                    'reactions': rea, 'comments': com, 'text': str(pick(r, ['post_message_oneline', 'media_caption', 'caption']) or '')[:60]})
    # one row per post (Windsor may return a post once per date)
    best = {}
    for p in out:
        if p['post_id'] not in best or p['score'] > best[p['post_id']]['score']: best[p['post_id']] = p
    return list(best.values())


def load_log():
    if not LOG.exists(): return []
    with LOG.open(encoding='utf-8') as f: return list(csv.DictReader(f))


def ucb(groups, keys, now, c):
    """groups: key -> list of log-scores. Returns key -> (ucb, mean, n)."""
    allv = [v for k in groups for v in groups[k]]
    gmean = sum(allv) / len(allv) if allv else 0.0
    N = len(allv); res = {}
    for k in keys:
        v = groups.get(k, []); n = len(v)
        mean = (sum(v) + gmean) / (n + 1)  # shrink toward global mean
        bonus = float('inf') if n == 0 else c * math.sqrt(math.log(N + 1) / n)
        res[k] = (mean + bonus, mean, n)
    return res


def tiebreak(key, day):
    return int(hashlib.md5(f'{key}|{day}'.encode()).hexdigest()[:8], 16)


def plan(args):
    now = parse_time(args.now) if args.now else datetime.now(timezone.utc)
    local = now.astimezone(TZ); today = local.date().isoformat()
    posts = load_posts(args.posts); log = load_log()
    min_age = timedelta(hours=CFG['min_post_age_hours_for_scoring'])
    scored = [p for p in posts if now - p['created'] >= min_age]
    # --- time slots (all page posts count, whoever published them)
    by_slot = {}
    for p in scored:
        if not p['text']: continue  # profile/cover photo changes etc. are not real posts
        s, _ = nearest_slot(p['created'].astimezone(TZ)); by_slot.setdefault(s, []).append(math.log1p(p['score']))
    su = ucb(by_slot, CFG['slots'], now, CFG['exploration_c'])
    tried = [s for s in CFG['slots'] if su[s][2] > 0]; untried = [s for s in CFG['slots'] if su[s][2] == 0]
    if tried and untried:  # cold start: exploit the best known slot, explore the rest one by one
        best = max(tried, key=lambda s: su[s][1])
        rest = sorted(untried, key=lambda s: tiebreak(s, today)) + sorted([s for s in tried if s != best], key=lambda s: -su[s][0])
        ranked = [best] + rest
    else:
        ranked = sorted(CFG['slots'], key=lambda s: (-su[s][0], -su[s][1], tiebreak(s, today)))
    today_slots = sorted(ranked[:CH['posts_per_day']], key=slot_minutes)
    if CH.get('fixed_slots'): today_slots = CH['fixed_slots']
    # --- themes (only autopilot posts carry a theme)
    pid2score = {p['post_id']: p for p in scored}
    by_theme = {}
    for r in log:
        p = pid2score.get(r['post_id'])
        if p: by_theme.setdefault(r['theme'], []).append(math.log1p(p['score']))
    items = []
    for d in sorted(QUEUE.iterdir()) if QUEUE.exists() else []:
        if (d / CH['meta']).exists() and (d / CH['media']).exists():
            meta = json.loads((d / CH['meta']).read_text(encoding='utf-8')); items.append((d.name, meta['theme'], meta.get('date')))
    themes = sorted({t for _, t, _ in items})
    tu = ucb(by_theme, themes, now, CFG['exploration_c'])
    last_theme = log[-1]['theme'] if log else None
    cand = [t for t in themes if t != last_theme] or themes
    theme_rank = sorted(cand, key=lambda t: (-tu[t][0], -tu[t][1], tiebreak(t, today)))
    nxt = None; dated = [i for i in items if i[2]]
    if dated:  # content calendar: only today's item, if there is one
        todays = [i for i in dated if i[2] == today]
        if todays: nxt = {'id': todays[0][0], 'theme': todays[0][1]}
        else:
            undated = [i for i in items if not i[2]]
            if undated: nid = min(i[0] for i in undated); nxt = {'id': nid, 'theme': [i[1] for i in undated if i[0] == nid][0]}
    elif theme_rank:
        t = theme_rank[0]; nid = min(i for i, th, _ in items if th == t); nxt = {'id': nid, 'theme': t}
    if nxt:
        nid = nxt['id']; meta = json.loads((QUEUE / nid / CH['meta']).read_text(encoding='utf-8'))
        nxt['media_url'] = f"{CH['url_base']}/{nid}/{CH['media']}"
        if CH['media'].endswith('.mp4'): nxt['cover_url'] = f"{CH['url_base']}/{nid}/cover.jpg"
        nxt['caption'] = meta.get('caption', '')
        if 'slides' in meta: nxt['media_urls'] = [f"{CH['url_base']}/{nid}/s{k}.jpg" for k in range(1, len(meta['slides']) + 1)]
        if meta.get('date'): nxt['date'] = meta['date']
    # --- should we publish now?
    cur, dist = nearest_slot(local)
    in_window = dist <= CFG['slot_window_minutes']
    ours_today = [r for r in log if parse_time(r['published_at_utc']).astimezone(TZ).date().isoformat() == today]
    recent_any = [p for p in posts if timedelta(0) <= now - p['created'] < timedelta(minutes=CFG['min_gap_from_any_post_minutes'])]
    if CH.get('fixed_slots'): recent_any = []  # stories and carousels keep their fixed times
    reasons = []
    if not in_window: reasons.append(f'not near any slot (nearest {cur}, {dist} min away)')
    if cur not in today_slots: reasons.append(f'{cur} is not one of today\'s slots {today_slots}')
    if any(r['slot'] == cur for r in ours_today): reasons.append(f'already published at {cur} today')
    if len(ours_today) >= CH['posts_per_day']: reasons.append('daily quota reached')
    if recent_any: reasons.append('another post went out on the page less than 2h ago')
    if not nxt: reasons.append('queue is empty')
    out = {
        'now_local': local.strftime('%Y-%m-%d %H:%M'), 'current_slot': cur, 'today_slots': today_slots,
        'publish_now': not reasons, 'reasons_not_to_publish': reasons, 'next_item': nxt,
        'queue_left': len(items), 'queue_low': len(items) < CFG['queue_low_threshold'],
        'slot_scores': {s: {'ucb': None if su[s][0] == float('inf') else round(su[s][0], 2), 'mean_log_score': round(su[s][1], 2), 'posts': su[s][2]} for s in CFG['slots']},
        'theme_scores': {t: {'ucb': None if tu[t][0] == float('inf') else round(tu[t][0], 2), 'mean_log_score': round(tu[t][1], 2), 'posts': tu[t][2]} for t in themes},
        'scored_posts': len(scored),
    }
    print(json.dumps(out, ensure_ascii=False, indent=1))


def record(args):
    now = parse_time(args.now) if args.now else datetime.now(timezone.utc)
    src = QUEUE / args.id
    meta = json.loads((src / CH['meta']).read_text(encoding='utf-8'))
    new = not LOG.exists()
    with LOG.open('a', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, LOG_FIELDS)
        if new: w.writeheader()
        w.writerow({'queue_id': args.id, 'theme': meta['theme'], 'post_id': args.post_id,
                    'published_at_utc': now.strftime('%Y-%m-%dT%H:%M:%SZ'), 'slot': args.slot})
    DONE.mkdir(exist_ok=True); shutil.move(str(src), str(DONE / args.id))
    print(f'recorded {args.id} ({meta["theme"]}) as {args.post_id}; moved to {CH["done"]}/{args.id}')


def report(args):
    now = datetime.now(timezone.utc); posts = load_posts(args.posts); log = load_log()
    since = now - timedelta(days=args.days)
    theme_of = {r['post_id']: r['theme'] for r in log}
    rec = sorted([p for p in posts if p['created'] >= since], key=lambda p: -p['score'])
    lines = [f'Posts in last {args.days} days: {len(rec)}']
    for p in rec:
        s, _ = nearest_slot(p['created'].astimezone(TZ))
        lines.append(f"- {p['created'].astimezone(TZ):%a %d/%m %H:%M} (slot {s}) theme={theme_of.get(p['post_id'], 'manual')} "
                     f"impr={int(p['impressions'])} clicks={int(p['clicks'])} react={int(p['reactions'])} comm={int(p['comments'])} | {p['text']}")
    print('\n'.join(lines))


ap = argparse.ArgumentParser(); ap.add_argument('--channel', choices=['fb', 'ig', 'igs', 'igc'], default='fb'); sp = ap.add_subparsers(dest='cmd', required=True)
a = sp.add_parser('plan'); a.add_argument('--posts'); a.add_argument('--now')
b = sp.add_parser('record'); b.add_argument('--id', required=True); b.add_argument('--post-id', required=True); b.add_argument('--slot', required=True); b.add_argument('--now')
c = sp.add_parser('report'); c.add_argument('--posts'); c.add_argument('--days', type=int, default=7)
args = ap.parse_args(); use_channel(args.channel); {'plan': plan, 'record': record, 'report': report}[args.cmd](args)
