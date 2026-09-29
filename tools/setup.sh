#!/usr/bin/env bash
# 클라우드 세션을 새로 열 때마다 한 번 실행: 파이썬 패키지, wkhtmltopdf, 폰트 설치.
# 사용법 (저장소 맨 위 폴더에서):  bash tools/setup.sh
set -e
cd "$(dirname "$0")/.."

echo "== Python packages"
pip install -q --break-system-packages pymupdf pypdf reportlab fonttools numpy pillow 2>/dev/null \
  || pip install -q pymupdf pypdf reportlab fonttools numpy pillow

echo "== wkhtmltopdf"
if ! command -v wkhtmltopdf >/dev/null; then
  (sudo -n apt-get update -qq && sudo -n apt-get install -y -qq wkhtmltopdf) \
  || (apt-get update -qq && apt-get install -y -qq wkhtmltopdf) \
  || echo "!! wkhtmltopdf 설치 실패 — PDF 문제지(gichul-strip) 빌드가 안 됩니다. 사용자에게 알릴 것."
fi
command -v wkhtmltopdf >/dev/null && wkhtmltopdf --version

echo "== Fonts"
if fc-list | grep -q KoPubBatangTT; then
  echo "이미 설치됨"
elif ls fonts/*.otf fonts/*.ttf >/dev/null 2>&1; then
  python3 .claude/skills/gichul-strip/scripts/setup_fonts.py fonts
else
  echo "!! fonts/ 폴더에 KoPubWorld 바탕체 Pro Medium/Bold 파일이 없습니다. 사용자에게 올려 달라고 할 것."
fi
command -v node >/dev/null || echo "!! node 없음 — 과목정보 새로 만들기(make_subject_info.py)만 안 됨"

echo "== 공개 여부"
python3 tools/check_private.py || true
