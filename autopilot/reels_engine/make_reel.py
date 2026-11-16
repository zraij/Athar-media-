"""Render a reel from autopilot/vqueue/<id>/reel.json -> reel.mp4 (1080x1920, 18s, with generated music + sfx) and cover.jpg.
python3 autopilot/reels_engine/make_reel.py <id> [<id> ...]      (or --sheet <id> to only write sheet.png of key moments)
Needs: playwright (+chromium), ffmpeg, numpy, pillow.
"""
import sys, json, pathlib, subprocess, asyncio, tempfile, os
from multiprocessing import Process
from playwright.async_api import async_playwright
HERE = pathlib.Path(__file__).resolve().parent
VQ = pathlib.Path(os.environ.get('VQ_DIR', HERE.parent / 'vqueue'))
TPL = (HERE / 'film_tpl.html').as_uri()
STPL = (HERE / 'styles_tpl.html').as_uri()

def tpl_for(reel): return STPL if reel.get('style') else TPL

def dur_for(reel): return 22.0 if reel.get('quiz') else DUR

def cues_for(reel):
    if not reel.get('style'): return HERO, CUES
    if reel.get('quiz'):
        n = len(reel['items']); hero = 2.8 + 10.9
        return hero, {"whoosh": [2.75, 16.9], "pop": [3.4 + i * .35 for i in range(n)] + [3.7 + k for k in range(10)] + [18.3], "impact": [hero]}
    if reel['style'] == 'split':
        k = len(reel['split']['rows']); hero = 2.8 + 0.9 + (k - 1) * .55 + 1.0
        pops = [2.8 + 0.9 + i * .55 for i in range(k)]
    else:
        n = min(5, len(reel['items'])); st = 1.15 if n > 4 else 1.35
        pops = [2.8 + 0.7 + i * st for i in range(n)]; hero = pops[-1] + 0.2
    return hero, {"whoosh": [2.75, 12.9], "pop": pops + [14.3], "impact": [hero]}
FPS, DUR = 30, 18.0
# HD for Instagram/Facebook: 1080x1920, 30 fps CFR, high profile, generous bitrate so the platforms recompress less
HD = ['-c:v', 'libx264', '-preset', 'slow', '-crf', '17', '-profile:v', 'high', '-level', '4.2', '-pix_fmt', 'yuv420p',
      '-r', '30', '-g', '60', '-maxrate', '15M', '-bufsize', '30M']
THEME = HERE / 'theme.wav'
HERO = 5.6
CUES = {"whoosh": [2.8, 8.45, 13.1], "pop": [3.4, 9.6, 9.82, 10.04, 10.26, 14.3], "impact": [HERO]}

async def shots(reel, times, sink):
    async with async_playwright() as p:
        b = await p.chromium.launch(); pg = await b.new_page(viewport={'width': 1080, 'height': 1920})
        await pg.add_init_script('window.REEL=' + json.dumps(reel, ensure_ascii=False) + ';')
        await pg.goto(tpl_for(reel)); await pg.wait_for_function('window.ready===true')
        for t in times:
            await pg.evaluate(f'seek({t})'); await pg.evaluate('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))')
            sink(t, await pg.screenshot(type='jpeg', quality=92))
        await b.close()

def part(reel, f0, f1, out):
    ff = subprocess.Popen(['ffmpeg', '-v', 'error', '-y', '-f', 'image2pipe', '-framerate', str(FPS), '-c:v', 'mjpeg', '-i', '-',
                           *HD, out], stdin=subprocess.PIPE)
    asyncio.run(shots(reel, [i / FPS for i in range(f0, f1)], lambda t, b: ff.stdin.write(b)))
    ff.stdin.close(); ff.wait()

def make(rid):
    d = VQ / rid; reel = json.loads((d / 'reel.json').read_text(encoding='utf-8'))
    tmp = pathlib.Path(tempfile.mkdtemp()); D = dur_for(reel); n = int(D * FPS); cuts = [0, n // 3, 2 * n // 3, n]
    ps = [Process(target=part, args=(reel, cuts[i], cuts[i + 1], str(tmp / f'p{i}.mp4'))) for i in range(3)]
    [p.start() for p in ps]; [p.join() for p in ps]
    (tmp / 'l.txt').write_text(''.join(f"file '{tmp / f'p{i}.mp4'}'\n" for i in range(3)))
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', str(tmp / 'l.txt'), '-c', 'copy', str(tmp / 'v.mp4')], check=True)
    hero, cues = cues_for(reel)
    theme = HERE / f'theme_{int(D)}.wav'
    if not theme.exists(): subprocess.run([sys.executable, str(HERE / 'theme_music.py'), str(theme), str(D)], check=True)
    subprocess.run([sys.executable, str(HERE / 'audio.py'), str(tmp / 'a.wav'), str(D), str(hero), '2.8', json.dumps(cues)], check=True, env={**os.environ, 'NO_MUSIC': '1'})
    part_out = d / 'reel.part.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(tmp / 'v.mp4'), '-i', str(theme), '-i', str(tmp / 'a.wav'),
                    '-filter_complex', '[1:a]volume=0.85[m];[2:a]volume=0.45,aformat=channel_layouts=stereo[s];[m][s]amix=inputs=2:normalize=0,loudnorm=I=-14:TP=-1.5,aresample=48000[a]',
                    '-map', '0:v', '-map', '[a]', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-shortest', '-movflags', '+faststart', str(part_out)], check=True)
    part_out.rename(d / 'reel.mp4')
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', '6.2', '-i', str(d / 'reel.mp4'), '-frames:v', '1', '-q:v', '3', str(d / 'cover.jpg')], check=True)
    print('made', rid, (d / 'reel.mp4').stat().st_size // 1024, 'KB')

def sheet(rid):
    from PIL import Image; import io
    d = VQ / rid; reel = json.loads((d / 'reel.json').read_text(encoding='utf-8')); ims = []
    asyncio.run(shots(reel, [0.0, 2.0, 4.6, 7.0, 11.5, 17.0], lambda t, b: ims.append(Image.open(io.BytesIO(b)).resize((270, 480)))))
    S = Image.new('RGB', (270 * len(ims), 480)); [S.paste(im, (i * 270, 0)) for i, im in enumerate(ims)]
    S.save(d / 'sheet.png'); print('sheet', d / 'sheet.png')

def check(rid):
    """Print lines wider than the safe area (1000 px)."""
    reel = json.loads((VQ / rid / 'reel.json').read_text(encoding='utf-8')); bad = []
    async def go():
        async with async_playwright() as p:
            b = await p.chromium.launch(); pg = await b.new_page(viewport={'width': 1080, 'height': 1920})
            await pg.add_init_script('window.REEL=' + json.dumps(reel, ensure_ascii=False) + ';')
            await pg.goto(tpl_for(reel)); await pg.wait_for_function('window.ready===true')
            r = await pg.evaluate('''()=>{const o=[];document.querySelectorAll('.line').forEach(L=>{const ws=[...L.querySelectorAll('.w')];if(!ws.length)return;const a=Math.min(...ws.map(w=>w.getBoundingClientRect().left)),z=Math.max(...ws.map(w=>w.getBoundingClientRect().right));if(z-a>1000)o.push([L.textContent,Math.round(z-a)])});document.querySelectorAll('.chip').forEach(c=>{const w=c.getBoundingClientRect().width;if(w>980)o.push([c.textContent,Math.round(w)])});return o}''')
            bad.extend(r); await b.close()
    asyncio.run(go()); print(rid, 'OK' if not bad else bad)

if __name__ == '__main__':
    a = sys.argv[1:]
    if a and a[0] == '--sheet': [sheet(r) for r in a[1:]]
    elif a and a[0] == '--check': [check(r) for r in a[1:]]
    else: [make(r) for r in a]
