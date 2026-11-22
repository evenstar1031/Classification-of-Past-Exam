#!/usr/bin/env python3
"""1학기 자료 압축을 풀어 `1학기/<과목>/` 에 정리하고, 앱이 읽는 목록 `1학기/목록.json` 을 만든다.

  python3 _자동관리/tools/sem1_import.py import --src <압축들이 있는 폴더> --tag <Release 태그> [--commit]
  python3 _자동관리/tools/sem1_import.py sync        # 파일이 옮겨지거나(올리기 → 원본) 지워졌으면 목록을 맞춘다

하는 일 (import)
  1) 압축(zip·7z·rar·나눈 압축 .001)을 푼다. 윈도에서 만든 zip 의 한글 이름(CP949)도 살린다. 압축 속 압축도 한 번 더 푼다.
  2) 맨 위 폴더 = 과목. 과목 폴더 밖의 파일은 「(과목 미정)」.
  3) 파일마다 종류(기출·강의자료·필기·정리본·기타)를 파일 이름 → 위 폴더 이름 순으로 정한다.
  4) 넣지 않는 것(skipped): 찌꺼기(.DS_Store·__MACOSX·~$ 임시파일·빈 파일), 저장소/압축 안에 똑같은 파일이 이미 있는 것,
     녹음·영상, 100MB 넘는 것(PDF 는 먼저 줄여 보고 그래도 크면).
  5) 넣되 사용자가 볼 것
       del   지워도 될 것 같은 것 — 글이 똑같은 다른 판, 이름만 다른 옛 판((1)·복사본·최종·v2 …)
       check 확인 필요 — 종류가 애매, 과목 폴더 밖, 사진·한글 파일로 된 기출, 열리지 않는 PDF
       기출 PDF는 그대로 넣는다(이미 수업별로 정리된 경우가 많음). 자동으로 기출 분류를 돌리지 않는다.
       queued/done: 앱에서 「수업별 문제지로 만들기」를 고른 기출 → `올리기/<과목>/` → 「기출 자동 정리」 → `_자동관리/원본/`
  6) --commit: 과목마다 커밋하고 바로 푸시(한 번에 2GB 넘게 밀지 않으려고), 마지막에 목록을 커밋.
"""
import argparse, datetime as dt, hashlib, json, os, re, shutil, subprocess, sys, tempfile, unicodedata, zipfile
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import subjects as SJ  # noqa: E402  (과목 키 → 보이는 폴더 '01. 진단의 기본')

ROOT = Path(__file__).resolve().parent.parent.parent   # 저장소 맨 위 (이 파일은 _자동관리/tools/)
BASE = '1학기'
MANIFEST = ROOT / BASE / '목록.json'
LIMIT = 95 * 1024 * 1024            # GitHub 은 파일 하나 100MB 까지
BATCH = 900 * 1024 * 1024           # 한 번에 푸시할 양
NOSUBJ = '(과목 미정)'

JUNK_NAMES = {'thumbs.db', 'desktop.ini', '.ds_store', 'icon\r'}
JUNK_EXT = {'.tmp', '.lnk', '.url', '.ini', '.crdownload', '.part', '.download'}
MEDIA_EXT = {'.mp4', '.mov', '.avi', '.mkv', '.wmv', '.webm', '.m4v', '.m4a', '.mp3', '.wav', '.aac', '.wma', '.flac', '.ogg', '.amr'}
ARCH_EXT = {'.zip', '.7z', '.rar', '.tar', '.gz', '.tgz', '.bz2', '.xz'}
IMG_EXT = {'.png', '.jpg', '.jpeg', '.heic', '.webp', '.gif', '.bmp', '.tif', '.tiff'}
KINDS = [  # 앞에 있을수록 우선
    ('기출', re.compile(r'기출|족보|시험|고사|퀴즈|쪽지|quiz|exam|midterm|mid-term|final ?test', re.I)),
    ('필기', re.compile(r'필기|노트|note|굿노트|goodnote|녹취|판서', re.I)),
    ('정리본', re.compile(r'정리|요약|summary|단권|핵심|암기|요점', re.I)),
    ('강의자료', re.compile(r'강의|lecture|\blec|슬라이드|slide|ppt|교안|수업 ?자료|handout|강의록|프린트', re.I)),
]
KIND_FOLDER = re.compile(r'^\s*(\d+[.)_\-\s]+)?(' + '|'.join(k[1].pattern for k in KINDS) + r'|자료|기타|etc|과제|실습)', re.I)
COPY_TAIL = re.compile(r'(\s*\(\d+\)|\s*-?\s*(복사본|사본)(\s*\(\d+\))?|\s*copy(\s*\d+)?)+$', re.I)       # 같은 것의 사본
NEWER_TAIL = re.compile(r'([\s_\-]*(최종|final|수정본?|v\d+|ver\.?\s?\d+|new))+$', re.I)                          # 고친 새 판
def strip_tails(stem):
    for _ in range(3): stem = NEWER_TAIL.sub('', COPY_TAIL.sub('', stem))
    return stem


def has_tail(name): return bool(COPY_TAIL.search(Path(name).stem))      # (1)·사본 → 남길 차례가 뒤로
def is_newer(name): return bool(NEWER_TAIL.search(COPY_TAIL.sub('', Path(name).stem)))   # 최종·v2 → 앞으로
def nfc(s): return unicodedata.normalize('NFC', s)
def norm(s): return re.sub(r'[\s·・.,_\-()\[\]]+', '', nfc(s)).lower()
def mb(n): return f'{n / 1048576:.1f}MB' if n >= 1048576 else f'{max(1, n // 1024)}KB'
def blob_sha(data): return hashlib.sha1(b'blob %d\0' % len(data) + data).hexdigest()
def run(*a, **k): return subprocess.run(a, check=True, text=True, capture_output=True, cwd=ROOT, **k).stdout


def git_tracked():
    """path → blob sha, 그리고 sha → [path]"""
    out = run('git', '-c', 'core.quotepath=false', 'ls-files', '-s', '-z').split('\0')
    by_path, by_sha = {}, {}
    for line in out:
        if not line: continue
        meta, path = line.split('\t', 1)
        sha = meta.split()[1]
        by_path[path] = sha
        by_sha.setdefault(sha, []).append(path)
    return by_path, by_sha


def subject_info():
    """과목정보에 있는 과목 이름들 (정규화 → 실제 이름)"""
    return {norm(p.stem): p.stem for p in (ROOT / '_자동관리/과목정보').glob('*.json')}


def clean_subject(name):
    n = nfc(name).strip()
    n = re.sub(r'^\s*\d+[.)_\-\s]+', '', n).strip() or n
    return n.replace('/', '·')


def load_manifest():
    if MANIFEST.exists():
        return json.loads(MANIFEST.read_text('utf-8'))
    return {'updated': None, 'imports': [], 'subjects': {}}


def save_manifest(m):
    m['updated'] = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime('%Y-%m-%d %H:%M')
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(m, ensure_ascii=False, indent=1) + '\n', 'utf-8')


# ───────────────────────── 압축 풀기 ─────────────────────────
def safe_parts(name):
    parts = [p for p in nfc(name).replace('\\', '/').split('/') if p not in ('', '.', '..')]
    return [p.strip() or '_' for p in parts]


def unzip(path, dest):
    with zipfile.ZipFile(path) as z:
        for info in z.infolist():
            name = info.filename
            if not info.flag_bits & 0x800:          # UTF-8 표시가 없으면 대개 윈도(CP949)
                raw = name.encode('cp437', errors='ignore')
                for enc in ('utf-8', 'cp949'):
                    try: name = raw.decode(enc); break
                    except UnicodeDecodeError: pass
            parts = safe_parts(name)
            if info.is_dir() or not parts: continue
            out = dest.joinpath(*parts)
            out.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as s, open(out, 'wb') as d:
                shutil.copyfileobj(s, d, 1 << 20)
            try:
                t = dt.datetime(*info.date_time).timestamp(); os.utime(out, (t, t))
            except Exception: pass


def nfc_tree(d):
    for p in sorted(d.rglob('*'), key=lambda x: -len(x.parts)):
        n = nfc(p.name)
        if n != p.name and not (p.parent / n).exists():
            p.rename(p.parent / n)


def extract(path, dest):
    """압축 하나를 dest 에 푼다. 실패하면 이유 문자열"""
    low = path.name.lower()
    try:
        if low.endswith('.zip') and zipfile.is_zipfile(path):
            unzip(path, dest)
        else:
            r = subprocess.run(['7z', 'x', '-y', '-p', f'-o{dest}', str(path)], capture_output=True, text=True)
            if r.returncode != 0:
                msg = (r.stderr or r.stdout)
                return '암호가 걸린 압축' if 'password' in msg.lower() or 'Wrong password' in msg else '풀 수 없는 압축'
            nfc_tree(dest)
    except RuntimeError as e:
        return '암호가 걸린 압축' if 'encrypted' in str(e).lower() or 'password' in str(e).lower() else f'풀 수 없는 압축 ({e})'
    except (zipfile.BadZipFile, OSError) as e:
        return f'풀 수 없는 압축 ({e.__class__.__name__})'
    return None


def is_archive(p):
    low = p.name.lower()
    if re.search(r'\.(zip|7z|rar)\.0*1$', low): return True                # 나눈 압축의 첫 조각
    if re.search(r'\.(zip|7z|rar)\.\d+$', low) or re.search(r'\.z\d\d$|\.part\d+\.rar$', low): return False
    return p.suffix.lower() in ARCH_EXT


def is_split_rest(p):
    low = p.name.lower()
    return bool(re.search(r'\.(zip|7z|rar)\.0*([2-9]|\d\d+)$', low) or re.search(r'\.z\d\d$', low)
                or (re.search(r'\.part(\d+)\.rar$', low) and not re.search(r'\.part0*1\.rar$', low)))


# ───────────────────────── 고르기 ─────────────────────────
def is_junk(p, rel_parts):
    n = p.name.lower()
    return (n in JUNK_NAMES or n.startswith('.') or n.startswith('~$') or p.suffix.lower() in JUNK_EXT
            or any(x == '__MACOSX' for x in rel_parts) or p.stat().st_size == 0)


def visible_children(d):
    out = []
    for c in sorted(d.iterdir()):
        if c.name == '__MACOSX' or c.name.startswith('.') or c.name.lower() in JUNK_NAMES: continue
        out.append(c)
    return out


def subjects_in(top, fallback):
    """압축을 푼 폴더 → [(과목 이름, 과목 폴더)] , 과목 밖 파일 [(path)]"""
    d = top
    while True:
        kids = visible_children(d)
        dirs = [k for k in kids if k.is_dir()]
        files = [k for k in kids if k.is_file()]
        if dirs and all(KIND_FOLDER.match(k.name) for k in dirs):     # 아래가 기출·강의자료 … → 여기가 과목
            name = d.name if d != top else fallback
            return [(clean_subject(name), d)], []
        if len(dirs) == 1 and not files:
            d = dirs[0]; continue
        return [(clean_subject(k.name), k) for k in dirs], files


def kind_of(rel_parts):
    ext = Path(rel_parts[-1]).suffix.lower()
    comps = [Path(rel_parts[-1]).stem] + list(reversed(rel_parts[:-1]))
    for c in comps:
        hits = [k for k, rx in KINDS if rx.search(c)]
        if hits:
            amb = hits[0] == '기출' and len(hits) > 1 and '정리본' in hits
            return hits[0], amb
    if ext in ('.ppt', '.pptx', '.key'): return '강의자료', False
    return '기타', False


def pdf_info(path):
    """(쪽수, 글 해시 또는 None) — 열리지 않으면 (None, None)"""
    try:
        import fitz
        with fitz.open(path) as doc:
            txt = ''.join(pg.get_text() for pg in doc)
            n = doc.page_count
    except Exception:
        return None, None
    t = re.sub(r'\s+', '', txt)
    return n, (hashlib.sha1(t.encode()).hexdigest()[:16] if len(t) >= 200 else None)


def shrink_pdf(src, dst):
    r = subprocess.run(['gs', '-sDEVICE=pdfwrite', '-dPDFSETTINGS=/ebook', '-dCompatibilityLevel=1.5',
                        '-dNOPAUSE', '-dBATCH', '-dQUIET', f'-sOutputFile={dst}', str(src)], capture_output=True)
    return r.returncode == 0 and dst.exists() and dst.stat().st_size <= LIMIT


def unique_dest(rel, taken):
    p = Path(rel)
    if rel not in taken: return rel
    stamp = dt.date.today().strftime('%y%m%d')
    for i in range(1, 100):
        cand = str(p.with_name(f'{p.stem} ({stamp}{"" if i == 1 else "-" + str(i)}){p.suffix}'))
        if cand not in taken: return cand
    raise RuntimeError(rel)


def do_import(src, tag, commit):
    by_path, by_sha = git_tracked()
    info = subject_info()
    m = load_manifest()
    imp = f'{dt.date.today():%y%m%d}-{re.sub(r"[^0-9A-Za-z가-힣]+", "", tag)[:24] or "up"}'
    if any(i['id'] == imp for i in m['imports']):
        imp += f'-{len(m["imports"]) + 1}'
    work = Path(tempfile.mkdtemp(prefix='sem1-', dir=ROOT / 'work' if (ROOT / 'work').exists() else None))

    skipped = {}      # 과목 → [{name, why}]
    staged = []       # 넣을 파일들
    archives = []

    def skip(subj, name, why):
        skipped.setdefault(subj, []).append({'name': name, 'why': why, 'imp': imp})

    assets = sorted(Path(src).iterdir())
    for a in assets:
        if is_split_rest(a): continue
        archives.append(a.name)
        if not is_archive(a):                     # 압축이 아닌 파일을 그대로 올린 경우
            d = work / f'_{len(archives)}'; d.mkdir(parents=True)
            shutil.copy2(a, d / nfc(a.name)); tops = [(d, Path(a.name).stem)]
        else:
            d = work / f'_{len(archives)}'; d.mkdir(parents=True)
            why = extract(a, d)
            if why: skip(NOSUBJ, a.name, why); continue
            a.unlink(missing_ok=True)                # 디스크 아끼기
            for _ in range(2):                       # 압축 속 압축
                inner = [p for p in d.rglob('*') if p.is_file() and is_archive(p) and '__MACOSX' not in p.parts]
                if not inner: break
                for p in inner:
                    out = p.with_name(re.sub(r'\.(zip|7z|rar|tar|gz|tgz|bz2|xz)(\.0*1)?$', '', p.name, flags=re.I))
                    if out.exists(): out = out.with_name(out.name + '_압축')
                    out.mkdir(parents=True)
                    if extract(p, out) is None: p.unlink()
                    else: shutil.rmtree(out, ignore_errors=True)
            tops = [(d, re.sub(r'\.(zip|7z|rar|tar|gz|tgz)(\.0*1)?$', '', nfc(a.name), flags=re.I))]
        for top, stem in tops:
            subs, loose = subjects_in(top, stem)
            groups = [(s, sd, sd) for s, sd in subs] + [(NOSUBJ, f.parent, f) for f in loose]
            for subj, base, what in groups:
                files = [what] if what.is_file() else sorted(p for p in what.rglob('*') if p.is_file())
                for f in files:
                    rel = [nfc(x) for x in f.relative_to(base).parts]
                    src_name = f'{a.name}/' + '/'.join(nfc(x) for x in f.relative_to(top).parts)
                    if is_junk(f, rel): continue                         # 찌꺼기는 목록에도 안 남김
                    ext = f.suffix.lower()
                    if is_split_rest(f) or is_archive(f): skip(subj, src_name, '풀지 못한 압축'); continue
                    if ext in MEDIA_EXT: skip(subj, src_name, f'녹음·영상 파일이라 넣지 않음 ({mb(f.stat().st_size)})'); continue
                    staged.append({'subj': subj, 'file': f, 'rel': rel, 'src': src_name})

    # ── 파일마다: 크기, 같은 파일, 종류 ──
    m_subj = m['subjects']
    known_text = {}            # 글 해시 → path (이미 목록에 있는 것)
    for s, sd in m_subj.items():
        for it in sd.get('items', []):
            if it.get('th'): known_text.setdefault(it['th'], it['path'])
    taken = set(by_path)
    seen_sha = {}
    new_items = []
    for st in staged:
        f, subj = st['file'], st['subj']
        note = None
        size = f.stat().st_size
        if size > LIMIT:
            if f.suffix.lower() == '.pdf':
                small = f.with_name(f.stem + '.__small.pdf')
                if shrink_pdf(f, small):
                    note = f'용량이 커서 줄여 넣음 (원래 {mb(size)})'; f.unlink(); small.rename(f); size = f.stat().st_size
                else:
                    small.unlink(missing_ok=True)
                    skip(subj, st['src'], f'100MB가 넘어 넣지 못함 ({mb(size)}) — 앱의 PDF 압축으로 줄여서 올려 주세요'); continue
            else:
                skip(subj, st['src'], f'100MB가 넘어 넣지 못함 ({mb(size)})'); continue
        data = f.read_bytes()
        sha = blob_sha(data)
        if sha in by_sha:
            skip(subj, st['src'], f'저장소에 똑같은 파일이 이미 있음: {by_sha[sha][0]}'); continue
        if sha in seen_sha:
            skip(subj, st['src'], f'압축 안에 똑같은 파일이 또 있음: {seen_sha[sha]}'); continue
        kind, amb = kind_of(st['rel'])
        rel = '/'.join([BASE, subj] + st['rel'])
        ext = f.suffix.lower()
        it = {'path': None, 'name': st['rel'][-1], 'kind': kind, 'size': size, 'sha': sha, 'imp': imp, 'src': st['src'],
              'state': 'ok', 'mtime': int(f.stat().st_mtime)}
        if note: it['note'] = note
        if ext == '.pdf':
            pages, th = pdf_info(f)
            if pages is None:
                it.update(state='check', why='열리지 않는 PDF예요. 깨진 파일이면 지워 주세요.')
            else:
                it['pages'] = pages
                if th: it['th'] = th
        # 종류별
        if it['state'] == 'ok':
            if subj == NOSUBJ:
                it.update(state='check', why='과목 폴더 밖에 있던 파일이에요. 어느 과목인지 확인해 주세요.')
            elif amb:
                it.update(state='check', why='기출인지 정리본인지 이름만으로 애매해요.')
            elif kind == '기타':
                it.update(state='check', why='어떤 자료인지 이름으로 알 수 없어요. 열어 보고 남길지 정해 주세요.')
            elif kind == '기출' and ext != '.pdf':
                it.update(state='check', why=('사진으로 된 기출이에요.' if ext in IMG_EXT else 'PDF가 아닌 기출이에요.')
                          + ' Claude에게 맡기면 문제지로 만들 수 있어요.')
            # 기출 PDF는 그대로 넣는다 — 1학기 기출은 이미 수업별로 정리해 둔 경우가 많아서 자동으로 분류를 돌리지 않는다.
            # 수업별 문제지로 다시 만들고 싶은 과목은 앱에서 골라 「올리기/」 로 보낸다(queued).
        rel = unique_dest(rel, taken)
        taken.add(rel); seen_sha[sha] = rel
        it['path'] = rel
        st['dest'] = rel; st['item'] = it
        new_items.append(st)

    # ── 지워도 될 것 같은 것: 글이 같은 다른 판, 이름만 다른 옛 판 ──
    # 「(1)·사본·최종」 같은 꼬리가 없는 것, 그다음 새것을 남긴다
    for st in sorted(new_items, key=lambda x: (has_tail(x['rel'][-1]), -x['item']['mtime'])):
        it = st['item']
        th = it.get('th')
        if th and th in known_text and it['state'] == 'ok':
            it.update(state='del', why='글이 똑같은 다른 판이 이미 있어요.', pair=known_text[th])
        elif th:
            known_text[th] = it['path']
    groups = {}
    for st in new_items:
        it = st['item']
        if it['state'] != 'ok': continue
        p = Path(st['rel'][-1])
        key = (st['subj'], '/'.join(st['rel'][:-1]), it['kind'], p.suffix.lower(), norm(strip_tails(p.stem)))
        groups.setdefault(key, []).append(it)
    for g in groups.values():
        if len(g) < 2: continue
        g.sort(key=lambda x: (is_newer(x['name']), x['mtime'] // 60, not has_tail(x['name']), x['size']), reverse=True)
        for old in g[1:]:
            old.update(state='del', why='이름이 비슷한 옛 판 같아요.', pair=g[0]['path'])

    # ── 파일 옮기기 ──
    for st in new_items:
        out = ROOT / st['dest']
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(st['file']), out)

    # ── 목록 ──
    total = 0
    for st in new_items:
        sd = m_subj.setdefault(st['subj'], {'items': [], 'skipped': []})
        sd['items'].append(st['item']); total += st['item']['size']
    for s, lst in skipped.items():
        m_subj.setdefault(s, {'items': [], 'skipped': []})['skipped'].extend(lst)
    m['imports'].append({'id': imp, 'tag': tag, 'date': dt.date.today().isoformat(), 'archives': archives,
                         'added': len(new_items), 'skipped': sum(len(v) for v in skipped.values()), 'bytes': total})
    sync(m)
    shutil.rmtree(work, ignore_errors=True)

    if commit:
        push_by_subject(new_items, imp)
    save_manifest(m)
    report(m, imp, new_items, skipped)
    if commit:
        run('git', 'add', str(MANIFEST.relative_to(ROOT)))
        if run('git', 'status', '--porcelain', '--', str(MANIFEST.relative_to(ROOT))).strip():
            git_commit_push(f'1학기 자료 목록 ({tag})')
    print(f'넣음 {len(new_items)}개 ({mb(total)}), 뺀 것 {sum(len(v) for v in skipped.values())}개')


def git_commit_push(msg):
    run('git', 'commit', '-q', '-m', msg)
    for i in range(4):
        r = subprocess.run(['git', 'push', '-q', 'origin', 'HEAD:main'], cwd=ROOT, capture_output=True, text=True)
        if r.returncode == 0: return
        subprocess.run(['git', 'pull', '-q', '--rebase', 'origin', 'main'], cwd=ROOT, capture_output=True)
    raise SystemExit('푸시하지 못함: ' + r.stderr)


def push_by_subject(new_items, imp):
    by = {}
    for st in new_items: by.setdefault(st['subj'], []).append(st)
    for subj, lst in by.items():
        batch, size = [], 0
        def flush():
            nonlocal batch, size
            if not batch: return
            run('git', 'add', '--', *[st['dest'] for st in batch])
            git_commit_push(f'1학기 자료: {subj} {len(batch)}개 ({imp})')
            batch, size = [], 0
        for st in lst:
            batch.append(st); size += st['item']['size']
            if size >= BATCH: flush()
        flush()


def report(m, imp, new_items, skipped):
    lines = [f'## 1학기 자료 정리 ({imp})', '']
    cnt = {}
    for st in new_items:
        c = cnt.setdefault(st['subj'], {})
        c[st['item']['state']] = c.get(st['item']['state'], 0) + 1
        c['n'] = c.get('n', 0) + 1
    lines.append('| 과목 | 넣음 | 기출 | 지워도 될 것 | 확인 필요 | 뺀 것 |')
    lines.append('|---|---|---|---|---|---|')
    for s in sorted(set(cnt) | set(skipped)):
        c = cnt.get(s, {})
        g = sum(1 for st in new_items if st['subj'] == s and st['item']['kind'] == '기출')
        lines.append(f'| {s} | {c.get("n", 0)} | {g} | {c.get("del", 0)} | {c.get("check", 0)} | {len(skipped.get(s, []))} |')
    lines += ['', '기출은 올린 그대로 넣었고 자동 분류는 돌리지 않았어요. 수업별 문제지로 다시 만들고 싶은 과목은 앱에서 고르면 됩니다.',
              '자세한 목록과 지우기·남기기는 앱의 **1학기 자료** 탭에서 할 수 있어요.']
    (ROOT / 'work').mkdir(exist_ok=True)
    (ROOT / 'work' / 'sem1_report.md').write_text('\n'.join(lines) + '\n', 'utf-8')


# ───────────────────────── 목록 맞추기 ─────────────────────────
def sync(m=None):
    own = m is None
    if own:
        if not MANIFEST.exists(): print('목록 없음'); return False
        m = load_manifest()
    before = json.dumps(m, ensure_ascii=False, sort_keys=True)
    by_path, by_sha = git_tracked()
    info = subject_info()
    for subj, sd in m['subjects'].items():
        keep = []
        for it in sd.get('items', []):
            p = it['path']
            on_disk = p in by_path or (ROOT / p).exists()
            if not on_disk:
                moved = [q for q in by_sha.get(it['sha'], []) if q != p]
                if moved:                                       # 올리기 → 원본 처럼 옮겨짐
                    it['path'] = sorted(moved, key=lambda q: (not q.startswith('_자동관리/원본/'), q))[0]
                else:
                    continue                                    # 지워짐
            if it['state'] == 'queued' and it['path'].startswith('_자동관리/원본/'):
                it['state'] = 'done'; it.pop('why', None)
            keep.append(it)
        sd['items'] = keep
        real = info.get(norm(subj))
        sd['info'] = real
        sd['gichul'] = real if real and (ROOT / '문제지' / SJ.folder(real)).is_dir() else None
        sd['upload'] = f'올리기/{SJ.folder(real)}' if real else None   # 「수업별 문제지로 만들기」가 옮길 곳
    m['subjects'] = {s: sd for s, sd in m['subjects'].items() if sd.get('items') or sd.get('skipped')}
    changed = json.dumps(m, ensure_ascii=False, sort_keys=True) != before
    if own and changed:
        save_manifest(m)
    if own: print('목록 맞춤' if changed else '바뀐 것 없음')
    return changed


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    a = sub.add_parser('import'); a.add_argument('--src', required=True); a.add_argument('--tag', required=True)
    a.add_argument('--commit', action='store_true')
    sub.add_parser('sync')
    o = ap.parse_args()
    if o.cmd == 'import': do_import(o.src, o.tag, o.commit)
    else: sync()
