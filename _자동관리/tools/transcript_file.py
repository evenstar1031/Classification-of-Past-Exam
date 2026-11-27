"""올리기/전사본/ 의 강의 녹음 전사본을 시간표로 수업을 찾아 학습자료 폴더에 넣는다.

폴더 이름에서 날짜와 교시를 읽어(`1117_01.1교시`, `2026-11-17_3교시`),
앱 시간표(_자동관리/app/app.html 의 DATA)로 그날 어떤 과목을 했는지 좁힌 뒤,
**전사본 첫머리를 읽어** 교수님이 말한 수업 이름으로 수업을 정한다.
(실제 수업 순서가 시간표와 다른 경우가 많아, 시간표는 후보를 좁히는 데만 쓴다.)
그 다음 과목정보에서 수업 번호를 찾아 아래로 옮긴다.

    학습자료/<학기>/<번호. 과목>/<id>_<수업명>/전사본/전사본_<날짜>.srt

이름에 교시를 쓰지 않는 이유: 실제 수업 순서가 시간표와 달라지는 일이 잦아
교시 번호는 틀리기 쉽다. 어느 수업인지는 내용으로 정하고, 이름에는 날짜만 남긴다.

녹음 하나에 두 수업이 이어 붙어 있는 일도 있다(쉬지 않고 다음 교시를 녹음한 경우).
그래서 1시간 조각들을 한 줄기로 이어 붙인 뒤, "반갑습니다 / 저는 ○○ 교수입니다 /
이번 시간에는 / 이상으로 마치겠습니다" 같은 말이 나오는 자리를 후보로 잡고,
그 앞뒤가 서로 **다른 수업**으로 읽히면 그 자리에서 잘라 각각의 수업에 넣는다.

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


def profs():
    """{(과목키, 수업 id): [교수 이름]} — 최근 연도부터"""
    out = {}
    for f in sorted(INFO.glob('*.json')):
        data = json.loads(f.read_text(encoding='utf-8'))
        for lec in data.get('lectures', []):
            names = []
            for _year, lst in sorted((lec.get('profs') or {}).items(), reverse=True):
                for nm in (lst or []):
                    if nm and nm not in names:
                        names.append(nm)
            out[(f.stem, lec.get('id'))] = names
    return out


PROF = {}


def guess_by_prof(head, cands):
    """"저는 ○○ 교수입니다" 처럼 교수님이 자기 이름을 말한 경우로 수업 고르기

    한 분이 여러 수업을 맡으면 가릴 수 없으니, 수업이 하나로 좁혀질 때만 쓴다."""
    hits = {}
    for cand in cands:
        for nm in PROF.get((cand[0], cand[1]), []):
            if re.search(re.escape(norm(nm)) + r'.{0,3}교수', head):
                hits[(cand[0], cand[1])] = cand
                break
    return list(hits.values())[0] if len(hits) == 1 else None


def parse_folder(name):
    """'1117_01.1교시' → ((11, 17), 1),  '1117' → ((11, 17), None).  못 읽으면 None

    교시는 없어도 된다. 하루를 통째로 녹음한 경우 날짜만 쓰면 되고,
    어느 수업인지는 내용으로 가린다."""
    n = unicodedata.normalize('NFC', name)
    d = re.match(r'\D*(?:(20\d{2})[-_.]?)?(\d{1,2})[-_.]?(\d{2})(?!\d)', n)
    if not d or not (1 <= int(d.group(2)) <= 12 and 1 <= int(d.group(3)) <= 31):
        # 앞이 아니라 중간에 붙은 날짜 (예: '01.1127. CP-D2 피드백' → 11/27)
        d = re.search(r'(?<!\d)()(0[1-9]|1[0-2])[-_.]?([0-3]\d)(?!\d)', n)
        if not d or not 1 <= int(d.group(3)) <= 31:
            return None
    m = re.search(r'(\d{1,2})\s*(?:교시|차시)', n)
    period = int(m.group(1)) if m else None
    return (int(d.group(2)), int(d.group(3))), period


def scan(text, name):
    """text 안에서 name 과 0.8 이상 닮은 자리 → (몇 번, 처음 위치, 가장 닮은 정도)

    전사본에는 오타가 섞이므로 글자 단위로 닮은 정도를 본다.
    느려지지 않게, 이름 토막이 아예 안 보이면 건너뛴다."""
    L = len(name)
    if L < 4 or len(text) < L:
        return 0, -1, 0.0
    if not any(name[i:i + 4] in text for i in range(0, L - 3, 2)):
        return 0, -1, 0.0
    need = -(-L * 8 // 10)          # 0.8 이상 (짧은 이름이 헐겁게 걸리지 않게 올림)
    count, first, best = 0, -1, 0.0
    i = 0
    while i <= len(text) - L:
        same = 0
        for a, b in zip(text[i:i + L], name):
            if a == b:
                same += 1
        if same >= need:
            count += 1
            best = max(best, same / L)
            if first < 0:
                first = i
            i += L
        else:
            i += 1
    return count, first, best


EARLY = 1500           # 이 글자 수 안에 나오면 "오늘 수업 제목"으로 본다


def guess_by_text(text, candidates, by_time=None):
    """수업 이름이 나오는 자리와 횟수로 수업 고르기 → (수업, 닮은 정도, 믿을 만한지)

    교수님은 거의 언제나 처음에 오늘 수업 이름을 말한다. 그래서 앞쪽에 나온 이름을
    먼저 믿고, 앞쪽에 아무 이름도 안 나오면(잡담으로 시작한 경우) 가장 자주
    되풀이되는 이름을 택한다. 지나가는 말로 한 번 나온 다른 수업에 끌려가지 않게."""
    scored = []
    for cand in candidates:
        count, first, ratio = 0, -1, 0.0
        for form in name_forms(cand[2]):
            n, pos, r = scan(text, form)
            if n:
                count = max(count, n)
                ratio = max(ratio, r)
                first = pos if first < 0 else min(first, pos)
        if count:
            near = 1 if (by_time and by_time[1] == cand[1] and by_time[0] == cand[0]) else 0
            scored.append((count, first, ratio, near, cand))
    if not scored:
        hit = guess_by_prof(text, candidates)
        return (hit, 0.9, True) if hit else (None, 0.0, False)

    early = [x for x in scored if x[1] < EARLY]
    if early:                                   # 앞머리에 이름을 말한 쪽
        early.sort(key=lambda x: (x[1] // 300, -x[3], x[1]))
        pick, sure = early[0], 'early'      # 참이지만, 앞머리에서 이름을 말했다는 표시
    else:                                       # 잡담으로 시작했으면 가장 자주 나온 쪽
        scored.sort(key=lambda x: (-x[0], -x[3], x[1]))
        pick, sure = scored[0], scored[0][0] >= 2
    return pick[4], pick[2], sure

# 새 수업이 시작될 때 교수님이 흔히 하는 말
CUE_START = re.compile(
    r'반갑습니다|안녕하십니까|안녕하세요'
    r'|교수(입니다|이고|예요|이에요)'
    r'|이번 ?시간(에는|은|부터)'
    r'|오늘 ?수업(에|을|은)? ?(들어가|시작)'
    r'|(에 ?대해서|에 ?대해|를|을) ?(이야기|말씀|강의|공부)(하겠습니다|해 ?보겠습니다)'
)
# 앞 수업이 끝날 때 흔히 하는 말
CUE_END = re.compile(
    r'(이상으로|이만|여기서)[^.]{0,12}(마치|마칠|끝내|끝나)'
    r'|수고(하셨습니다|했습니다)'
    r'|질문 ?(있으면|있으시면|없으시면)'
    r'|(끝내|마치)도록 ?하겠습니다'
)
MIN_SEC = 600          # 한 수업으로 볼 최소 길이 (10분)
GAP_SEC = 90           # 이만큼 조용하면 쉬는 시간으로 보고 수업이 바뀌는 자리 후보로 삼는다
TEXT_MAX = 60000       # 한 구간에서 읽을 글자 수 상한


def srt_blocks(path):
    """srt 파일 → [{'time': 시간줄, 'text': [글줄]}]"""
    blocks, cur = [], None
    for line in path.read_text(encoding='utf-8', errors='replace').split('\n'):
        t = line.strip()
        if '-->' in t:
            cur = {'time': t, 'text': []}
            blocks.append(cur)
        elif t and not t.isdigit() and cur is not None:
            cur['text'].append(t)
    return [b for b in blocks if b['text']]


def t_sec(stamp):
    m = re.match(r'(\d+):(\d\d):(\d\d)', stamp.strip())
    return int(m[1]) * 3600 + int(m[2]) * 60 + int(m[3]) if m else 0


def start_sec(block):
    return t_sec(block['time'].split('-->')[0])


def end_sec(block):
    half = block['time'].split('-->')
    return t_sec(half[1]) if len(half) > 1 else start_sec(block)


def shift(stamp, off):
    """00:12:34,560 → off 초 만큼 밀기"""
    m = re.match(r'(\d+):(\d\d):(\d\d)([,.]\d+)?', stamp.strip())
    if not m:
        return stamp.strip()
    sec = int(m[1]) * 3600 + int(m[2]) * 60 + int(m[3]) + off
    return '%02d:%02d:%02d%s' % (sec // 3600, sec // 60 % 60, sec % 60, m[4] or ',000')


CHUNK = 3600   # 노트북 전사 스크립트가 녹음을 자르는 길이(초) — 음성 조각 k 는 k*CHUNK 초에서 시작


def part_no(path):
    m = re.search(r'_part(\d+)$', Path(path).stem)
    return int(m.group(1)) if m else None


def merge_chunks(srts):
    """1시간 조각들(_part00, _part01 …)을 한 줄기로 이어 붙인다.
    조각 번호가 있으면 k*CHUNK 초에서 시작하게 해서 음성(mp3 조각)과 시각이 맞게 한다."""
    out, off = [], 0
    for path in srts:
        blocks = srt_blocks(path)
        if not blocks:
            continue
        k = part_no(path)
        if k is not None:
            off = k * CHUNK
        for b in blocks:
            half = b['time'].split('-->')
            b['time'] = shift(half[0], off) + ' --> ' + shift(half[-1], off)
            out.append(b)
        off = end_sec(out[-1])
    return out


def text_of(blocks, start, stop=None):
    """구간의 글자만 이어 붙이기"""
    got, n = [], 0
    for b in blocks[start:stop if stop is not None else len(blocks)]:
        for t in b['text']:
            got.append(t)
            n += len(t)
        if n > TEXT_MAX:
            break
    return norm(' '.join(got))[:TEXT_MAX]


def write_blocks(blocks, path):
    out = []
    for i, b in enumerate(blocks, 1):
        out.append('%d\n%s\n%s' % (i, b['time'], '\n'.join(b['text'])))
    path.write_text('\n\n'.join(out) + '\n', encoding='utf-8')


def split_points(blocks, cands, by_time):
    """수업이 바뀌는 자리 → 각 수업이 시작하는 블록 번호 [0, b1, …]

    쉬는 시간(긴 침묵)과 인사말이 나오는 자리를 모두 후보로 잡아 잘게 나눈 뒤,
    토막마다 어느 수업인지 가려서 **같은 수업끼리 다시 붙인다.**
    그래서 한 수업 안에서 잠깐 쉬거나 다른 수업 이름을 한 번 말해도 갈라지지 않는다."""
    if not blocks:
        return [0]
    cuts = [0]
    for i in range(1, len(blocks)):
        quiet = start_sec(blocks[i]) - end_sec(blocks[i - 1]) >= GAP_SEC
        if quiet or CUE_START.search(' '.join(blocks[i]['text'])) \
                or CUE_END.search(' '.join(blocks[i - 1]['text'])):
            cuts.append(i)

    segs = []
    for n, a in enumerate(cuts):
        b = cuts[n + 1] if n + 1 < len(cuts) else len(blocks)
        hit, _r, sure = guess_by_text(text_of(blocks, a, b), cands, by_time if n == 0 else None)
        segs.append([a, hit, sure])

    # 이름이 한 번 스치듯 나왔을 뿐인 토막(잡담·복습 중에 다른 수업 이름이 나온 경우)은
    # 믿을 만한 가장 가까운 토막의 수업에 붙인다
    sure = [i for i, g in enumerate(segs) if g[1] and g[2]]
    if sure:
        for i, g in enumerate(segs):
            if not (g[1] and g[2]):
                g[1] = segs[min(sure, key=lambda j: abs(j - i))][1]

    out, prev = [], None
    for a, hit, _c in segs:
        if hit is None:                      # 못 가린 토막은 앞 수업에 붙인다
            if not out:
                out.append(a)
            continue
        key = (hit[0], hit[1])
        if key == prev:
            continue
        if out and prev is None:             # 맨 앞의 못 가린 토막이 이 수업의 시작이었다
            prev = key
            continue
        out.append(a)
        prev = key

    kept = []                                # 너무 짧은 토막은 따로 두지 않는다
    for a in (out or [0]):
        if not kept or start_sec(blocks[a]) - start_sec(blocks[kept[-1]]) >= MIN_SEC:
            kept.append(a)
    return kept or [0]

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




def find_lecture(tt, lec_table, day, period):
    entry = tt.get(day)
    if not entry:
        return None, None, '시간표에 그 날짜가 없음'
    year, slots = entry
    if period is None:
        return None, year, '폴더 이름에 교시가 없어 내용으로만 가림'
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


def audio_plan(folder, srts):
    """노트북이 함께 올린 _음성.json(전사본 조각 → GitHub 릴리스 mp3 이름)을 읽어
    수업 전사본 옆에 둘 {tag, parts:[{file, start}]} 를 만든다. 없으면 None."""
    f = folder / '_음성.json'
    if not f.exists():
        return None
    try:
        info = json.loads(f.read_text(encoding='utf-8-sig'))
    except ValueError:
        return None
    names = info.get('parts') or {}
    parts = []
    for path in srts:
        a = names.get(Path(path).stem)
        if a:
            parts.append({'file': a, 'start': (part_no(path) or 0) * CHUNK})
    if not parts:
        return None
    return {'tag': info.get('tag') or 'lecture-audio', 'parts': parts}


def upload_day(folder):
    """폴더를 올린 커밋의 날짜(한국 시간) → (월, 일). git 이 없거나 기록이 없으면 오늘(한국)."""
    import datetime
    import subprocess
    kst = datetime.timezone(datetime.timedelta(hours=9))
    try:
        out = subprocess.run(['git', '-C', str(ROOT), 'log', '-1', '--format=%ct', '--', str(folder)],
                             capture_output=True, text=True, timeout=30).stdout.strip()
        t = datetime.datetime.fromtimestamp(int(out), kst) if out else datetime.datetime.now(kst)
    except (OSError, ValueError, subprocess.SubprocessError):
        t = datetime.datetime.now(kst)
    return (t.month, t.day)


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
    PROF.update(profs())
    by_subject = {}
    for key, lec_id, name in lec_table.values():
        by_subject.setdefault(key, []).append((key, lec_id, name))
    moved, left, used = [], [], set()
    taken = {}   # 날짜 → 이번에 이미 녹음이 들어간 수업들 (같은 날 녹음 두 개가 한 수업으로 몰리지 않게)

    for folder in sorted(p for p in INBOX.iterdir() if p.is_dir()):
        srts = sorted(folder.glob('*.srt'))
        if not srts:
            continue
        parsed = parse_folder(folder.name)
        guessed = ''
        if not parsed:
            # 폴더 이름에 날짜가 없으면 올린 날(그 폴더를 올린 커밋의 한국 날짜)로 시간표를 찾는다
            up = upload_day(folder)
            if up:
                m = re.search(r'(\d{1,2})\s*(?:교시|차시)', unicodedata.normalize('NFC', folder.name))
                parsed = (up, int(m.group(1)) if m else None)
                guessed = f'  (폴더 이름에 날짜가 없어 올린 날 {up[0]}/{up[1]} 수업으로 봄)'
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
        blocks = merge_chunks(srts)
        if not blocks:
            left.append((folder.name, '전사본이 비어 있음'))
            continue
        bounds = split_points(blocks, cands, by_time)
        if year is None:
            entry = tt.get(day)
            year = entry[0] if entry else 0
        stem = f'전사본_{year}-{day[0]:02d}-{day[1]:02d}'

        # 그날 시간표에 있는 수업들 (시간표 순서)
        today = []
        for _a, _b, title, _p in (tt.get(day) or (0, []))[1]:
            h = lec_table.get(norm(title))
            if h and h not in today:
                today.append(h)
        if day not in taken:   # 그날 녹음이 이미 들어간 수업(앞서 올린 것)도 '이미 있음'으로 친다
            taken[day] = [h for h in today
                          if list((ROOT / '학습자료' / S.folder(h[0]) / f'{h[1]}_{h[2]}' / '전사본').glob(stem + '*.srt'))]
        done = taken[day]

        plan, bad = [], None
        for n, start in enumerate(bounds):
            stop = bounds[n + 1] if n + 1 < len(bounds) else len(blocks)
            by_text, _r, how = guess_by_text(text_of(blocks, start, stop), cands,
                                             by_time if n == 0 else None)
            note = ''
            # 그날 시간표에 없는 수업은, 앞머리에서 그 수업 이름을 말했을 때만 믿는다
            # (본문에 지나가듯 나온 다른 수업 이름에 끌려가지 않게)
            if by_text and today and by_text not in today and how != 'early':
                by_text = None
            if not by_text and n == 0 and today and (not by_time or by_time in done):
                rest = [x for x in today if x not in done]
                if by_time in today:   # 시간표에서 그 교시 뒤의 수업부터
                    k = today.index(by_time)
                    rest = [x for x in today[k:] if x not in done] or rest
                if rest:
                    by_time = rest[0]
                    note = (f'  (시간표의 그 교시 수업은 이미 다른 녹음이 있어 그날 다음 수업 "{by_time[2]}" 으로 봄 — 확인 필요)'
                            if period else f'  (교시가 없어 그날 아직 녹음이 없는 수업 "{by_time[2]}" 으로 봄 — 확인 필요)')
            if by_text:
                hit = by_text
                if n == 0 and by_time and by_time[1] != by_text[1]:
                    note = (f'  (폴더 이름의 {period}교시는 시간표상 "{by_time[2]}" 이지만, '
                            f'내용이 "{by_text[2]}" 이라 내용을 따름)')
            elif n == 0 and by_time:
                hit = by_time
                note = note or '  (첫머리에서 수업 이름을 못 찾아 시간표대로 넣음 — 확인 필요)'
            else:
                bad = '이어 붙은 뒷부분이 어느 수업인지 못 찾음'
                break
            note += guessed if n == 0 else ''
            if len(bounds) > 1:
                note += f'  (한 녹음 안의 {n + 1}번째 수업, {start_sec(blocks[start]) // 60}분부터)'
            plan.append((hit, start, stop, note))
            done.append(hit)
        if bad:
            left.append((folder.name, bad))
            continue

        for hit, start, stop, note in plan:
            subj_key, lec_id, lec_name = hit
            dest = ROOT / '학습자료' / S.folder(subj_key) / f'{lec_id}_{lec_name}' / '전사본'
            out = free_name(dest, stem, used)
            moved.append((folder.name, out.relative_to(ROOT), note))
            if not dry:
                dest.mkdir(parents=True, exist_ok=True)
                write_blocks(blocks[start:stop], out)
                au = audio_plan(folder, srts)
                if au:   # 같은 녹음에서 나온 수업들은 시각이 원래 녹음 그대로라 같은 음성 목록을 쓴다
                    out.with_name(out.stem + '.음성.json').write_text(
                        json.dumps(au, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        if not dry:
            for src in srts:
                src.unlink()
            (folder / '_음성.json').unlink(missing_ok=True)
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
