# 셀링부스터 크롤러 허브

관리 페이지: `https://sulkooworks-commits.github.io/sellingbooster/크롤러/crawler-hub.html`

버튼을 눌렀을 때만 GitHub Actions가 수집을 1회 실행하고, 결과를 `data/`에 커밋합니다. 자동 스케줄은 없습니다.

```
크롤러/
├─ crawler-hub.html        관리 페이지 (목록 · 옵션 · 수집 실행 · 결과 표 · 이력 · 스크립트 다운로드)
├─ crawlers.json           크롤러 레지스트리 (페이지가 읽음)
├─ scripts/
│   ├─ _runner.py          공통 러너 — Actions가 호출. 결과 저장 규칙 담당
│   └─ <id>.py             크롤러 본체 (단독 실행 가능 + collect() 제공)
└─ data/<id>/
    ├─ latest.json         최신 결과 {columns, rows, meta}
    ├─ latest.csv          같은 내용 CSV (UTF-8 BOM, 엑셀 호환)
    ├─ runs.json           실행 이력 (최근 300건)
    └─ history/<ts>.json   회차별 스냅샷
.github/workflows/crawler-run.yml   workflow_dispatch(crawler, params) → _runner.py 실행 → data/ 커밋
```

## 개발자: 스크립트 단독 검증

```bash
pip install requests
python musinsa_keyword_ranking.py                 # out/ 폴더에 CSV·스냅샷 저장
python musinsa_keyword_ranking.py --gf A M F
python musinsa_keyword_ranking.py --engine browser   # 차단 시 (pip install playwright && playwright install chromium)
```

## 새 크롤러 추가 (3단계)

1. `scripts/<id>.py` 작성 — `collect(params: dict) -> dict` 필수
   ```python
   def collect(params=None):
       ...
       return {"columns": ["rank", "name"], "rows": [{"rank": 1, "name": "..."}], "meta": {"log": ["..."]}}
   ```
   `raw` 키(원본 응답)는 선택. 단독 실행용 `main()`을 두면 다운로드 검증에 편함.
2. `crawlers.json`의 `crawlers` 배열에 항목 추가 (`id` = 파일명, `params`는 옵션 UI 자동 생성, `columns`는 표 컬럼)
3. 커밋 → 페이지에 카드 자동 표시. 러너·워크플로 수정 불필요

`params` 타입: `multi`(체크박스, 배열 전달) · `select`(라디오, 문자열 전달) · `text`(문자열 전달)

## 실행 권한

페이지의 「▶ 수집 실행」은 GitHub Fine-grained 토큰(Repository: sellingbooster, Permissions: Actions → Read and write)을 브라우저 localStorage에 저장해 사용합니다. SEO 모니터링 페이지와 같은 키(`seoMonitorDispatchToken`)를 쓰므로 한 번만 입력하면 됩니다.
