#!/usr/bin/env python3
"""학습자료 본문 글씨체(KoPubWorld 바탕) 설치.

이 스킬 폴더의 fonts/ 에 있는 보통체+굵은체 두 파일을 wkhtmltopdf가 텍스트로 그릴 수 있게
TrueType 윤곽으로 바꿔 'StudyBatang' 이라는 이름으로 등록한다. (OTF(CFF) 그대로 쓰면 글자가
그림으로 찍혀 PDF에서 검색·복사가 안 된다.) 제목·문항 글씨체(Apple SD 산돌고딕 Neo)는 저장소
fonts/ → GichulTT 로 tools/setup.sh 가 이미 등록한다.

바꾼 결과는 ~/.cache/pilgi-study-fonts 에 남겨, 같은 세션에서 두 번째부터는 바로 끝난다.

usage: python3 .claude/skills/pilgi-study/scripts/setup_fonts.py
"""
import glob, hashlib, os, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..'))
sys.path.insert(0, os.path.join(ROOT, '.claude', 'skills', 'gichul-strip', 'scripts'))
import setup_fonts as SF  # noqa: E402  (otf2ttf, weight_of)

FAMILY = 'StudyBatang'
SRC = os.path.join(HERE, '..', 'fonts')
CACHE = os.path.expanduser('~/.cache/pilgi-study-fonts')


def main():
    SF.need('markdown')         # 1부(설명) Markdown → HTML
    files = [p for p in glob.glob(os.path.join(SRC, '*')) if p.lower().endswith(('.otf', '.ttf'))]
    found = {}
    for p in files:
        role, _, _ = SF.weight_of(os.path.basename(os.path.splitext(p)[0]))
        found.setdefault(role, p)
    if set(found) != {'Regular', 'Bold'}:
        sys.exit(f'!! {SRC} 에 보통체+굵은체 두 파일이 필요합니다. 찾은 것: {files}')
    os.makedirs(SF.FONTDIR, exist_ok=True); os.makedirs(CACHE, exist_ok=True)
    SF.FAMILY = FAMILY          # otf2ttf 가 이 이름으로 등록
    for style, src in found.items():
        h = hashlib.sha1(open(src, 'rb').read()).hexdigest()[:12]
        cached = os.path.join(CACHE, f'{FAMILY}-{style}-{h}.ttf')
        if not os.path.exists(cached):
            print(f'{style:7s} <- {os.path.basename(src)} (TrueType 변환 중…)')
            SF.otf2ttf(src, cached, style)
        shutil.copy(cached, os.path.join(SF.FONTDIR, f'{FAMILY}-{style}.ttf'))
    subprocess.run(['fc-cache', '-f'], check=True, capture_output=True)
    ok = [l for l in subprocess.run(['fc-list'], capture_output=True, text=True).stdout.splitlines() if FAMILY in l]
    print('\n'.join(ok))
    if len(ok) < 2:
        sys.exit('!! StudyBatang 등록 실패')
    gt = [l for l in subprocess.run(['fc-list'], capture_output=True, text=True).stdout.splitlines() if 'GichulTT' in l]
    if len(gt) < 2:
        print('!! GichulTT(제목·문항 글씨체)가 없습니다 — 먼저 bash tools/setup.sh 를 실행하세요.')
    print('[OK] 학습자료 글씨체 준비 완료')


if __name__ == '__main__':
    main()
