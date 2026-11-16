"""Render a reel from autopilot/vqueue/<id>/reel.json -> reel.mp4 (1080x1920, 18s, with generated music + sfx) and cover.jpg.
python3 autopilot/reels_engine/make_reel.py <id> [<id> ...]      (or --sheet <id> to only write sheet.png of key moments)
Needs: playwright (+chromium), ffmpeg, numpy, pillow.
"""
import sys, json, pathlib, subprocess, asyncio, tempfile, os
from multiprocessing import Process
from playwright.async_api import async_playwright
HERE = pathlib.Path(__file__).resolve().parent
VQ = HERE.parent / 'vqueue'
TPL = (HERE / 'film_tpl.html').as_uri()
FPS, DUR = 30, 18.0
HERO = 5.6
CUES = {"whoosh": [2.8, 8.45, 13.1], "pop": [3.4, 9.6, 9.82, 10.04, 10.26, 14.3], "impact": [HERO]}

async def shots(reel, times, sink):
    async with async_playwright() as p:
        b = await p.chromium.launch(); pg = await b.new_page(viewport={'width': 1080, 'height': 1920})
        await pg.add_init_script('window.REEL=' + json.dumps(reel, ensure_ascii=False) + ';')
        await pg.goto(TPL); await pg.wait_for_function('window.ready===true')
        for t in times:
            await pg.evaluate(f'seek({t})'); await pg.evaluate('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))')
            sink(t, await pg.screenshot(type='jpeg', quality=92))
        await b.close()

def part(reel, f0, f1, out):
    ff = subprocess.Popen(['ffmpeg', '-v', 'error', '-y', '-f', 'image2pipe', '-framerate', str(FPS), '-c:v', 'mjpeg', '-i', '-',
                           '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '21', '-pix_fmt', 'yuv420p', out], stdin=subprocess.PIPE)
    asyncio.run(shots(reel, [i / FPS for i in range(f0, f1)], lambda t, b: ff.stdin.write(b)))
    ff.stdin.close(); ff.wait()

def make(rid):
    d = VQ / rid; reel = json.loads((d / 'reel.json').read_text(encoding='utf-8'))
    tmp = pathlib.Path(tempfile.mkdtemp()); n = int(DUR * FPS); cuts = [0, n // 3, 2 * n // 3, n]
    ps = [Process(target=part, args=(reel, cuts[i], cuts[i + 1], str(tmp / f'p{i}.mp4'))) for i in range(3)]
    [p.start() for p in ps]; [p.join() for p in ps]
    (tmp / 'l.txt').write_text(''.join(f"file '{tmp / f'p{i}.mp4'}'\n" for i in range(3)))
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', str(tmp / 'l.txt'), '-c', 'copy', str(tmp / 'v.mp4')], check=True)
    subprocess.run([sys.executable, str(HERE / 'audio.py'), str(tmp / 'a.wav'), str(DUR), str(HERO), '3.0', json.dumps(CUES)], check=True)
    part_out = d / 'reel.part.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(tmp / 'v.mp4'), '-i', str(tmp / 'a.wav'), '-map', '0:v', '-map', '1:a', '-c:v', 'copy',
                    '-c:a', 'aac', '-b:a', '160k', '-af', 'loudnorm=I=-14:TP=-1.5', '-shortest', '-movflags', '+faststart', str(part_out)], check=True)
    part_out.rename(d / 'reel.mp4')
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', '6.2', '-i', str(d / 'reel.mp4'), '-frames:v', '1', '-q:v', '3', str(d / 'cover.jpg')], check=True)
    print('made', rid, (d / 'reel.mp4').stat().st_size // 1024, 'KB')

def sheet(rid):
    from PIL import Image; import io
    d = VQ / rid; reel = json.loads((d / 'reel.json').read_text(encoding='utf-8')); ims = []
    asyncio.run(shots(reel, [0.0, 2.0, 4.6, 6.4, 11.5, 17.0], lambda t, b: ims.append(Image.open(io.BytesIO(b)).resize((270, 480)))))
    S = Image.new('RGB', (270 * len(ims), 480)); [S.paste(im, (i * 270, 0)) for i, im in enumerate(ims)]
    S.save(d / 'sheet.png'); print('sheet', d / 'sheet.png')

if __name__ == '__main__':
    a = sys.argv[1:]
    if a and a[0] == '--sheet': [sheet(r) for r in a[1:]]
    else: [make(r) for r in a]
