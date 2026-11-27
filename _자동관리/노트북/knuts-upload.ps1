# KNUTS 전사본 GitHub 올리기 (v2, 2026-11-27)
# 이 폴더에 만들어진 전사본(.srt)을 Classification-of-Past-Exam 저장소의
# "올리기/전사본" 으로, 전사에 쓴 MP3를 GitHub 릴리스 "강의 음성"으로 올립니다.
# 처음 실행하면 git 설치와 저장소 연결까지 알아서 합니다.
# 다른 폴더의 전사본도 올리려면 그 폴더를 이 파일 위에 끌어다 놓으세요.
#
# v2에서 바뀐 것
#  - 음성을 먼저 올리고, 어느 전사본이 어느 MP3인지(_음성.json)를 전사본과 함께 올립니다
#    → 앱 전사본 화면에서 문장을 누르면 그 자리부터 수업 녹음이 나옵니다.
#  - 릴리스 파일 이름에 날짜를 넣고(예: 20261127_01.1_p00.mp3) 덮어쓰지 않습니다.
#  - 폴더 이름에 날짜가 없으면 녹음 날짜를 앞에 붙여 올립니다(1127_01.1교시 …) → 자동 분류가 멈추지 않음.
#  - 원본 MP3는 그 음성이 GitHub에 올라간 것이 확인될 때만 지웁니다.

param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Items)

$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$here    = $PSScriptRoot
$repoDir = Join-Path $here "전사본저장소"
$url     = "https://github.com/seohoe1031/Classification-of-Past-Exam.git"
$skip    = @("전사본저장소", "입력", "Faster-Whisper-XXL", "ffmpeg")
$mine    = Join-Path $here "전사본"
$pushed  = $false
$TAG     = "lecture-audio"   # 강의 음성을 모아 둘 GitHub 릴리스 이름
$DeleteLocalMp3 = $true      # 올린 뒤 노트북의 MP3를 지워 공간을 비웁니다 (원본 녹화본은 그대로)
$CleanLocal     = $true      # 다 올라간 뒤 노트북의 전사본·MP3를 지웁니다 (GitHub에만 남김)
$DeleteSourceMp3 = $true     # 전사에 쓴 원본 MP3도 지웁니다 — 음성이 GitHub에 올라간 게 확인될 때만 (화면 녹화본 mp4는 건드리지 않음)

function Say($msg, $color) {
  if ($color) { Write-Host $msg -ForegroundColor $color } else { Write-Host $msg }
}
function HasDate($name) {
  # 이름에 날짜(1117, 2026-11-17)가 들어 있는지 — knuts-transcribe.ps1 과 같은 규칙
  if (-not $name) { return $false }
  return ($name -match '(^|\D)(20\d{2}[-_.]?)?(0?[1-9]|1[0-2])[-_.]?[0-3]\d(\D|$)')
}
function RecDate($dir) {
  # 녹음 날짜: _원본.txt 가 가리키는 원본 파일의 수정 시각, 없으면 폴더를 만든 시각
  $mark = Join-Path $dir.FullName "_원본.txt"
  if (Test-Path -LiteralPath $mark) {
    $src = (Get-Content -LiteralPath $mark -Raw -Encoding UTF8).Trim()
    if ($src -and (Test-Path -LiteralPath $src)) { return (Get-Item -LiteralPath $src).LastWriteTime }
  }
  return $dir.CreationTime
}
function WriteUtf8($path, $text) {
  [System.IO.File]::WriteAllText($path, $text, (New-Object System.Text.UTF8Encoding $false))
}
function HasGit { return [bool](Get-Command git -ErrorAction SilentlyContinue) }
function RefreshPath {
  $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
              [System.Environment]::GetEnvironmentVariable("Path", "User")
}

# ── 1. git ──
Write-Host ""
Write-Host "■ 1/6  git 확인" -ForegroundColor Cyan
if (-not (HasGit)) { RefreshPath }
if (-not (HasGit)) {
  Write-Host "  git이 없어서 설치합니다. 권한을 묻는 창이 뜨면 '예'를 눌러 주세요. (3~5분)"
  winget install --id Git.Git -e --source winget --accept-source-agreements --accept-package-agreements
  RefreshPath
  if (-not (HasGit)) {
    Write-Host "  설치는 됐지만 이 창에서는 아직 인식되지 않아요." -ForegroundColor Yellow
    Write-Host "  이 창을 닫고 'GitHub 올리기.bat'을 한 번만 더 실행해 주세요." -ForegroundColor Yellow
    Read-Host "엔터를 누르면 닫혀요"; exit 0
  }
}
Write-Host ("  " + (git --version)) -ForegroundColor Green

# ── 2. 저장소 연결 ──
Write-Host ""
Write-Host "■ 2/6  저장소 연결" -ForegroundColor Cyan
if (Test-Path -LiteralPath (Join-Path $repoDir ".git")) {
  Write-Host "  이미 연결돼 있어요. 최신 상태로 맞춥니다…"
  & git -C "$repoDir" pull --rebase 2>&1 | Out-Null
} else {
  Write-Host "  필요한 부분만 내려받는 중… (처음 한 번, 1분 이내)"
  & git clone --filter=blob:none --no-checkout --depth 1 "$url" "$repoDir" 2>&1 | Out-Null
  if (-not (Test-Path -LiteralPath (Join-Path $repoDir ".git"))) {
    Write-Host "  내려받기에 실패했어요. 인터넷 연결을 확인하고 다시 실행해 주세요." -ForegroundColor Red
    Read-Host "엔터를 누르면 닫혀요"; exit 1
  }
  & git -C "$repoDir" sparse-checkout set "올리기/전사본" 2>&1 | Out-Null
  & git -C "$repoDir" checkout main 2>&1 | Out-Null
  & git -C "$repoDir" config user.name "seohoe1031" 2>&1 | Out-Null
  & git -C "$repoDir" config user.email "1031seohoe@users.noreply.github.com" 2>&1 | Out-Null
}
$target = Join-Path $repoDir "올리기\전사본"
if (-not (Test-Path -LiteralPath $target)) { New-Item -ItemType Directory -Force -Path $target | Out-Null }
Write-Host "  연결됨" -ForegroundColor Green

# ── 3. 전사본 모으기 ──
Write-Host ""
Write-Host "■ 3/6  전사본 모으기" -ForegroundColor Cyan
$roots = New-Object System.Collections.ArrayList
if (Test-Path -LiteralPath $mine) { [void]$roots.Add($mine) }
[void]$roots.Add($here)
if ($Items) { foreach ($i in $Items) { if (Test-Path -LiteralPath $i -PathType Container) { [void]$roots.Add((Get-Item -LiteralPath $i).FullName) } } }

# 전사본 폴더 하나 = 녹음 하나. 저장소에 올릴 이름(날짜가 없으면 녹음 날짜를 붙임)을 정해 둔다.
$jobs = New-Object System.Collections.ArrayList
foreach ($root in ($roots | Sort-Object -Unique)) {
  foreach ($d in @(Get-ChildItem -LiteralPath $root -Directory -ErrorAction SilentlyContinue | Where-Object { $skip -notcontains $_.Name })) {
    $srts = @(Get-ChildItem -LiteralPath $d.FullName -Filter "*.srt" -ErrorAction SilentlyContinue)
    if ($srts.Count -eq 0) { continue }
    $day = RecDate $d
    $name = $d.Name
    if (-not (HasDate $name)) { $name = $day.ToString("MMdd") + "_" + $name }
    [void]$jobs.Add([pscustomobject]@{ Dir = $d; Name = $name; Day = $day; Srts = $srts; Dest = (Join-Path $target $name) })
  }
}

$copied = 0; $already = 0; $folders = New-Object System.Collections.ArrayList
foreach ($j in $jobs) {
  if (-not (Test-Path -LiteralPath $j.Dest)) { New-Item -ItemType Directory -Force -Path $j.Dest | Out-Null }
  $new = 0
  foreach ($f in $j.Srts) {
    $to = Join-Path $j.Dest $f.Name
    if ((Test-Path -LiteralPath $to) -and ((Get-Item -LiteralPath $to).Length -eq $f.Length)) { $already++; continue }
    Copy-Item -LiteralPath $f.FullName -Destination $to -Force
    $copied++; $new++
  }
  if ($new -gt 0) {
    $note = $(if ($j.Name -ne $j.Dir.Name) { "  (날짜를 붙여 " + $j.Name + " 로 올림)" } else { "" })
    Write-Host ("  + " + $j.Dir.Name + " (" + $new + "개)" + $note) -ForegroundColor Green
    [void]$folders.Add($j.Name)
  }
}
if ($copied -eq 0) {
  if ($already -gt 0) { Write-Host ("  새로 올릴 전사본이 없어요. 이미 올라간 전사본 " + $already + "개를 확인했어요.") -ForegroundColor DarkGray }
  else {
    Write-Host "  올릴 전사본(.srt)을 찾지 못했어요." -ForegroundColor Yellow
    Write-Host "  'KNUTS 전사.bat'으로 먼저 전사하거나, 전사본이 든 폴더를 이 파일 위에 끌어다 놓아 주세요."
  }
}

# ── 4. 강의 음성(MP3)을 GitHub 릴리스로 ──
# 음성을 먼저 올리고, 어느 전사본이 어느 MP3인지 _음성.json 에 적어 전사본과 같이 올린다.
Write-Host ""
Write-Host "■ 4/6  강의 음성 올리기" -ForegroundColor Cyan
$audioWritten = 0
try {
  $withMp3 = @($jobs | Where-Object { @(Get-ChildItem -LiteralPath $_.Dir.FullName -Filter "*.mp3" -ErrorAction SilentlyContinue).Count -gt 0 })
  if ($withMp3.Count -eq 0) {
    Write-Host "  올릴 음성이 없어요." -ForegroundColor DarkGray
  } else {
    $all = @($withMp3 | ForEach-Object { Get-ChildItem -LiteralPath $_.Dir.FullName -Filter "*.mp3" })
    Write-Host ("  음성 " + $all.Count + "개 (" + [math]::Round(($all | Measure-Object -Property Length -Sum).Sum / 1MB) + "MB)")
    $gh = Get-Command gh -ErrorAction SilentlyContinue
    if (-not $gh) { RefreshPath; $gh = Get-Command gh -ErrorAction SilentlyContinue }
    if (-not $gh) {
      Write-Host "  GitHub CLI를 설치합니다. 권한을 묻는 창이 뜨면 '예'를 눌러 주세요."
      winget install --id GitHub.cli -e --source winget --accept-source-agreements --accept-package-agreements
      RefreshPath
      $gh = Get-Command gh -ErrorAction SilentlyContinue
    }
    if (-not $gh) {
      Write-Host "  GitHub CLI가 없어 음성 올리기를 건너뜁니다. 창을 닫고 다시 실행해 주세요." -ForegroundColor Yellow
    } else {
      & gh auth status 2>&1 | Out-Null
      if ($LASTEXITCODE -ne 0) {
        Write-Host "  GitHub 로그인이 필요해요. 브라우저가 열립니다. (처음 한 번)" -ForegroundColor Yellow
        & gh auth login --hostname github.com --git-protocol https --web
      }
      & gh auth status 2>&1 | Out-Null
      if ($LASTEXITCODE -ne 0) {
        Write-Host "  로그인이 안 돼서 음성 올리기를 건너뜁니다." -ForegroundColor Yellow
      } else {
        $full = (& git -C "$repoDir" remote get-url origin) -replace '\.git$', '' -replace '^.*github\.com[:/]', ''
        if (-not $full) { $full = "seohoe1031/Classification-of-Past-Exam" }
        & gh release view $TAG --repo $full 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
          & gh release create $TAG --repo $full --title "강의 음성" --notes "강의 녹음을 전사용으로 줄인 MP3(모노 16kHz). 파일 이름은 녹음날짜_폴더_조각번호입니다. 앱 전사본 화면에서 문장을 누르면 이 녹음이 그 자리부터 재생됩니다." 2>&1 | Out-Null
        }
        # 릴리스에 이미 있는 파일 (이름 → 크기). 같은 이름을 덮어쓰지 않기 위해
        $have = @{}
        foreach ($line in @(& gh release view $TAG --repo $full --json assets --jq '.assets[] | [.name, .size] | @tsv' 2>$null)) {
          $q = $line -split "`t"; if ($q.Count -eq 2) { $have[$q[0]] = [int64]$q[1] }
        }
        $tmp = Join-Path $env:TEMP "knuts-audio"
        if (Test-Path -LiteralPath $tmp) { Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue }
        New-Item -ItemType Directory -Force -Path $tmp | Out-Null
        $up = 0
        foreach ($j in $withMp3) {
          $plain = ($j.Name -replace '[^0-9A-Za-z._-]', '').Trim('._-')
          $plain = $plain -replace '^\d{4}_', ''   # 폴더 이름 앞 날짜(1127_)는 아래 녹음 날짜와 겹치므로 뺀다
          if (-not $plain) { $plain = 'audio' }
          $stem0 = $j.Day.ToString("yyyyMMdd") + "_" + $plain
          $man = Join-Path $j.Dest "_음성.json"
          $map = [ordered]@{}
          if (Test-Path -LiteralPath $man) {
            try { $old = Get-Content -LiteralPath $man -Raw -Encoding UTF8 | ConvertFrom-Json; foreach ($pp in $old.parts.PSObject.Properties) { $map[$pp.Name] = $pp.Value } } catch { }
          }
          foreach ($f in @(Get-ChildItem -LiteralPath $j.Dir.FullName -Filter "*.mp3" | Sort-Object Name)) {
            $m = [regex]::Match($f.BaseName, '_part(\d+)$')
            $pn = $(if ($m.Success) { $m.Groups[1].Value } else { "00" })
            # 같은 이름이 있으면: 크기가 같으면 이미 올라간 것, 다르면 _2, _3 … 을 붙인다 (덮어쓰지 않음)
            $assetName = $stem0 + "_p" + $pn + ".mp3"; $k = 1; $done = $false
            while ($have.ContainsKey($assetName)) {
              if ($have[$assetName] -eq $f.Length) { $done = $true; break }
              $k++; $assetName = $stem0 + "_" + $k + "_p" + $pn + ".mp3"
            }
            if (-not $done) {
              $asset = Join-Path $tmp $assetName
              Copy-Item -LiteralPath $f.FullName -Destination $asset -Force
              & gh release upload $TAG "$asset" --repo $full 2>&1 | Out-Null
              $done = ($LASTEXITCODE -eq 0)
              Remove-Item -LiteralPath $asset -Force -ErrorAction SilentlyContinue
              if ($done) { $have[$assetName] = $f.Length; $up++; Write-Host ("  + " + $assetName) -ForegroundColor Green }
              else { Write-Host ("  ! " + $f.Name + " 올리기 실패 — 다음에 다시 실행하면 이어서 올려요") -ForegroundColor Yellow }
            } else {
              Write-Host ("  = " + $assetName + " (이미 올라가 있음)") -ForegroundColor DarkGray
            }
            if ($done) {
              $map[$f.BaseName] = $assetName   # 전사본 조각(…_part00.srt)과 같은 이름
              if ($DeleteLocalMp3) { Remove-Item -LiteralPath $f.FullName -Force -ErrorAction SilentlyContinue }
            }
          }
          if ($map.Count -gt 0) {
            $json = [ordered]@{ tag = $TAG; parts = $map } | ConvertTo-Json -Depth 4
            WriteUtf8 $man $json
            $audioWritten++
          }
        }
        Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
        Say ("  음성 " + $up + "개 올림" + $(if ($DeleteLocalMp3 -and $up -gt 0) { " (노트북의 MP3는 지웠어요 — 원본 녹화본은 그대로예요)" } else { "" })) Green
        Write-Host ("  https://github.com/" + $full + "/releases/tag/" + $TAG)
      }
    }
  }
} catch {
  Write-Host ("  음성 올리기 중 문제가 생겼어요: " + $_.Exception.Message) -ForegroundColor Yellow
}

# ── 5. 전사본(+ 음성 연결 정보) 올리기 ──
Write-Host ""
Write-Host "■ 5/6  GitHub에 올리기" -ForegroundColor Cyan
& git -C "$repoDir" add -A 2>&1 | Out-Null
& git -C "$repoDir" diff --cached --quiet 2>&1 | Out-Null
if ($LASTEXITCODE -eq 0) {
  Write-Host "  올릴 게 없어서 건너뜁니다." -ForegroundColor DarkGray
  $pushed = $true
} else {
  Write-Host "  처음이면 브라우저가 열리며 GitHub 로그인을 물어볼 수 있어요. 한 번만 하면 됩니다."
  $what = ($folders | Sort-Object -Unique) -join ", "
  if (-not $what) { $what = "음성 연결" }
  & git -C "$repoDir" commit -m ("전사본 추가 " + (Get-Date -Format "yyyy-MM-dd") + " — " + $what) 2>&1 | Out-Null
  & git -C "$repoDir" pull --rebase 2>&1 | Out-Null
  $out = (& git -C "$repoDir" push 2>&1) -join " "
  if ($LASTEXITCODE -eq 0) {
    $pushed = $true
    Write-Host ("  올리기 완료 — 전사본 " + $copied + "개" + $(if ($audioWritten -gt 0) { ", 음성 연결 " + $audioWritten + "개" } else { "" })) -ForegroundColor Green
    Write-Host ""
    Write-Host "  다음: 앱의 '인체감염학' 화면에서 「내 Claude로 전사본 정리」를 누르세요."
    Write-Host "  https://github.com/seohoe1031/Classification-of-Past-Exam/tree/main/%EC%98%AC%EB%A6%AC%EA%B8%B0/%EC%A0%84%EC%82%AC%EB%B3%B8"
  } else {
    Write-Host ("  올리기 실패 — " + $out) -ForegroundColor Yellow
    Write-Host "  인터넷이나 GitHub 로그인을 확인하고 다시 실행해 주세요. 복사해 둔 파일은 그대로 있어요."
  }
}

# ── 6. 노트북 비우기 ──
Write-Host ""
Write-Host "■ 6/6  노트북 비우기" -ForegroundColor Cyan
if (-not $CleanLocal) {
  Write-Host "  설정에서 꺼 두셨어요 (CleanLocal)." -ForegroundColor DarkGray
} elseif (-not $pushed) {
  Write-Host "  올리기가 끝나지 않아서 아무것도 지우지 않았어요." -ForegroundColor Yellow
} else {
  $freed = 0; $gone = 0
  foreach ($j in $jobs) {
    $d = $j.Dir
    if (@(Get-ChildItem -LiteralPath $d.FullName -Filter "*.mp3" -ErrorAction SilentlyContinue).Count -gt 0) {
      Write-Host ("  " + $d.Name + " — 음성이 아직 안 올라가서 그대로 둡니다.") -ForegroundColor Yellow
      continue
    }
    # 저장소에 같은 이름으로 올라간 게 있는지 확인하고 지웁니다
    $safe = $true
    if (-not ($folders -contains $j.Name)) {
      foreach ($f in $j.Srts) { if (-not (Test-Path -LiteralPath (Join-Path $j.Dest $f.Name))) { $safe = $false } }
    }
    if (-not $safe) {
      Write-Host ("  " + $d.Name + " — 저장소에서 확인이 안 돼 그대로 둡니다.") -ForegroundColor Yellow
      continue
    }
    # 전사에 쓴 원본 MP3: 이 녹음의 음성이 모두 GitHub에 올라간 게 _음성.json 으로 확인될 때만 지운다
    $mark = Join-Path $d.FullName "_원본.txt"
    if ($DeleteSourceMp3 -and (Test-Path -LiteralPath $mark)) {
      $src = (Get-Content -LiteralPath $mark -Raw -Encoding UTF8).Trim()
      if ($src -and $src -match '\.mp3$' -and (Test-Path -LiteralPath $src)) {
        $ok = $false
        $man = Join-Path $j.Dest "_음성.json"
        if (Test-Path -LiteralPath $man) {
          try {
            $pp = (Get-Content -LiteralPath $man -Raw -Encoding UTF8 | ConvertFrom-Json).parts
            $ok = $true
            foreach ($f in $j.Srts) { if (-not $pp.PSObject.Properties[$f.BaseName]) { $ok = $false } }
          } catch { $ok = $false }
        }
        if ($ok) {
          $freed += (Get-Item -LiteralPath $src).Length
          Remove-Item -LiteralPath $src -Force -ErrorAction SilentlyContinue
          Write-Host ("  - " + [System.IO.Path]::GetFileName($src) + " (전사에 쓴 MP3 — GitHub에 음성 있음)") -ForegroundColor DarkGray
        } else {
          Write-Host ("  " + [System.IO.Path]::GetFileName($src) + " — GitHub에 음성이 확인되지 않아 원본 MP3는 남겨 둡니다.") -ForegroundColor Yellow
        }
      }
    }
    foreach ($f in $j.Srts) { $freed += $f.Length; Remove-Item -LiteralPath $f.FullName -Force -ErrorAction SilentlyContinue }
    Remove-Item -LiteralPath $mark -Force -ErrorAction SilentlyContinue
    if (@(Get-ChildItem -LiteralPath $d.FullName -Force -ErrorAction SilentlyContinue).Count -eq 0) {
      Remove-Item -LiteralPath $d.FullName -Force -ErrorAction SilentlyContinue
    }
    $gone++
  }
  if ($gone -eq 0) {
    Write-Host "  비울 게 없어요." -ForegroundColor DarkGray
  } else {
    Say ("  " + $gone + "개 폴더를 비웠어요 (" + [math]::Round($freed / 1MB) + "MB 확보). 전사본과 음성은 GitHub에 있습니다.") Green
  }
}

Write-Host ""
Read-Host "엔터를 누르면 닫혀요"
