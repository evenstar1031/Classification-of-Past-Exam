#!/usr/bin/env bash
# 클라우드 세션을 새로 열 때마다 한 번 실행: 파이썬 패키지, wkhtmltopdf, 폰트 설치.
# 사용법 (저장소 맨 위 폴더에서):  bash tools/setup.sh
set -e
cd "$(dirname "$0")/.."

echo "== Python packages"
# 버전 고정: 같은 내용이면 PDF가 바이트까지 똑같이 나오도록 (GitHub Actions
# .github/workflows/build-pdfs.yml 과 같은 버전이어야 함 — 바꾸면 둘 다 바꿀 것)
PKGS="pymupdf==1.28.2 pypdf==6.19.0 reportlab==5.0.1 fonttools==4.66.1 numpy==2.4.6 pillow==12.3.0 cffi==2.1.1"
pip install -q --break-system-packages $PKGS 2>/dev/null || pip install -q $PKGS

echo "== wkhtmltopdf"
if ! command -v wkhtmltopdf >/dev/null; then
  (sudo -n apt-get update -qq && sudo -n apt-get install -y -qq wkhtmltopdf) \
  || (apt-get update -qq && apt-get install -y -qq wkhtmltopdf) \
  || echo "!! wkhtmltopdf 설치 실패 — PDF 문제지(gichul-strip) 빌드가 안 됩니다. 사용자에게 알릴 것."
fi
command -v wkhtmltopdf >/dev/null && wkhtmltopdf --version

echo "== Fonts"
if [ -n "$(find fonts -maxdepth 1 -iname '*.ttf' -o -maxdepth 1 -iname '*.otf')" ]; then
  python3 .claude/skills/gichul-strip/scripts/setup_fonts.py fonts
else
  echo "!! fonts/ 폴더에 폰트 파일이 없습니다 (보통체+굵은체 2개, 예: AppleSDGothicNeo-Medium/SemiBold.ttf). 사용자에게 올려 달라고 할 것."
fi
command -v node >/dev/null || echo "!! node 없음 — 과목정보 새로 만들기(make_subject_info.py)만 안 됨"

echo "== 공개 여부"
python3 tools/check_private.py || true
