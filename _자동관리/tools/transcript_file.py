"""올리기/전사본/ 의 강의 녹음 전사본을 시간표로 수업을 찾아 학습자료 폴더에 넣는다.

폴더 이름에서 날짜와 교시를 읽어(`1117_01.1교시`, `2026-11-17_3교시`),
앱 시간표(_자동관리/app/app.html 의 DATA)로 그날 어떤 과목을 했는지 좁힌 뒤,
**전사본 첫머리를 읽어** 교수님이 말한 수업 이름으로 수업을 정한다.
(실제 수업 순서가 시간표와 다른 경우가 많아, 시간표는 후보를 좁히는 데만 쓴다.)
그 다음 과목정보에서 수업 번호를 찾아 아래로 옮긴다.

    학습자료/<학기>/<번호. 과목>/<id>_<수업명>/전사본/전사본_<날짜>.srt

이름에 교시를 쓰지 않는 이유: 실제 수업 순서가 시간표와 달라지는 일이 잦아
교시 번호는 틀리기 쉽다. 어느 수업인지는 내용으로 정하고, 이름에는 날짜만 남긴다.

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


def head_text(srt, limit=4000):
    """전사본 첫머리 글자 (자막 번호·시간 줄 빼고)"""
    out = []
    for line in srt.read_text(encoding='utf-8', errors='replace').split('\n'):
        t = line.strip()
        if not t or t.isdigit() or '-->' in t:
            continue
        out.append(t)
        if sum(len(x) for x in out) > limit:
            break
    return norm(' '.join(out))[:limit]


def best_window(head, name):
    """head 안에서 name 과 가장 비슷한 자리의 (닮은 정도, 위치)"""
    L = len(name)
    if L < 4 or len(head) < L:
        return 0.0, -1
    best, pos = 0.0, -1
    for i in range(len(head) - L + 1):
        same = 0
        for a, b in zip(head[i:i + L], name):
            if a == b:
                same += 1
        r = same / L
        if r > best:
            best, pos = r, i
            if r == 1.0:
                break
    return best, pos


def day_subjects(tt, lec_table, day):
    """그날 시간표에 나오는 과목들의 키"""
    keys = []
    entry = tt.get(day)
    if not entry:
        return keys
    for _a, _b, title, _p in entry[1]:
        hit = lec_table.get(norm(title))
        if hit and hit[0] not in keys:
            keys.append(hit[0])
    return keys


def name_forms(name):
    """수업 이름과, 교수님이 줄여 부를 만한 토막 ('신종감염병 및 해외유입감염병' → 두 토막)"""
    forms = [norm(name)]
    for part in re.split(r'및|·|,|와 |과 |\(|\)', name):
        n = norm(part)
        if len(n) >= 4 and n not in forms:
            forms.append(n)
    return forms


def guess_by_text(head, candidates, by_time=None):
    """첫머리에 나오는 수업 이름으로 수업 고르기 → (수업, 닮은 정도)

    같은 점수면 먼저 나온 쪽을, 그래도 같으면 시간표가 가리키는 쪽을 택한다."""
    scored = []
    for cand in candidates:
        best = (0.0, -1)
        for form in name_forms(cand[2]):
            ratio, pos = best_window(head, form)
            if ratio > best[0]:
                best = (ratio, pos)
        ratio, pos = best
        if ratio < 0.8:
            continue
        bonus = 0.1 if (by_time and by_time[1] == cand[1] and by_time[0] == cand[0]) else 0.0
        scored.append((ratio + bonus - pos * 1e-6, ratio, cand))
    if not scored:
        return None, 0.0
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][2], scored[0][1]


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


def free_name(dest, stem, used):
    """같은 날 같은 수업 전사본이 여럿이면 _2, _3 을 붙인다"""
    cand = dest / f'{stem}.srt'
    i = 1
    while cand in used or cand.exists():
        i += 1
        cand = dest / f'{stem}_{i}.srt'
    used.add(cand)
    return cand


def main(dry=False):
    if not INBOX.exists():
        print('올릴 전사본이 없습니다.')
        return 0
    tt = timetable()
    lec_table = lectures()
    by_subject = {}
    for key, lec_id, name in lec_table.values():
        by_subject.setdefault(key, []).append((key, lec_id, name))
    moved, left, used = [], [], set()

    for folder in sorted(p for p in INBOX.iterdir() if p.is_dir()):
        srts = sorted(folder.glob('*.srt'))
        if not srts:
            continue
        parsed = parse_folder(folder.name)
        if not parsed:
            left.append((folder.name, '폴더 이름에서 날짜·교시를 못 읽음 (예: 1117_1교시)'))
            continue
        day, period = parsed
        by_time, year, why = find_lecture(tt, lec_table, day, period)

        # 그날 과목의 수업들 중에서 전사본 첫머리에 나오는 수업 이름 찾기
        keys = day_subjects(tt, lec_table, day)
        cands = [c for k in keys for c in by_subject.get(k, [])]
        if not cands:
            cands = [c for lst in by_subject.values() for c in lst]
        head = head_text(srts[0])
        by_text, ratio = guess_by_text(head, cands, by_time)

        hit, note = None, ''
        if by_text:
            hit = by_text
            if by_time and by_time[1] != by_text[1]:
                tname = by_time[2]
                note = (f'  (폴더 이름의 {period}교시는 시간표상 "{tname}" 이지만, '
                        f'내용이 "{by_text[2]}" 이라 내용을 따름)')
        elif by_time:
            hit = by_time
            note = '  (첫머리에서 수업 이름을 못 찾아 시간표대로 넣음 — 확인 필요)'
        else:
            left.append((folder.name, why or '시간표·내용 둘 다로 수업을 못 찾음'))
            continue
        if year is None:
            entry = tt.get(day)
            year = entry[0] if entry else 0

        subj_key, lec_id, lec_name = hit
        dest = ROOT / '학습자료' / S.folder(subj_key) / f'{lec_id}_{lec_name}' / '전사본'
        stem = f'전사본_{year}-{day[0]:02d}-{day[1]:02d}'
        for src in srts:
            out = free_name(dest, stem, used)
            moved.append((folder.name, out.relative_to(ROOT), note))
            note = ''
            if not dry:
                dest.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(out))
        if not dry:
            if all(p.name == '_원본.txt' for p in folder.iterdir()):
                shutil.rmtree(folder)

    for name, out, note in moved:
        print(f'  {name}  ->  {out}{note}')
    for name, why in left:
        print(f'  [그대로 둠] {name} — {why}')
    print(f'\n옮김 {len(moved)}개, 남김 {len(left)}개' + (' (미리보기)' if dry else ''))
    return 0


if __name__ == '__main__':
    sys.exit(main(dry='--dry' in sys.argv))
