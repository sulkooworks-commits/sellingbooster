#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
merge_live.py — 라이브(저장소) index.html 의 '사용자 편집 콘텐츠'를 로컬 소스에 병합
사용자가 대시보드 편집모드로 추가·수정한 메뉴/사이트맵/수동 일정이
새 빌드 덮어쓰기로 사라지지 않도록, 모든 패치 작업 '이전에' 반드시 실행한다.

사용법:
  python3 merge_live.py                # 라이브 취득→복호화→diff 리포트 (dry-run)
  python3 merge_live.py --apply        # 차이가 있으면 index-source.html 에 병합 저장
  python3 merge_live.py --file X.html  # 네트워크 대신 파일 사용(암호화본/평문 모두 허용)

병합 블록 (라이브 → 로컬):
  1) 메뉴 카드 전체   : <div class="menu-cols"> … 균형 닫힘
  2) 사이트맵 컬럼    : 각 <div class="ck-sm-col"> … (있는 경우)
  3) 수동 일정 컬럼   : <div class="sched-col team"> … (팀원 업무 관리)
코드·기능(JS/CSS)은 로컬이 항상 최신 — 콘텐츠만 라이브 우선.
"""
import re, sys, json, base64, hashlib, urllib.request

PW   = "sulkoo2026"
RAW  = "https://raw.githubusercontent.com/sulkooworks-commits/sellingbooster/main/index.html"
SRC  = "index-source.html"

def fetch_live(path=None):
    if path:
        data = open(path, encoding="utf-8").read()
    else:
        req = urllib.request.Request(RAW + "?t=merge", headers={"Cache-Control": "no-store"})
        data = urllib.request.urlopen(req, timeout=20).read().decode("utf-8")
    m = re.search(r"var PAYLOAD = (\{.*?\});", data, re.DOTALL)
    if not m:
        return data  # 이미 평문
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    p = json.loads(m.group(1))
    key = hashlib.pbkdf2_hmac("sha256", PW.encode(), base64.b64decode(p["salt"]), p["iter"], 32)
    return AESGCM(key).decrypt(base64.b64decode(p["iv"]), base64.b64decode(p["ct"]), None).decode("utf-8")

def balanced_div(html, start_pat):
    """start_pat 위치의 <div …> 부터 균형 닫힘까지의 [start, end) 반환"""
    m = re.search(start_pat, html)
    if not m:
        return None
    i = m.start(); depth = 0; j = i
    for t in re.finditer(r"<div\b|</div>", html[i:]):
        depth += 1 if t.group(0) == "<div" else -1
        if depth == 0:
            j = i + t.end()
            return (i, j)
    return None

BLOCKS = [
    ("메뉴 카드(.menu-cols)",      r'<div class="menu-cols">'),
    ("수동 일정(.sched-col team)", r'<div class="sched-col team">'),
]

def sm_cols(html):
    """사이트맵 컬럼들: 각 ck-sm-col 블록 리스트"""
    out, pos = [], 0
    while True:
        m = re.search(r'<div class="ck-sm-col[^"]*">', html[pos:])
        if not m:
            break
        rng = balanced_div(html[pos:], re.escape(m.group(0)))
        if not rng:
            break
        out.append(html[pos + rng[0]:pos + rng[1]])
        pos += rng[1]
    return out

def scan_history(n=12):
    """최근 n개 커밋을 복호화해 HEAD 에 없는 카드(=덮어쓰기 유실 후보)를 보고"""
    import urllib.request as U
    h=U.urlopen("https://github.com/sulkooworks-commits/sellingbooster/commits/main/index.html",timeout=20).read().decode("utf-8","ignore")
    shas=[]
    for m in re.finditer(r"/sulkooworks-commits/sellingbooster/commit/([0-9a-f]{40})",h):
        if m.group(1) not in shas: shas.append(m.group(1))
    head=fetch_live()
    base=set(re.findall(r'<a class="card"[^>]*href="([^"]+)"',head))
    hit=False
    for s in shas[:n]:
        try:
            raw=U.urlopen(f"https://raw.githubusercontent.com/sulkooworks-commits/sellingbooster/{s}/index.html",timeout=20).read().decode("utf-8")
            plain=fetch_live.__wrapped__(raw) if False else None
        except Exception:
            continue
        try:
            m2=re.search(r"var PAYLOAD = (\{.*?\});",raw,re.DOTALL)
            import json as J,base64 as B,hashlib as H
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            p=J.loads(m2.group(1))
            key=H.pbkdf2_hmac("sha256",PW.encode(),B.b64decode(p["salt"]),p["iter"],32)
            plain=AESGCM(key).decrypt(B.b64decode(p["iv"]),B.b64decode(p["ct"]),None).decode()
        except Exception:
            continue
        extra=[(t.strip(),href) for href,t in re.findall(r'<a class="card"[^>]*href="([^"]+)"[^>]*>\s*<div class="t">([^<]*)</div>',plain) if href not in base]
        if extra:
            hit=True
            print(f"★ {s[:10]}: HEAD 에 없는 카드 → "+", ".join(f"{t}({h})" for t,h in extra))
    if not hit:
        print("✓ 최근 이력에 유실 카드 없음")

def main():
    if "--history" in sys.argv:
        scan_history(); return
    apply_ = "--apply" in sys.argv
    fpath = None
    if "--file" in sys.argv:
        fpath = sys.argv[sys.argv.index("--file") + 1]
    live = fetch_live(fpath)
    local = open(SRC, encoding="utf-8").read()
    if live == local:
        print("✓ 라이브 == 로컬 (완전 동일) — 병합 불필요")
        return
    changed = False
    for name, pat in BLOCKS:
        lr, cr = balanced_div(live, pat), balanced_div(local, pat)
        if not lr or not cr:
            print(f"⚠ {name}: 앵커 미발견(라이브 {bool(lr)}/로컬 {bool(cr)}) — 수동 확인 필요")
            continue
        lb, cb = live[lr[0]:lr[1]], local[cr[0]:cr[1]]
        if lb == cb:
            print(f"· {name}: 동일")
            continue
        # 카드 href 목록으로 요약 diff
        lh = set(re.findall(r'href="([^"]+)"', lb))
        ch = set(re.findall(r'href="([^"]+)"', cb))
        print(f"≠ {name}: 라이브에만 {sorted(lh - ch) or '—'} / 로컬에만 {sorted(ch - lh) or '—'}")
        if apply_:
            local = local[:cr[0]] + lb + local[cr[1]:]
            changed = True
    # 사이트맵 컬럼: 라이브 세트로 통째 교체(순서 포함)
    ls, cs = sm_cols(live), sm_cols(local)
    if ls and cs and "".join(ls) != "".join(cs):
        print(f"≠ 사이트맵(ck-sm-col): 라이브 {len(ls)}열 ↔ 로컬 {len(cs)}열 — 라이브 우선")
        if apply_:
            joined_c = "".join(cs)
            idx = local.find(cs[0])
            end = local.find(cs[-1]) + len(cs[-1])
            local = local[:idx] + "".join(ls) + local[end:]
            changed = True
    elif ls:
        print("· 사이트맵: 동일")
    if apply_ and changed:
        open(SRC, "w", encoding="utf-8").write(local)
        print("→ index-source.html 병합 저장 완료 (이후 LOCK 재동기화 + 재암호화 필수)")
    elif not apply_:
        print("(dry-run — 적용하려면 --apply)")

if __name__ == "__main__":
    main()
