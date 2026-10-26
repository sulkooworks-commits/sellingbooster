# -*- coding: utf-8 -*-
"""다이소몰 검색창 플로팅 레이어 — 추천 검색어 / 급상승 검색어 수집기

화면: https://www.daisomall.co.kr  상단 검색창 클릭 시 열리는 레이어
  - 추천 검색어 (이미지 칩 6개 내외, 운영자 큐레이션)
  - 급상승 검색어 ("최근 1시간, 검색횟수 급상승", 10건 × 2페이지 = 20건)

실제 데이터 API (사이트 프론트 코드에서 호출부 확인, 로그인·쿠키 불필요)
  추천:   POST https://fapi.daisomall.co.kr/ds/dsl/selRcmKeywd   body {"mallSeCd": "01"}
          → data[] : rcmKeywdNm(검색어) · dispOrdr(노출순서) · pdNo · imgUrl(/file/... → cdn.daisomall.co.kr)
                     exhStDtm/exhEdDtm(노출기간)
          ※ mallSeCd 01 = 메인 검색 레이어(화면과 일치 확인). body 없이 호출하면 01·02·03 전체가 섞여 옴
  급상승: GET  https://www.daisomall.co.kr/ssn/search/trendSearch?rank=20&mallId=MALL_MAIN
          → resultSet.result[0].resultDocuments[] : rank · keyword · PRERANK · RANKING_GAP · SUMMED_GAP
          ※ result[1]·[2] 도 함께 오지만 메인 레이어는 result[0] 만 사용(사이트 코드 기준)
          배지 판정(사이트 코드 그대로):  ▲ = PRERANK>0 and RANKING_GAP<0 /  N = PRERANK==0 and RANKING_GAP>0

단독 실행 (개발자 확인용)
  pip install requests
  python daiso_search_keywords.py                       # 추천+급상승 → out/ 폴더
  python daiso_search_keywords.py --sections rising     # 급상승만
  python daiso_search_keywords.py --engine browser      # 차단 시 Playwright (pip install playwright && playwright install chromium)

크롤러 허브(_runner.py)는 collect(params) 를 호출함.
robots.txt: User-agent * Crawl-delay 30 — 1회 실행 2건 요청이라 기본 간격 2초로 충분, 연속 실행은 피할 것.
"""
import argparse
import csv
import json
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import quote

PAGE = "https://www.daisomall.co.kr/ds/dst/SCR_DST_0015?searchTerm="
RCM_API = "https://fapi.daisomall.co.kr/ds/dsl/selRcmKeywd"
TREND_API = "https://www.daisomall.co.kr/ssn/search/trendSearch?rank={rank}&mallId=MALL_MAIN"
IMG_HOST = "https://cdn.daisomall.co.kr"
SECTIONS = {"recommend": "추천", "rising": "급상승"}
KST = timezone(timedelta(hours=9))
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": "https://www.daisomall.co.kr/",
    "Origin": "https://www.daisomall.co.kr",
}
COLUMNS = ["collected_at", "section", "rank", "keyword", "change_type", "prev_rank",
           "ranking_gap", "summed_gap", "pd_no", "image_url", "exhibit_period", "search_url"]


# ── 엔진 1: requests ────────────────────────────────────────────────
def req(method: str, url: str, body=None, retries: int = 3):
    import requests
    last = None
    for i in range(retries):
        try:
            if method == "POST":
                r = requests.post(url, json=body or {}, headers=HEADERS, timeout=15)
            else:
                r = requests.get(url, headers=HEADERS, timeout=15)
            if r.status_code == 200:
                return r.json()
            last = f"HTTP {r.status_code}"
            if r.status_code in (403, 429):
                break
        except Exception as e:  # noqa
            last = repr(e)
        time.sleep(2 * (i + 1))
    raise RuntimeError(f"requests 실패: {last}")


# ── 엔진 2: Playwright (실제 페이지 안에서 fetch) ─────────────────────
class BrowserFetcher:
    def __init__(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=True)
        self._page = self._browser.new_page(locale="ko-KR")
        self._page.goto("https://www.daisomall.co.kr/", wait_until="domcontentloaded", timeout=60000)

    def fetch(self, method: str, url: str, body=None):
        return self._page.evaluate(
            """async ([m, u, b]) => {
                 const opt = m === 'POST' ? {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(b || {})} : {};
                 const r = await fetch(u, opt);
                 if (!r.ok) throw new Error('HTTP ' + r.status);
                 return await r.json();
               }""", [method, url, body])

    def close(self):
        try:
            self._browser.close()
            self._pw.stop()
        except Exception:
            pass


def search_url(kw: str) -> str:
    return PAGE + quote(kw)


def _int(v, default=0):
    try:
        return int(str(v).strip())
    except Exception:
        return default


# ── 파싱 ────────────────────────────────────────────────────────────
def parse_recommend(payload: dict, collected_at: str) -> list:
    items = [d for d in (payload.get("data") or []) if str(d.get("mallSeCd", "01")) == "01"]
    items.sort(key=lambda d: _int(d.get("dispOrdr"), 99))
    rows = []
    for i, d in enumerate(items, 1):
        kw = d.get("rcmKeywdNm", "")
        img = d.get("imgUrl") or ""
        rows.append({
            "collected_at": collected_at, "section": "추천", "rank": i, "keyword": kw,
            "change_type": "", "prev_rank": "", "ranking_gap": "", "summed_gap": "",
            "pd_no": d.get("pdNo", ""),
            "image_url": (IMG_HOST + img) if img.startswith("/") else img,
            "exhibit_period": f"{(d.get('exhStDtm') or '')[:10]} ~ {(d.get('exhEdDtm') or '')[:10]}",
            "search_url": search_url(kw),
        })
    return rows


def parse_rising(payload: dict, collected_at: str) -> list:
    result = ((payload.get("resultSet") or {}).get("result") or [{}])[0]
    rows = []
    for d in result.get("resultDocuments") or []:
        pre, gap = _int(d.get("PRERANK")), _int(d.get("RANKING_GAP"))
        if pre > 0 and gap < 0:
            change = "UP"
        elif pre == 0 and gap > 0:
            change = "NEW"
        else:
            change = "NONE"
        kw = d.get("keyword", "")
        rows.append({
            "collected_at": collected_at, "section": "급상승", "rank": _int(d.get("rank")), "keyword": kw,
            "change_type": change, "prev_rank": pre if pre > 0 else "",
            "ranking_gap": gap, "summed_gap": _int(d.get("SUMMED_GAP")),
            "pd_no": "", "image_url": "", "exhibit_period": "",
            "search_url": search_url(kw),
        })
    rows.sort(key=lambda r: r["rank"])
    return rows


# ── 수집 본체 (허브 러너 · 단독 실행 공용) ───────────────────────────
def collect(params: dict = None) -> dict:
    """params: {"sections": ["recommend","rising"], "rank": 20, "engine": "auto|requests|browser", "delay": 2}
    반환: {"columns": [...], "rows": [...], "meta": {...}, "raw": {...}}
    """
    p = params or {}
    sections = [s for s in (p.get("sections") or list(SECTIONS)) if s in SECTIONS] or list(SECTIONS)
    rank = max(1, min(_int(p.get("rank"), 20), 20))
    engine = p.get("engine", "auto")
    delay = float(p.get("delay", 2))

    collected_at = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
    rows, raw, log = [], {}, []
    browser = None
    used = None

    def get(method, url, body=None):
        nonlocal browser, used
        if engine in ("auto", "requests") and browser is None:
            try:
                data = req(method, url, body)
                used = used or "requests"
                return data
            except Exception as e:
                if engine == "requests":
                    raise
                log.append(f"requests 실패 → browser 전환: {e}")
        if browser is None:
            browser = BrowserFetcher()
        used = "browser"
        return browser.fetch(method, url, body)

    try:
        for i, sec in enumerate(sections):
            if i:
                time.sleep(delay)
            if sec == "recommend":
                payload = get("POST", RCM_API, {"mallSeCd": "01"})
                part = parse_recommend(payload, collected_at)
            else:
                payload = get("GET", TREND_API.format(rank=rank))
                part = parse_rising(payload, collected_at)
            raw[sec] = payload
            rows.extend(part)
            log.append(f"[{SECTIONS[sec]}] {len(part)}건: {', '.join(r['keyword'] for r in part[:6])}")
    finally:
        if browser:
            browser.close()

    return {
        "columns": COLUMNS,
        "rows": rows,
        "meta": {"collected_at": collected_at, "engine": used,
                 "params": {"sections": sections, "rank": rank},
                 "requests": len(sections), "log": log},
        "raw": raw,
    }


# ── 단독 실행: out/ 폴더에 CSV(월별 누적) + JSON 스냅샷 ──────────────
def main():
    ap = argparse.ArgumentParser(description="다이소몰 추천/급상승 검색어 수집")
    ap.add_argument("--sections", nargs="+", choices=list(SECTIONS), default=list(SECTIONS))
    ap.add_argument("--rank", type=int, default=20, help="급상승 수집 건수 (최대 20)")
    ap.add_argument("--engine", choices=["auto", "requests", "browser"], default="auto")
    ap.add_argument("--out", default="out")
    args = ap.parse_args()

    res = collect({"sections": args.sections, "rank": args.rank, "engine": args.engine})
    for line in res["meta"]["log"]:
        print(line)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(KST)
    csv_path = out / f"daiso_search_keywords_{stamp:%Y-%m}.csv"
    new = not csv_path.exists()
    with csv_path.open("a", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        if new:
            w.writeheader()
        w.writerows(res["rows"])
    snap = out / "snapshots"
    snap.mkdir(exist_ok=True)
    sp = snap / f"daiso_{stamp:%Y%m%d_%H%M}.json"
    sp.write_text(json.dumps(res["raw"], ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n엔진: {res['meta']['engine']} / 저장: {csv_path} (+{len(res['rows'])}행) / {sp}")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:
        print(e, file=sys.stderr)
        sys.exit(1)
