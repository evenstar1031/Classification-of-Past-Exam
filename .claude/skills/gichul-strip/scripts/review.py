#!/usr/bin/env python3
"""Visual review helpers.

review.py WORKDIR sheets             -> WORKDIR/sheet_N.png (8 pages per strip)
review.py WORKDIR pages 5 6 10       -> WORKDIR/pages.png (those pages side by side)
review.py WORKDIR find "Venous O₂" "SI=SI₀" ...
                                     -> WORKDIR/crops.png (zoomed snippet around each hit)
"""
import glob, os, sys
from PIL import Image

WORK, mode, args = sys.argv[1], sys.argv[2], sys.argv[3:]
pv = sorted(glob.glob(os.path.join(WORK, 'pv', '*.png')))


def strip(paths, out, sc):
    ims = [Image.open(p) for p in paths]
    w, h = ims[0].size; w2, h2 = int(w * sc), int(h * sc)
    s = Image.new('RGB', ((w2 + 6) * len(ims), h2), 'grey')
    for i, im in enumerate(ims):
        s.paste(im.resize((w2, h2)), (i * (w2 + 6), 0))
    s.save(out); print(out)


if mode == 'sheets':
    for k in range(0, len(pv), 8):
        strip(pv[k:k + 8], os.path.join(WORK, f'sheet_{k // 8 + 1}.png'), 0.36)
elif mode == 'pages':
    strip([pv[int(a) - 1] for a in args], os.path.join(WORK, 'pages.png'), 0.55)
elif mode == 'find':
    import pymupdf
    d = pymupdf.open(os.path.join(WORK, 'raw.pdf'))
    crops = []
    for t in args:
        for i, p in enumerate(d):
            r = p.search_for(t)
            if r:
                r = r[0]
                pix = p.get_pixmap(dpi=125, clip=pymupdf.Rect(20, r.y0 - 30, p.rect.width - 20, r.y1 + 30))
                crops.append(Image.frombytes('RGB', (pix.width, pix.height), pix.samples))
                print(f'{t!r}: page {i + 1}'); break
        else:
            print(f'{t!r}: NOT FOUND')
    if crops:
        H = sum(c.height + 6 for c in crops)
        s = Image.new('RGB', (max(c.width for c in crops), H), 'grey'); y = 0
        for c in crops:
            s.paste(c, (0, y)); y += c.height + 6
        s.save(os.path.join(WORK, 'crops.png')); print(os.path.join(WORK, 'crops.png'))
