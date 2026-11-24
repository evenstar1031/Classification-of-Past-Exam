"""올리기/전사본/ 의 강의 녹음 전사본을 시간표로 수업을 찾아 학습자료 폴더에 넣는다.

폴더 이름에서 날짜와 교시를 읽어(`1117_01.1교시`, `2026-11-17_3교시`),
앱 시간표(_자동관리/app/app.html 의 DATA)에서 그 시간의 수업을 찾고,
과목정보에서 수업 번호를 찾아 아래로 옮긴다.

    학습자료/<학기>/<번호. 과목>/<id>_<수업명>/전사본/전사본_<연도>_<교시>교시.srt

    python3 _자동관리/tools/transcript_file.py          # 옮기기
    python3 _자동관리/tools/transcript_file.py --dry    # 어디로 갈지만 보기
"""
import json
import re
import shutil
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import subjects as S  # noqa: E402

INBOX = ROOT / '올리기' / '전사본'
APP = ROOT / '_자동관리' / 'app' / 'app.html'
INFO = ROOT / '_자동관리' / '과목정보'


def norm(t):
    """비교용: 공백·기호 빼고 한글 정규화"""
    t = unicodedata.normalize('NFC', str(t or ''))
    return re.sub(r'[\s\-–—·,()\[\]/]+', '', t)


def timetable():
    """앱 시간표 → {(월,일): (연도, [(시작교시, 끝교시, 수업명, 교수)])}"""
    src = unicodedata.normalize('NFC', APP.read_text(encoding='utf-8'))
    i = src.index('const DATA = [')
    block = src[i:src.index('\n];', i)]
    out = {}
    for line in block.split('\n'):
        m = re.match(r"\{d:'(\d{4})-(\d{2})-(\d{2})'", line)
        if not m:
            continue
        slots = []
        for p in re.finditer(r"\[(\d+),(\d+),'((?:[^'\\]|\\.)*)'(?:,'((?:[^'\\]|\\.)*)')?", line):
            slots.append((int(p.group(1)), int(p.group(2)),
                          p.group(3).replace("\\'", "'"), p.group(4) or ''))
        out[(int(m.group(2)), int(m.group(3)))] = (int(m.group(1)), slots)
    return out


def lectures():
    """{정규화한 수업명: (과목키, 수업 id, 수업명)}"""
    table = {}
    for f in sorted(INFO.glob('*.json')):
        data = json.loads(f.read_text(encoding='utf-8'))
        for lec in data.get('lectures', []):
            name = lec.get('name') or ''
            table.setdefault(norm(name), (f.stem, lec.get('id'), name))
    return table


def parse_folder(name):
    """'1117_01.1교시' → ((11, 17), 1).  못 읽으면 None"""
    n = unicodedata.normalize('NFC', name)
    m = re.search(r'(\d{1,2})\s*(?:교시|차시)', n)
    if not m:
        return None
    period = int(m.group(1))
    d = re.match(r'\D*(?:(20\d{2})[-_.]?)?(\d{1,2})[-_.]?(\d{2})(?!\d)', n)
    if not d:
        return None
    return (int(d.group(2)), int(d.group(3))), period


def find_lecture(tt, lec_table, day, period):
    entry = tt.get(day)
    if not entry:
        return None, None, '시간표에 그 날짜가 없음'
    year, slots = entry
    for a, b, title, _prof in slots:
        if a <= period <= b:
            hit = lec_table.get(norm(title))
            if hit:
                return hit, year, None
            for key, val in lec_table.items():
                if key and (key in norm(title) or norm(title) in key):
                    return val, year, None
            return None, None, f'시간표 수업 "{title}" 을 과목정보에서 못 찾음'
    return None, None, f'{period}교시에 수업이 없음'


def main(dry=False):
    if not INBOX.exists():
        print('올릴 전사본이 없습니다.')
        return 0
    tt = timetable()
    lec_table = lectures()
    moved, left = [], []

    for folder in sorted(p for p in INBOX.iterdir() if p.is_dir()):
        srts = sorted(folder.glob('*.srt'))
        if not srts:
            continue
        parsed = parse_folder(folder.name)
        if not parsed:
            left.append((folder.name, '폴더 이름에서 날짜·교시를 못 읽음 (예: 1117_1교시)'))
            continue
        day, period = parsed
        hit, year, why = find_lecture(tt, lec_table, day, period)
        if not hit:
            left.append((folder.name, why))
            continue
        subj_key, lec_id, lec_name = hit
        dest = ROOT / '학습자료' / S.folder(subj_key) / f'{lec_id}_{lec_name}' / '전사본'
        for n, src in enumerate(srts, 1):
            tail = '' if len(srts) == 1 else f'_{n}'
            out = dest / f'전사본_{year}_{period}교시{tail}.srt'
            moved.append((folder.name, out.relative_to(ROOT)))
            if not dry:
                dest.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(out))
        if not dry:
            rest = list(folder.iterdir())
            if all(p.name == '_원본.txt' for p in rest):
                shutil.rmtree(folder)

    for name, out in moved:
        print(f'  {name}  ->  {out}')
    for name, why in left:
        print(f'  [그대로 둠] {name} — {why}')
    print(f'\n옮김 {len(moved)}개, 남김 {len(left)}개' + (' (미리보기)' if dry else ''))
    return 0


if __name__ == '__main__':
    sys.exit(main(dry='--dry' in sys.argv))
