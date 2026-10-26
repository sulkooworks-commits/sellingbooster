# -*- coding: utf-8 -*-
"""크롤러 허브 공통 러너 — GitHub Actions(crawler-run.yml)가 호출

사용: python 크롤러/scripts/_runner.py <crawler_id> [--params '{"gf":["A","M"]}']

동작
  1. 크롤러/crawlers.json 에서 <crawler_id> 항목을 찾아 scripts/<id>.py 의 collect(params) 호출
  2. 결과를 크롤러/data/<id>/ 에 저장
       latest.json           최신 수집 결과 (columns · rows · meta)  ← 허브 페이지가 표로 표시
       latest.csv            같은 내용 CSV (엑셀용, UTF-8 BOM)
       history/<ts>.json     수집 1회분 결과 스냅샷 (rows 포함, raw 제외)
       runs.json             실행 이력 (최근 300건) ← 허브 페이지가 완료 감지·이력 표시에 사용
  3. 실패해도 runs.json 에 status=error 로 기록하고 종료 코드 1

크롤러 스크립트 규약 (새 크롤러 추가 시)
  - scripts/<id>.py 에 collect(params: dict) -> dict 함수 정의
  - 반환: {"columns": [str,...], "rows": [dict,...], "meta": {...}, "raw": any(선택)}
  - crawlers.json 에 항목 추가 (id 는 파일명과 동일)
"""
import argparse
import importlib.util
import json
import sys
import traceback
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent          # 크롤러/
REGISTRY = BASE / "crawlers.json"
KST = timezone(timedelta(hours=9))
MAX_RUNS = 300


def load_crawler(cid: str) -> dict:
    reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
    for c in reg["crawlers"]:
        if c["id"] == cid:
            return c
    raise SystemExit(f"crawlers.json 에 id={cid} 항목이 없습니다")


def import_script(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not hasattr(mod, "collect"):
        raise SystemExit(f"{path.name} 에 collect(params) 함수가 없습니다")
    return mod


def write_csv(path: Path, columns, rows):
    import csv
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def append_run(data_dir: Path, entry: dict):
    runs_path = data_dir / "runs.json"
    runs = []
    if runs_path.exists():
        try:
            runs = json.loads(runs_path.read_text(encoding="utf-8"))
        except Exception:
            runs = []
    runs.insert(0, entry)
    runs_path.write_text(json.dumps(runs[:MAX_RUNS], ensure_ascii=False, indent=1), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("crawler_id")
    ap.add_argument("--params", default="", help='JSON 문자열, 예: {"gf":["A","M"]}')
    ap.add_argument("--run-url", default="", help="GitHub Actions 실행 URL (이력 링크용)")
    args = ap.parse_args()

    params = {}
    if args.params.strip():
        try:
            params = json.loads(args.params)
        except json.JSONDecodeError as e:
            raise SystemExit(f"--params JSON 파싱 실패: {e}")

    crawler = load_crawler(args.crawler_id)
    data_dir = BASE / "data" / crawler["id"]
    (data_dir / "history").mkdir(parents=True, exist_ok=True)
    started = datetime.now(KST)
    ts = started.strftime("%Y%m%d_%H%M%S")
    print(f"▶ {crawler['name']} ({crawler['id']}) 수집 시작 {started:%Y-%m-%d %H:%M:%S} params={params}")

    try:
        mod = import_script(BASE / crawler["script"])
        res = mod.collect(params)
        columns, rows, meta = res["columns"], res["rows"], dict(res.get("meta") or {})
        for line in meta.get("log", []):
            print("  " + line)
        finished = datetime.now(KST)
        meta.update({
            "crawler_id": crawler["id"],
            "started_at": started.strftime("%Y-%m-%d %H:%M:%S"),
            "finished_at": finished.strftime("%Y-%m-%d %H:%M:%S"),
            "duration_sec": round((finished - started).total_seconds(), 1),
            "count": len(rows),
            "snapshot": f"history/{ts}.json",
            "run_url": args.run_url,
        })
        latest = {"columns": columns, "rows": rows, "meta": meta}
        (data_dir / "latest.json").write_text(json.dumps(latest, ensure_ascii=False, indent=1), encoding="utf-8")
        (data_dir / "history" / f"{ts}.json").write_text(json.dumps(latest, ensure_ascii=False), encoding="utf-8")
        write_csv(data_dir / "latest.csv", columns, rows)
        append_run(data_dir, {
            "ts": ts, "run_at": meta["finished_at"], "status": "ok", "count": len(rows),
            "duration_sec": meta["duration_sec"], "engine": meta.get("engine"),
            "params": meta.get("params", params), "snapshot": meta["snapshot"], "run_url": args.run_url,
        })
        print(f"✅ 완료 {len(rows)}건 ({meta['duration_sec']}초, engine={meta.get('engine')}) → {data_dir}")
    except Exception as e:  # noqa
        err = f"{type(e).__name__}: {e}"
        traceback.print_exc()
        append_run(data_dir, {
            "ts": ts, "run_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S"), "status": "error",
            "count": 0, "error": err[:500], "params": params, "run_url": args.run_url,
        })
        print(f"❌ 실패: {err}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
