# -*- coding: utf-8 -*-
"""오늘의집 인기 검색어 수집기

화면: https://store.ohou.se/ranks  우측 상단 「인기 검색어」 플로팅 창 (10위, ▲/▼/NEW)

실제 데이터 (로그인·쿠키 불필요, 화면 10건과 일치 확인)
  1순위  GET https://store.ohou.se/api/navigation           (JSON 약 30KB)
         → nav.trendingKeywords[] : rank · displayKeyword(화면 표기) · key(공백 제거) · isNew · diffRank
  2순위  GET https://store.ohou.se/ranks  HTML 의 __NEXT_DATA__
         → props.pageProps.dehydratedState.queries[queryKey=["navigation"]].state.data.nav.trendingKeywords
         (페이지 SSR 원본. 1순위 API 경로가 바뀌었을 때 대비)
  변동 판정: isNew → NEW / diffRank>0 → ▲ / diffRank<0 → ▼ / 그 외 변동 없음
  검색 링크: https://ohou.se/search/index?query=<displayKeyword>  (사이트 링크 형식 그대로)

단독 실행 (개발자 확인용)
  pip install requests
  python ohouse_trending_keywords.py                    # out/ 폴더에 CSV·스냅샷
  python ohouse_trending_keywords.py --engine browser   # 차단 시 Playwright (pip install playwright && playwright install chromium)

크롤러 허브(_runner.py)는 collect(params) 를 호출함.
robots.txt: User-agent * 는 Disallow: / — 내부 참고용 소량 호출(1회 1건). 서비스 기능으로 상업 활용 시 약관 확인 필요.
"""
import argparse
import csv
import json
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import quote

API = "https://store.ohou.se/api/navigation"
PAGE = "https://store.ohou.se/ranks"
SEARCH = "https://ohou.se/search/index?query="
KST = timezone(timedelta(hours=9))
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"),
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": PAGE,
}
COLUMNS = ["collected_at", "rank", "keyword", "search_key", "change_type", "diff_rank", "search_url"]


def _get(url: str, accept: str, retries: int = 3):
    import requests
    last = None
    for i in range(retries):
        try:
            r = requests.get(url, headers={**HEADERS, "Accept": accept}, timeout=20)
            if r.status_code == 200:
                return r
            last = f"HTTP {r.status_code}"
            if r.status_code in (403, 429):
                break
        except Exception as e:  # noqa
            last = repr(e)
        time.sleep(2 * (i + 1))
    raise RuntimeError(f"requests 실패({url}): {last}")


def trending_from_nav(data: dict) -> list:
    return ((data or {}).get("nav") or {}).get("trendingKeywords") or []


def trending_from_html(html: str) -> list:
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        raise RuntimeError("__NEXT_DATA__ 없음")
    nd = json.loads(m.group(1))
    for q in nd["props"]["pageProps"]["dehydratedState"]["queries"]:
        if q.get("queryKey") == ["navigation"]:
            return trending_from_nav(q["state"]["data"])
    raise RuntimeError("navigation 쿼리 없음")


# ── 엔진 1: requests (API → HTML 순) ────────────────────────────────
def fetch_requests(log: list) -> tuple:
    try:
        items = trending_from_nav(_get(API, "application/json").json())
        if items:
            return items, "api"
        log.append("API 응답에 trendingKeywords 없음 → HTML 파싱 시도")
    except Exception as e:
        log.append(f"API 실패 → HTML 파싱 시도: {e}")
    return trending_from_html(_get(PAGE, "text/html").text), "html"


# ── 엔진 2: Playwright (실제 페이지 안에서 fetch) ─────────────────────
def fetch_browser() -> tuple:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        try:
            pg = b.new_page(locale="ko-KR")
            pg.goto(PAGE, wait_until="domcontentloaded", timeout=60000)
            data = pg.evaluate("async () => { const r = await fetch('/api/navigation', {headers:{Accept:'application/json'}}); "
                               "if (!r.ok) throw new Error('HTTP ' + r.status); return await r.json(); }")
            items = trending_from_nav(data)
            if items:
                return items, "browser-api"
            return trending_from_html(pg.content()), "browser-html"
        finally:
            b.close()


def to_rows(items: list, collected_at: str) -> list:
    rows = []
    for d in items:
        diff = d.get("diffRank")
        try:
            diff = int(diff)
        except Exception:
            diff = 0
        if d.get("isNew"):
            change = "NEW"
        elif diff > 0:
            change = "UP"
        elif diff < 0:
            change = "DOWN"
        else:
            change = "NONE"
        kw = d.get("displayKeyword") or d.get("key") or ""
        rows.append({
            "collected_at": collected_at, "rank": int(d.get("rank") or 0), "keyword": kw,
            "search_key": d.get("key", ""), "change_type": change,
            "diff_rank": "" if d.get("isNew") else diff,
            "search_url": SEARCH + quote(kw),
        })
    rows.sort(key=lambda r: r["rank"])
    return rows


def collect(params: dict = None) -> dict:
    """params: {"engine": "auto|requests|browser"}  반환: {"columns","rows","meta","raw"}"""
    p = params or {}
    engine = p.get("engine", "auto")
    collected_at = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
    log = []
    if engine == "browser":
        items, src = fetch_browser()
    else:
        try:
            items, src = fetch_requests(log)
        except Exception as e:
            if engine == "requests":
                raise
            log.append(f"requests 실패 → browser 전환: {e}")
            items, src = fetch_browser()
    rows = to_rows(items, collected_at)
    log.append(f"[인기 검색어] {len(rows)}건 (출처 {src}): {', '.join(r['keyword'] for r in rows[:5])}")
    return {
        "columns": COLUMNS, "rows": rows,
        "meta": {"collected_at": collected_at, "engine": src, "params": {}, "requests": 1, "log": log},
        "raw": items,
    }


def main():
    ap = argparse.ArgumentParser(description="오늘의집 인기 검색어 수집")
    ap.add_argument("--engine", choices=["auto", "requests", "browser"], default="auto")
    ap.add_argument("--out", default="out")
    args = ap.parse_args()
    res = collect({"engine": args.engine})
    for line in res["meta"]["log"]:
        print(line)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(KST)
    csv_path = out / f"ohouse_trending_keywords_{stamp:%Y-%m}.csv"
    new = not csv_path.exists()
    with csv_path.open("a", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        if new:
            w.writeheader()
        w.writerows(res["rows"])
    snap = out / "snapshots"
    snap.mkdir(exist_ok=True)
    sp = snap / f"ohouse_{stamp:%Y%m%d_%H%M}.json"
    sp.write_text(json.dumps(res["raw"], ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n엔진: {res['meta']['engine']} / 저장: {csv_path} (+{len(res['rows'])}행) / {sp}")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:
        print(e, file=sys.stderr)
        sys.exit(1)
