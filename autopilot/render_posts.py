"""Render queue posters.
python3 autopilot/render_posts.py            -> renders every queue/<id>/post.json lacking post.jpg
python3 autopilot/render_posts.py --all      -> re-renders all
python3 autopilot/render_posts.py --sheet out.png  -> also writes a contact sheet of rendered posts
Each queue/<id>/post.json: {theme, illus, kicker, title, sub, bullets[], caption, [glyph|ask|school|subject|grade|listTop]}
"""
import json, sys, pathlib, asyncio, io
from playwright.async_api import async_playwright
from PIL import Image
ROOT = pathlib.Path(__file__).resolve().parent
import os
Q = pathlib.Path(os.environ.get('Q_DIR', ROOT / 'queue'))
async def main():
    allf = '--all' in sys.argv
    items = sorted(p for p in Q.iterdir() if (p / 'post.json').exists())
    todo = [p for p in items if (allf or not (p / 'post.jpg').exists()) and not json.loads((p / 'post.json').read_text(encoding='utf-8')).get('prebuilt')]
    async with async_playwright() as pw:
        b = await pw.chromium.launch()
        for d in todo:
            post = json.loads((d / 'post.json').read_text(encoding='utf-8'))
            pg = await b.new_page(viewport={'width': 1080, 'height': 1350})
            if post.get('style'):  # one of the 7 motion styles, rendered as a still
                await pg.add_init_script('window.REEL=' + json.dumps(post, ensure_ascii=False) + ';')
                await pg.goto((ROOT / 'reels_engine' / 'styles_tpl.html').as_uri() + '?fmt=post')
            else:
                await pg.add_init_script('window.POST=' + json.dumps(post, ensure_ascii=False) + ';')
                await pg.goto((ROOT / 'poster.html').as_uri())
            await pg.wait_for_function('window.ready===true')
            await pg.evaluate('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))')
            bad = [] if post.get('style') else await pg.evaluate('''()=>{const o=[];['title','sub','kick'].forEach(id=>{const e=document.getElementById(id);if(e&&e.scrollWidth>e.clientWidth+2)o.push(id)});const t=document.getElementById('title');if(t&&t.getBoundingClientRect().height>290)o.push('title>2 lines');const s=document.getElementById('sub');if(s&&s.getBoundingClientRect().height>80)o.push('sub wraps');const ch=document.getElementById('chips');if(ch&&ch.getBoundingClientRect().bottom>1186)o.push('chips too tall');const l=document.getElementById('list');if(l&&l.getBoundingClientRect().bottom>1182)o.push('list too tall');return o}''')
            if bad: print('CHECK', d.name, bad)
            png = await pg.screenshot(type='png')
            Image.open(io.BytesIO(png)).convert('RGB').save(d / 'post.jpg', quality=92)
            await pg.close(); print('rendered', d.name)
        await b.close()
    if '--sheet' in sys.argv:
        out = sys.argv[sys.argv.index('--sheet') + 1]
        ims = [Image.open(p / 'post.jpg').resize((270, 338)) for p in items if (p / 'post.jpg').exists()]
        cols = 7; rows = (len(ims) + cols - 1) // cols
        S = Image.new('RGB', (cols * 270, rows * 338), 'white')
        for i, im in enumerate(ims): S.paste(im, ((i % cols) * 270, (i // cols) * 338))
        S.save(out); print('sheet', out)
asyncio.run(main())
