#!/usr/bin/env python3
"""1학기 자료를 과목마다 zip 하나(크면 몇 조각)로 묶어 Release 「sem1-downloads」 에 올린다.
로그인하지 않은 사람도 앱 「1학기 자료」 탭의 「과목 전체 내려받기」 버튼으로 받는다.

  python3 _자동관리/tools/sem1_zip.py build [--dry]      # .github/workflows/sem1-zips.yml 이 돌린다

- 무엇을 넣나: `1학기/목록.json` 의 과목별 파일 중 「지워도 될 것」(state del) 을 뺀 전부. 폴더 구조는 올린 그대로,
  zip 맨 위 폴더는 「01. 생리학」 처럼 1학기 과목 번호를 붙인다.
- 바뀐 과목만 다시 만든다: 파일 목록(경로·sha)의 지문을 `1학기/내려받기.json` 에 적어 두고 같으면 건너뜀.
- 이 스크립트는 저장소를 sparse + blob:none 으로 받은 상태에서 돈다. 과목 하나씩 `git sparse-checkout` 으로 받고, 묶고, 올리고, 비운다.
- `git ls-tree -l`(크기) 은 blob 을 전부 받아 오므로 쓰지 않는다. 크기는 목록.json 에 있다.
"""
import argparse, datetime as dt, json, os, subprocess, sys, zipfile
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import subjects as SJ  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent
LIST = '1학기/목록.json'
STATE = '1학기/내려받기.json'
TAG = 'sem1-downloads'
PART = 1900 * 1024 * 1024          # Release 파일 하나 2GB 까지
SLUG = {'생리학': 'physiology', '해부학': 'anatomy', '면역학': 'immunology', '병리학': 'pathology',
        '병원체학': 'microbiology', '약리학 총론': 'pharmacology', '기초의학종합': 'basic-medicine'}
DEFLATE = {'.txt', '.md', '.csv', '.hwp', '.doc', '.xls', '.ppt', '.rtf', '.html', '.htm', '.json', '.svg'}


def run(*a, check=True):
    r = subprocess.run(a, cwd=ROOT, text=True, capture_output=True)
    if check and r.returncode != 0:
        raise SystemExit(f'실패: {" ".join(a)}\n{r.stderr}')
    return r.stdout


def fnv(text):
    """앱(app.html D1.fp)과 같은 32비트 FNV-1a"""
    h = 0x811c9dc5
    for b in text.encode('utf-8'):
        h = ((h ^ b) * 0x01000193) & 0xffffffff
    return f'{h:08x}'


def number(s):
    for i, (k, show) in enumerate(SJ.ORDER[1], 1):
        if s in (k, show):
            return i
    return 99


def files_of(m, s, tree):
    sd = m['subjects'][s]
    out = [it for it in sd.get('items', []) if it.get('state') != 'del'
           and it['path'].startswith(f'1학기/{s}/') and it['path'] in tree]
    return sorted(out, key=lambda it: it['path'])


def fingerprint(items):
    return fnv('\n'.join(f'{it["path"]} {it["sha"]}' for it in items))


def split(items):
    parts, cur, size = [], [], 0
    for it in items:
        if cur and size + it['size'] > PART:
            parts.append(cur); cur, size = [], 0
        cur.append(it); size += it['size']
    if cur: parts.append(cur)
    return parts


def release_assets():
    if subprocess.run(['gh', 'release', 'view', TAG], cwd=ROOT, capture_output=True).returncode != 0:
        run('gh', 'release', 'create', TAG, '--title', '1학기 자료 · 과목별 내려받기', '--latest=false',
            '--notes', '앱 「1학기 자료」 탭의 「과목 전체 내려받기」가 여기 있는 압축을 줍니다. 자동으로 다시 만들어지니 손으로 고치지 마세요.')
    return {a['name'] for a in json.loads(run('gh', 'release', 'view', TAG, '--json', 'assets'))['assets']}


def save_state(st, dry):
    st['updated'] = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime('%Y-%m-%d %H:%M')
    text = json.dumps(st, ensure_ascii=False, indent=1) + '\n'
    (ROOT / STATE).write_text(text, 'utf-8')
    if dry: return
    run('git', 'add', STATE)
    if not run('git', 'status', '--porcelain', '--', STATE).strip(): return
    run('git', 'commit', '-q', '-m', '1학기 과목별 압축 목록')
    for _ in range(4):
        if subprocess.run(['git', 'push', '-q', 'origin', 'HEAD:main'], cwd=ROOT, capture_output=True).returncode == 0:
            return
        run('git', 'fetch', '-q', '--depth=1', 'origin', 'main')       # 다른 커밋이 먼저 들어옴 → 그 위에 다시
        run('git', 'reset', '-q', '--hard', 'origin/main')
        (ROOT / STATE).write_text(text, 'utf-8')
        run('git', 'add', STATE); run('git', 'commit', '-q', '-m', '1학기 과목별 압축 목록')
    raise SystemExit('목록을 푸시하지 못함')


def build(dry, only=None):
    m = json.loads((ROOT / LIST).read_text('utf-8'))
    tree = set(p for p in run('git', '-c', 'core.quotepath=false', 'ls-tree', '-r', '-z', '--name-only', 'HEAD', '--', '1학기').split('\0') if p)
    st = json.loads((ROOT / STATE).read_text('utf-8')) if (ROOT / STATE).exists() else {}
    st.setdefault('tag', TAG); st.setdefault('subjects', {})
    have = set() if dry else release_assets()
    base = [l for l in run('git', 'sparse-checkout', 'list', check=False).splitlines() if l.strip()]
    out_dir = ROOT / 'work' / 'zips'; out_dir.mkdir(parents=True, exist_ok=True)
    keep_assets = set()

    for s in sorted(m['subjects'], key=number):
        no = number(s)
        if no == 99 or (only and s != only): continue                                    # (과목 미정) 등은 묶지 않음
        items = files_of(m, s, tree)
        if not items:
            st['subjects'].pop(s, None); continue
        fp = fingerprint(items)
        old = st['subjects'].get(s)
        if old and old.get('fp') == fp and all(p['asset'] in have for p in old['parts']) and not dry:
            keep_assets |= {p['asset'] for p in old['parts']}
            print(f'{no:02d}. {s}: 바뀐 것 없음'); continue
        print(f'{no:02d}. {s}: {len(items)}개 묶는 중'); sys.stdout.flush()
        if base:
            run('git', 'sparse-checkout', 'set', '--no-cone', *base, f'/1학기/{s}/')
        top = f'{no:02d}. {s}'
        slug = SLUG.get(s, f'subject{no:02d}')
        groups = split(items)
        parts = []
        for k, grp in enumerate(groups, 1):
            asset = f'sem1-{no:02d}-{slug}' + (f'-part{k}' if len(groups) > 1 else '') + '.zip'
            label = top + (f' ({k}／{len(groups)})' if len(groups) > 1 else '') + '.zip'
            zp = out_dir / asset
            with zipfile.ZipFile(zp, 'w', allowZip64=True) as z:
                for it in grp:
                    src = ROOT / it['path']
                    if not src.exists():
                        raise SystemExit(f'파일을 받지 못함: {it["path"]}')
                    rel = it['path'][len(f'1학기/{s}/'):]
                    comp = zipfile.ZIP_DEFLATED if src.suffix.lower() in DEFLATE else zipfile.ZIP_STORED
                    z.write(src, f'{top}/{rel}', compress_type=comp)
            size = zp.stat().st_size
            if not dry:
                run('gh', 'release', 'upload', TAG, f'{zp}#{label}', '--clobber')
                zp.unlink()
            parts.append({'asset': asset, 'label': label, 'size': size, 'count': len(grp)})
            keep_assets.add(asset)
        st['subjects'][s] = {'no': no, 'fp': fp, 'count': len(items), 'bytes': sum(p['size'] for p in parts), 'parts': parts,
                             'built': dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime('%Y-%m-%d %H:%M')}
        if base:
            run('git', 'sparse-checkout', 'set', '--no-cone', *base)   # 디스크 비우기
        save_state(st, dry)                                          # 과목마다 바로 적어 두면 중간에 멈춰도 다음에 이어서

    for s in [s for s in st['subjects'] if s not in m['subjects']]:
        st['subjects'].pop(s)
    if not dry:
        for a in sorted(have - keep_assets):
            if a.startswith('sem1-'):
                run('gh', 'release', 'delete-asset', TAG, a, '--yes', check=False)
    save_state(st, dry)
    print('끝')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    b = sub.add_parser('build'); b.add_argument('--dry', action='store_true', help='올리지 않고 work/zips 에 만들기만')
    b.add_argument('--only', help='이 과목만 (시험용)')
    o = ap.parse_args()
    build(o.dry, o.only)
