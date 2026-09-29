#!/usr/bin/env python3
"""Install KoPubWorld Batang Pro and register a TrueType copy for wkhtmltopdf.

wkhtmltopdf draws @font-face webfonts and CFF-flavoured OTF fonts as vector
outlines, so the PDF ends up with no text layer (unsearchable, and the final
answer-leak scan can't run).  Converting the same fonts to TrueType outlines
and registering them under a distinct family name fixes that.

usage: setup_fonts.py [UPLOAD_DIR]   (default /mnt/user-data/uploads)
"""
import glob, os, shutil, subprocess, sys

FAMILY = 'KoPubBatangTT'
FONTDIR = os.path.expanduser('~/.fonts')


def need(pkg, mod=None):
    try:
        __import__(mod or pkg)
    except ImportError:
        subprocess.run([sys.executable, '-m', 'pip', 'install', pkg,
                        '--break-system-packages', '-q'], check=True)


def otf2ttf(src, dst, style):
    from fontTools.ttLib import TTFont, newTable
    from fontTools.pens.cu2quPen import Cu2QuPen
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    f = TTFont(src)
    if 'CFF ' in f:
        gs, order = f.getGlyphSet(), f.getGlyphOrder()
        glyf = newTable('glyf'); glyf.glyphOrder = order; glyf.glyphs = {}
        for name in order:
            pen = TTGlyphPen(gs)
            try:
                gs[name].draw(Cu2QuPen(pen, 1.0, reverse_direction=True))
            except Exception:
                pass
            glyf.glyphs[name] = pen.glyph()
        f['glyf'] = glyf; f['loca'] = newTable('loca')
        maxp = newTable('maxp'); maxp.tableVersion = 0x00010000
        for k in ('maxZones', 'maxTwilightPoints', 'maxStorage', 'maxFunctionDefs',
                  'maxInstructionDefs', 'maxStackElements', 'maxSizeOfInstructions',
                  'maxComponentElements'):
            setattr(maxp, k, 0)
        maxp.maxZones = 1
        f['maxp'] = maxp
        f['head'].indexToLocFormat = 0; f['head'].glyphDataFormat = 0
        del f['CFF ']
        if 'VORG' in f:
            del f['VORG']
        f['post'].formatType = 3.0
        f.sfntVersion = '\x00\x01\x00\x00'
    for r in f['name'].names:
        if r.nameID in (1, 16, 21):
            r.string = FAMILY
        elif r.nameID in (2, 17, 22):
            r.string = style
        elif r.nameID == 4:
            r.string = f'{FAMILY} {style}'
        elif r.nameID == 6:
            r.string = f'{FAMILY}-{style}'
    bold = style == 'Bold'
    f['OS/2'].usWeightClass = 700 if bold else 400
    f['OS/2'].fsSelection = (f['OS/2'].fsSelection & ~0b1100001) | (0b100000 if bold else 0b1000000)
    f['head'].macStyle = 1 if bold else 0
    f.save(dst)


def main():
    up = sys.argv[1] if len(sys.argv) > 1 else '/mnt/user-data/uploads'
    need('fonttools', 'fontTools'); need('pymupdf'); need('pypdf'); need('reportlab')
    os.makedirs(FONTDIR, exist_ok=True)
    found = {}
    for p in glob.glob(os.path.join(up, '*')):
        b = os.path.basename(p).lower()
        if 'kopub' in b and 'batang' in b and b.endswith(('.otf', '.ttf')):
            if 'bold' in b:
                found['Bold'] = p
            elif 'medium' in b:
                found['Regular'] = p
    if len(found) < 2:
        sys.exit(f'KoPubWorld Batang Medium/Bold not both found in {up}: {found}')
    for style, src in found.items():
        shutil.copy(src, FONTDIR)                       # original, as requested
        otf2ttf(src, os.path.join(FONTDIR, f'{FAMILY}-{style}.ttf'), style)
    subprocess.run(['fc-cache', '-f'], check=True, capture_output=True)
    out = subprocess.run(['fc-list'], capture_output=True, text=True).stdout
    ok = [l for l in out.splitlines() if FAMILY in l]
    print('\n'.join(ok))
    if len(ok) < 2:
        sys.exit('TT family not registered')
    # glyph coverage report for characters the builder uses
    from fontTools.ttLib import TTFont
    cm = TTFont(os.path.join(FONTDIR, f'{FAMILY}-Regular.ttf')).getBestCmap()
    chars = '①②③④⑤⑥⑦⑧⑨⑩⑪⑫²³⁺⁻₀₁₂₃₄₅öé×−℃'
    missing = [c for c in chars if ord(c) not in cm]
    print('missing glyphs (use <sup>/<sub> for these):', ''.join(missing) or 'none')


if __name__ == '__main__':
    main()
