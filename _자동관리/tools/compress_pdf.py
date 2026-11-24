#!/usr/bin/env python3
"""PDF 용량 줄이기 — knu1 앱 「PDF 압축」(seohoe1031/pdf-compress)과 같은 Ghostscript 설정.

앱은 브라우저 안의 Ghostscript(WASM)로, 여기서는 설치된 Ghostscript(gs)로 같은 인자를 준다.
  권장(recommended, 기본) = -dPDFSETTINGS=/ebook (이미지 150dpi)   강하게 = /screen(72dpi)   약하게 = /printer(300dpi)
1% 미만으로 줄거나 오히려 커지면 원본을 그대로 둔다(앱과 같음). 글자는 그대로라 검색·복사가 된다.

usage: python3 compress_pdf.py <pdf 또는 폴더> ... [--preset recommended|extreme|low]
"""
import os, shutil, subprocess, sys, tempfile

PRESET = {'extreme': '/screen', 'recommended': '/ebook', 'low': '/printer'}
COMMON = ['-dCompatibilityLevel=1.5', '-dNOPAUSE', '-dBATCH', '-dSAFER', '-dQUIET',
          '-dAutoRotatePages=/None', '-dDetectDuplicateImages=true',
          '-dCompressFonts=true', '-dSubsetFonts=true',
          '-dColorImageDownsampleType=/Bicubic', '-dGrayImageDownsampleType=/Bicubic']


def ensure_gs():
    if shutil.which('gs'):
        return True
    for cmd in (['sudo', '-n', 'apt-get'], ['apt-get']):
        try:
            subprocess.run(cmd + ['install', '-y', '-qq', 'ghostscript'], capture_output=True, timeout=300)
            if not shutil.which('gs'):
                subprocess.run(cmd + ['update', '-qq'], capture_output=True, timeout=300)
                subprocess.run(cmd + ['install', '-y', '-qq', 'ghostscript'], capture_output=True, timeout=300)
        except Exception:
            pass
        if shutil.which('gs'):
            return True
    return False


def compress(path, preset='recommended'):
    """path 를 제자리에서 압축. (전 크기, 후 크기, 상태) — 상태: 'ok' | 'kept' | 'skip:<이유>'"""
    before = os.path.getsize(path)
    if not ensure_gs():
        return before, before, 'skip:Ghostscript(gs)가 없음'
    fd, tmp = tempfile.mkstemp(suffix='.pdf', dir=os.path.dirname(os.path.abspath(path))); os.close(fd)
    try:
        r = subprocess.run(['gs', '-sDEVICE=pdfwrite', f'-dPDFSETTINGS={PRESET[preset]}', *COMMON,
                            f'-sOutputFile={tmp}', path], capture_output=True, text=True, timeout=1800)
        log = (r.stdout or '') + (r.stderr or '')
        ok = r.returncode == 0 and os.path.exists(tmp) and os.path.getsize(tmp) > 100 \
            and open(tmp, 'rb').read(4) == b'%PDF' and 'No pages will be processed' not in log
        if not ok:
            return before, before, 'skip:압축 실패 — 원본 유지'
        try:                                   # 쪽 수가 같은지 한 번 더 확인
            import pymupdf
            if len(pymupdf.open(tmp)) != len(pymupdf.open(path)):
                return before, before, 'skip:쪽 수가 달라짐 — 원본 유지'
        except ImportError:
            pass
        after = os.path.getsize(tmp)
        if after >= before * 0.99:
            return before, before, 'kept'
        os.replace(tmp, path)
        return before, after, 'ok'
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def report(path, res):
    b, a, st = res
    mb = lambda x: f'{x / 1048576:.1f}MB'
    if st == 'ok':
        return f'[OK] 압축 {mb(b)} → {mb(a)} (−{round((1 - a / b) * 100)}%)  {os.path.basename(path)}'
    if st == 'kept':
        return f'[OK] 압축해도 거의 안 줄어 원본 유지 {mb(b)}  {os.path.basename(path)}'
    return f'[CHECK] 압축 건너뜀({st[5:]}) {mb(b)}  {os.path.basename(path)}'


def main():
    args = sys.argv[1:]
    preset = 'recommended'
    if '--preset' in args:
        i = args.index('--preset'); preset = args[i + 1]; del args[i:i + 2]
    files = []
    for p in args:
        if os.path.isdir(p):
            files += sorted(os.path.join(dp, f) for dp, _, fs in os.walk(p) for f in fs if f.lower().endswith('.pdf'))
        else:
            files.append(p)
    tb = ta = 0
    for f in files:
        res = compress(f, preset); tb += res[0]; ta += res[1]
        print(report(f, res), flush=True)
    if len(files) > 1 and tb:
        print(f'합계 {tb / 1048576:.1f}MB → {ta / 1048576:.1f}MB (−{round((1 - ta / tb) * 100)}%)')


if __name__ == '__main__':
    main()
