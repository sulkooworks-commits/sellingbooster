# -*- coding: utf-8 -*-
"""올리브영 급상승 검색어 수집기

화면: https://www.oliveyoung.co.kr/store/main/main.do  상단 중앙 검색창 클릭 시 레이어 우측 「급상승 검색어」
      (10위 노출, ▲/NEW/-, "HH:M0 기준")

실제 데이터 API (사이트 search.js 의 MainSuddenKeyword() 호출부 그대로, 로그인·쿠키 불필요)
  GET https://www.oliveyoung.co.kr/search/api/v1/common/popular-keywords?size=100
  → data.dateTime(UTC, 랭킹 기준시각) · data.items[] : rank · id(검색어) · searchTerm · rankDiff · count · countDiff
  화면은 상위 10건만 노출, API는 100건까지 반환
  변동 판정(사이트 getRankingDiff() 그대로): rankDiff 없음 → NEW / 0 → 변동 없음(-) / ≥1 → ▲ / 그 외 → ▼
  기준시각 표기(사이트 그대로): KST 시:분, 분은 10분 단위 내림 (예 16:57 → 16:50)
  검색 링크: https://www.oliveyoung.co.kr/store/search/getSearchMain.do?query=<검색어>

단독 실행 (개발자 확인용)
  pip install requests
  python oliveyoung_rising_keywords.py               # 100건 → out/ 폴더
  python oliveyoung_rising_keywords.py --size 10     # 화면과 같은 10건만
  python oliveyoung_rising_keywords.py --engine browser
      # Cloudflare 차단 시 Playwright (pip install playwright && playwright install chromium)

크롤러 허브(_runner.py)는 collect(params) 를 호출함.
robots.txt: User-agent * 는 Disallow: / — 내부 참고용 소량 호출(1회 1건). 서비스 기능으로 상업 활용 시 약관 확인 필요.
"""
import argparse
import csv
import json
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import quote

API = "https://www.oliveyoung.co.kr/search/api/v1/common/popular-keywords?size={size}"
PAGE = "https://www.oliveyoung.co.kr/store/main/main.do?oy=0"
SEARCH = "https://www.oliveyoung.co.kr/store/search/getSearchMain.do?query="
KST = timezone(timedelta(hours=9))
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": PAGE,
    "X-Requested-With": "XMLHttpRequest",
}
COLUMNS = ["collected_at", "ranking_base_time", "rank", "keyword", "change_type", "rank_diff",
           "search_count", "count_diff", "search_url"]


def fetch_requests(url: str, retries: int = 3) -> dict:
    import requests
    last = None
    for i in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.status_code == 200 and "application/json" in r.headers.get("content-type", ""):
                return r.json()
            last = f"HTTP {r.status_code} ({r.headers.get('content-type', '')})"
            if r.status_code in (403, 429, 503):
                break  # Cloudflare 차단 가능성 → browser 엔진
        except Exception as e:  # noqa
            last = repr(e)
        time.sleep(2 * (i + 1))
    raise RuntimeError(f"requests 실패: {last}")


def fetch_browser(url: str) -> dict:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        try:
            pg = b.new_page(locale="ko-KR")
            pg.goto(PAGE, wait_until="domcontentloaded", timeout=60000)
            return pg.evaluate("async (u) => { const r = await fetch(u, {headers:{'X-Requested-With':'XMLHttpRequest'}}); "
                               "if (!r.ok) throw new Error('HTTP ' + r.status); return await r.json(); }", url)
        finally:
            b.close()


def base_time(dt_str: str) -> str:
    """'2026-10-26T07:50:13.501+0000' → '2026-10-26 16:50' (사이트처럼 분 10단위 내림)"""
    if not dt_str:
        return ""
    try:
        dt = datetime.strptime(dt_str[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc).astimezone(KST)
        return dt.replace(minute=dt.minute // 10 * 10).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return dt_str


def to_rows(payload: dict, collected_at: str) -> list:
    data = payload.get("data") or {}
    bt = base_time(data.get("dateTime", ""))
    rows = []
    for d in data.get("items") or []:
        kw = d.get("id") or d.get("searchTerm") or ""
        if not kw:
            continue
        diff = d.get("rankDiff")
        if diff is None or str(diff).strip() == "":
            change, diff_v = "NEW", ""
        else:
            diff_v = int(diff)
            change = "NONE" if diff_v == 0 else ("UP" if diff_v >= 1 else "DOWN")
        rows.append({
            "collected_at": collected_at, "ranking_base_time": bt, "rank": int(d.get("rank") or 0),
            "keyword": kw, "change_type": change, "rank_diff": diff_v,
            "search_count": d.get("count", ""), "count_diff": d.get("countDiff", ""),
            "search_url": SEARCH + quote(kw),
        })
    rows.sort(key=lambda r: r["rank"])
    return rows


def collect(params: dict = None) -> dict:
    """params: {"size": "100"|"10", "engine": "auto|requests|browser"}  반환: {"columns","rows","meta","raw"}"""
    p = params or {}
    try:
        size = max(1, min(int(p.get("size") or 100), 100))
    except Exception:
        size = 100
    engine = p.get("engine", "auto")
    url = API.format(size=size)
    collected_at = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
    log, used = [], "requests"
    if engine == "browser":
        payload, used = fetch_browser(url), "browser"
    else:
        try:
            payload = fetch_requests(url)
        except Exception as e:
            if engine == "requests":
                raise
            log.append(f"requests 실패 → browser 전환: {e}")
            payload, used = fetch_browser(url), "browser"
    rows = to_rows(payload, collected_at)
    log.append(f"[급상승] {len(rows)}건 (기준 {rows[0]['ranking_base_time'] if rows else '-'}): "
               f"{', '.join(r['keyword'] for r in rows[:5])}")
    return {
        "columns": COLUMNS, "rows": rows,
        "meta": {"collected_at": collected_at, "engine": used, "params": {"size": size}, "requests": 1, "log": log},
        "raw": payload,
    }


def main():
    ap = argparse.ArgumentParser(description="올리브영 급상승 검색어 수집")
    ap.add_argument("--size", type=int, default=100, help="수집 건수 (최대 100, 화면 노출은 10)")
    ap.add_argument("--engine", choices=["auto", "requests", "browser"], default="auto")
    ap.add_argument("--out", default="out")
    args = ap.parse_args()
    res = collect({"size": args.size, "engine": args.engine})
    for line in res["meta"]["log"]:
        print(line)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(KST)
    csv_path = out / f"oliveyoung_rising_keywords_{stamp:%Y-%m}.csv"
    new = not csv_path.exists()
    with csv_path.open("a", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        if new:
            w.writeheader()
        w.writerows(res["rows"])
    snap = out / "snapshots"
    snap.mkdir(exist_ok=True)
    sp = snap / f"oliveyoung_{stamp:%Y%m%d_%H%M}.json"
    sp.write_text(json.dumps(res["raw"], ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n엔진: {res['meta']['engine']} / 저장: {csv_path} (+{len(res['rows'])}행) / {sp}")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:
        print(e, file=sys.stderr)
        sys.exit(1)
