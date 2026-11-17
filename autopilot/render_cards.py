"""Render stories and carousels.
python3 autopilot/render_cards.py [--all] [--sheet out.png]
squeue/<date>/story.json  {date, kind, ...card fields}            -> story.jpg (1080x1920)
cqueue/<date>/carousel.json {date, theme, caption, slides:[card]} -> s1.jpg ... sN.jpg (1080x1350)
"""
import json, sys, pathlib, asyncio, io
from playwright.async_api import async_playwright
from PIL import Image
ROOT = pathlib.Path(__file__).resolve().parent
async def shot(b, card, fmt, out):
    w, h = (1080, 1920) if fmt == 'story' else (1080, 1350)
    pg = await b.new_page(viewport={'width': w, 'height': h})
    await pg.add_init_script('window.CARD=' + json.dumps({**card, 'fmt': fmt}, ensure_ascii=False) + ';')
    await pg.goto((ROOT / 'cards.html').as_uri()); await pg.wait_for_function('window.ready===true')
    await pg.evaluate('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))')
    Image.open(io.BytesIO(await pg.screenshot(type='png'))).convert('RGB').save(out, quality=92); await pg.close()
async def main():
    allf = '--all' in sys.argv; made = []
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for d in sorted((ROOT / 'squeue').glob('*/story.json')):
            out = d.parent / 'story.jpg'
            if allf or not out.exists(): await shot(b, json.loads(d.read_text(encoding='utf-8')), 'story', out)
            made.append(out)
        for d in sorted((ROOT / 'cqueue').glob('*/carousel.json')):
            c = json.loads(d.read_text(encoding='utf-8'))
            if c.get('prebuilt'): made += [d.parent / f's{i}.jpg' for i in range(1, len(c['slides']) + 1)]; continue
            for i, s in enumerate(c['slides'], 1):
                out = d.parent / f's{i}.jpg'
                if allf or not out.exists(): await shot(b, s, 'post', out)
                made.append(out)
        await b.close()
    if '--sheet' in sys.argv:
        out = sys.argv[sys.argv.index('--sheet') + 1]
        ims = [Image.open(m).resize((216, 384 if 'story' in m.name else 270)) for m in made]
        cols = 10; rows = (len(ims) + cols - 1) // cols
        S = Image.new('RGB', (cols * 216, rows * 384), 'white')
        for i, im in enumerate(ims): S.paste(im, ((i % cols) * 216, (i // cols) * 384))
        S.save(out); print('sheet', out, len(made))
asyncio.run(main())
