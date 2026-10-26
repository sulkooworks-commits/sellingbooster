# -*- coding: utf-8 -*-
"""무신사 랭킹 > 검색어 (인기 / 급상승) 수집기

페이지: https://www.musinsa.com/main/musinsa/ranking?subPan=keyword
실제 데이터 API (페이지가 호출하는 것과 동일, 로그인·쿠키 불필요):
  https://client.musinsa.com/api/home/web/v5/pans/ranking
    ?sectionId=1067|2449 &gf=A|M|F &ageBand=AGE_BAND_ALL &storeCode=musinsa &subPan=keyword
  sectionId 1067 = 인기 (200건, 순위 변동 포함) / 2449 = 급상승 (약 126건, 변동 없음)
  응답: data.modules[] 중 type=RANKING_SEARCH 항목(rank / title.text / fluctuation / onClick.url),
        type=QUERY_UPDATEDAT 의 information.updatedAt = 랭킹 기준시각(KST 값을 UTC epoch처럼 내려줌)

단독 실행 (개발자 확인용)
  pip install requests
  python musinsa_keyword_ranking.py                   # 인기+급상승 × 성별 전체(A) → out/ 폴더
  python musinsa_keyword_ranking.py --gf A M F        # 성별 3종
  python musinsa_keyword_ranking.py --tabs popular    # 인기만
  python musinsa_keyword_ranking.py --engine browser  # requests가 차단(403)될 때 Playwright로 수집
                                                      # (pip install playwright && playwright install chromium)
  --engine auto(기본) = requests 시도 → 실패 시 Playwright 자동 전환

크롤러 허브(_runner.py)에서는 collect(params) 를 호출함 — 반환 형식은 아래 collect() 설명 참고.
"""
import argparse
import csv
import json
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

API = "https://client.musinsa.com/api/home/web/v5/pans/ranking"
PAGE = "https://www.musinsa.com/main/musinsa/ranking"
TABS = {"popular": ("1067", "인기"), "rising": ("2449", "급상승")}
GF_LABEL = {"A": "전체", "M": "남성", "F": "여성"}
KST = timezone(timedelta(hours=9))
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": PAGE,
    "Origin": "https://www.musinsa.com",
}
COLUMNS = ["collected_at", "ranking_updated_at", "tab", "section_id", "gender",
           "rank", "keyword", "change_type", "change_amount", "search_url"]


def build_url(section_id: str, gf: str) -> str:
    return (f"{API}?sectionId={section_id}&gf={gf}&ageBand=AGE_BAND_ALL"
            f"&storeCode=musinsa&subPan=keyword")


# ── 엔진 1: requests ────────────────────────────────────────────────
def fetch_requests(url: str, retries: int = 3) -> dict:
    import requests
    last = None
    for i in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.status_code == 200:
                return r.json()
            last = f"HTTP {r.status_code}"
            if r.status_code in (403, 429):
                break  # 차단 → 재시도 의미 없음
        except Exception as e:  # noqa
            last = repr(e)
        time.sleep(2 * (i + 1))
    raise RuntimeError(f"requests 실패: {last}")


# ── 엔진 2: Playwright (실제 페이지 안에서 fetch 실행 → 차단 우회) ───
class BrowserFetcher:
    def __init__(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=True)
        self._page = self._browser.new_page(locale="ko-KR")
        self._page.goto(PAGE + "?subPan=keyword", wait_until="domcontentloaded", timeout=60000)

    def fetch(self, url: str) -> dict:
        return self._page.evaluate(
            "async (u) => { const r = await fetch(u, {credentials:'omit'}); "
            "if (!r.ok) throw new Error('HTTP ' + r.status); return await r.json(); }", url)

    def close(self):
        try:
            self._browser.close()
            self._pw.stop()
        except Exception:
            pass


# ── 파싱 ────────────────────────────────────────────────────────────
def parse(payload: dict, tab_key: str, gf: str, collected_at: str) -> list:
    modules = payload.get("data", {}).get("modules", [])
    updated = ""
    for m in modules:
        if m.get("type") == "QUERY_UPDATEDAT":
            ms = (m.get("information") or {}).get("updatedAt")
            if ms:
                # 서버가 KST 시각을 UTC epoch처럼 내려줌(페이지 '1분 전' 표기와 대조 확인) → 오프셋 없이 변환
                updated = datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%d %H:%M")
    rows = []
    section_id, tab_label = TABS[tab_key]
    for m in modules:
        if m.get("type") != "RANKING_SEARCH":
            continue
        fl = m.get("fluctuation") or {}
        rows.append({
            "collected_at": collected_at,
            "ranking_updated_at": updated,
            "tab": tab_label,
            "section_id": section_id,
            "gender": GF_LABEL.get(gf, gf),
            "rank": int(m.get("rank") or 0),
            "keyword": (m.get("title") or {}).get("text", ""),
            "change_type": fl.get("type", ""),      # UP / DOWN / NEW / NONE (인기 탭만)
            "change_amount": fl.get("amount", ""),
            "search_url": (m.get("onClick") or {}).get("url", ""),
        })
    rows.sort(key=lambda r: r["rank"])
    return rows


# ── 수집 본체 (허브 러너 · 단독 실행 공용) ───────────────────────────
def collect(params: dict = None) -> dict:
    """params: {"tabs": ["popular","rising"], "gf": ["A","M","F"], "engine": "auto|requests|browser", "delay": 1.5}
    반환: {"columns": [...], "rows": [...], "meta": {...}, "raw": {...}}  — 허브 공통 형식
    """
    p = params or {}
    tabs = [t for t in (p.get("tabs") or list(TABS)) if t in TABS] or list(TABS)
    gfs = [g for g in (p.get("gf") or ["A"]) if g in GF_LABEL] or ["A"]
    engine = p.get("engine", "auto")
    delay = float(p.get("delay", 1.5))

    collected_at = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
    rows, raw, log = [], {}, []
    browser = None
    used_engine = None

    def get(url):
        nonlocal browser, used_engine
        if engine in ("auto", "requests") and browser is None:
            try:
                data = fetch_requests(url)
                used_engine = used_engine or "requests"
                return data
            except Exception as e:
                if engine == "requests":
                    raise
                log.append(f"requests 실패 → browser 전환: {e}")
        if browser is None:
            browser = BrowserFetcher()
        used_engine = "browser"
        return browser.fetch(url)

    try:
        for tab in tabs:
            for gf in gfs:
                url = build_url(TABS[tab][0], gf)
                payload = get(url)
                part = parse(payload, tab, gf, collected_at)
                raw[f"{tab}_{gf}"] = payload
                rows.extend(part)
                log.append(f"[{TABS[tab][1]} / {GF_LABEL[gf]}] {len(part)}건 "
                           f"(기준 {part[0]['ranking_updated_at'] if part else '-'}) "
                           f"TOP3: {', '.join(r['keyword'] for r in part[:3])}")
                time.sleep(delay)
    finally:
        if browser:
            browser.close()

    return {
        "columns": COLUMNS,
        "rows": rows,
        "meta": {
            "collected_at": collected_at,
            "engine": used_engine,
            "params": {"tabs": tabs, "gf": gfs},
            "requests": len(tabs) * len(gfs),
            "log": log,
        },
        "raw": raw,
    }


# ── 단독 실행: out/ 폴더에 CSV(월별 누적) + JSON 스냅샷 ──────────────
def main():
    ap = argparse.ArgumentParser(description="무신사 검색어 랭킹 수집")
    ap.add_argument("--tabs", nargs="+", choices=list(TABS), default=list(TABS))
    ap.add_argument("--gf", nargs="+", choices=list(GF_LABEL), default=["A"])
    ap.add_argument("--engine", choices=["auto", "requests", "browser"], default="auto")
    ap.add_argument("--out", default="out")
    ap.add_argument("--delay", type=float, default=1.5, help="요청 간 대기(초)")
    args = ap.parse_args()

    res = collect({"tabs": args.tabs, "gf": args.gf, "engine": args.engine, "delay": args.delay})
    for line in res["meta"]["log"]:
        print(line)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(KST)
    csv_path = out / f"musinsa_keyword_ranking_{stamp:%Y-%m}.csv"
    new = not csv_path.exists()
    with csv_path.open("a", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        if new:
            w.writeheader()
        w.writerows(res["rows"])
    snap_dir = out / "snapshots"
    snap_dir.mkdir(exist_ok=True)
    snap_path = snap_dir / f"{stamp:%Y%m%d_%H%M}.json"
    snap_path.write_text(json.dumps(res["raw"], ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n엔진: {res['meta']['engine']} / 저장: {csv_path} (+{len(res['rows'])}행) / {snap_path}")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:
        print(e, file=sys.stderr)
        sys.exit(1)
