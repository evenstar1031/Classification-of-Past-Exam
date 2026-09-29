#!/usr/bin/env python3
"""이 저장소가 GitHub에서 비공개(Private)인지 확인. 비공개가 아니면 종료코드 1.

기출 PDF·문제지는 학교 자료라서 공개 저장소에 올리면 안 된다.
Claude는 기출 파일을 커밋하기 전에 반드시 이걸 돌리고, OK가 아니면 커밋하지 않는다.
"""
import json, re, subprocess, sys, urllib.request

url = subprocess.run(['git', 'remote', 'get-url', 'origin'], capture_output=True, text=True).stdout.strip()
m = re.search(r'github\.com[/:]([^/]+)/([^/.]+?)(?:\.git)?/?$', url)
if not m:
    sys.exit(f'!! origin 주소를 알 수 없음: {url!r} — 사용자에게 저장소가 Private인지 확인받을 것')
api = f'https://api.github.com/repos/{m.group(1)}/{m.group(2)}'
try:
    d = json.load(urllib.request.urlopen(api, timeout=20))
except Exception as e:
    sys.exit(f'!! 공개 여부를 확인하지 못함 ({e}) — 사용자에게 저장소가 Private인지 확인받을 것')
if d.get('private'):
    print(f'[OK] {m.group(1)}/{m.group(2)} 는 비공개 저장소입니다.')
else:
    print(f'[STOP] {m.group(1)}/{m.group(2)} 는 공개(Public) 저장소입니다. 기출 파일을 커밋하지 마세요.\n'
          '       사용자에게: GitHub 저장소 → Settings → 맨 아래 Danger Zone → Change visibility → Make private')
    sys.exit(1)
