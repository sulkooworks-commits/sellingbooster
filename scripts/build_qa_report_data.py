#!/usr/bin/env python3
"""
셀링부스터 QA 진행 보고 — 아사나 집계 → 암호화 데이터 생성
GitHub Actions에서 6시간 간격 실행. 산출물: QA/APP/data/qa_report.enc.json (AES-256-GCM)
필요 환경변수: ASANA_TOKEN, REPORT_PASS
"""
import os, json, base64, hashlib, urllib.request, datetime

TOKEN = os.environ["ASANA_TOKEN"]
PASS  = os.environ["REPORT_PASS"]
PROJECT = "1212334968261160"
API = "https://app.asana.com/api/1.0"

SEC = {  # 섹션 gid → 리포트 키
    "1212334968261161": "qa_line", "1212287900218727": "assigned",
    "1212287900218729": "in_progress", "1212287900218731": "work_done",
    "1212287900218733": "reviewed", "1212287900222037": "hold",
    "1212287900222039": "enhance",
}
SEC_LABEL = {"qa_line":"QA 라인 (할당 대기)","assigned":"업무 할당","in_progress":"진행 중",
             "work_done":"작업 완료 (검수 대기)","reviewed":"검수 완료","hold":"보류·중복","enhance":"고도화 예정"}

def api(path):
    req = urllib.request.Request(API+path, headers={"Authorization": "Bearer "+TOKEN})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)

def all_tasks():
    out, offset = [], None
    fields = "completed,name,memberships.section.gid,custom_fields.gid,custom_fields.display_value"
    while True:
        p = f"/projects/{PROJECT}/tasks?limit=100&opt_fields={fields}"
        if offset: p += "&offset="+offset
        j = api(p)
        out += j["data"]
        nxt = j.get("next_page") or {}
        offset = nxt.get("offset")
        if not offset: break
    return out

def cf(t, gid):
    for c in t.get("custom_fields", []):
        if c["gid"] == gid: return c.get("display_value")
    return None

def main():
    tasks = all_tasks()
    total = len(tasks); done = sum(1 for t in tasks if t["completed"])
    openn = total - done

    # 앱 3차 카드: 차수=3차 & 디바이스에 APP 포함
    app = [t for t in tasks
           if (cf(t, "1208108980900826") == "3차") and ("APP" in (cf(t, "1212345665719510") or ""))]
    auto = [t for t in app if (cf(t, "1212345665719522") or "").startswith("A-")]
    manual = [t for t in app if t not in auto]
    app_open = [t for t in app if not t["completed"]]
    auto_open = [t for t in auto if not t["completed"]]

    by_sec = {}
    for t in auto:
        if t["completed"]:
            by_sec["completed"] = by_sec.get("completed", 0) + 1; continue
        gid = (t.get("memberships") or [{}])[0].get("section", {}).get("gid")
        k = SEC.get(gid, "etc")
        by_sec[k] = by_sec.get(k, 0) + 1

    by_type = {}
    for t in auto_open:
        ty = cf(t, "1212351705198327") or "미지정"
        by_type[ty] = by_type.get(ty, 0) + 1

    errors = []
    for t in auto_open:
        if cf(t, "1212351705198327") == "오류":
            gid = (t.get("memberships") or [{}])[0].get("section", {}).get("gid")
            errors.append({
                "tid": cf(t, "1212345665719522") or "-",
                "title": t["name"].replace("[SB]", "").strip(),
                "sec": SEC_LABEL.get(SEC.get(gid, ""), "기타"),
                "ver": cf(t, "1215706549201611") or "-",
            })
    errors.sort(key=lambda x: x["tid"])

    web_open = openn - len(app_open)
    processed = by_sec.get("completed", 0) + by_sec.get("work_done", 0)
    data = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc)
                        .astimezone(datetime.timezone(datetime.timedelta(hours=9)))
                        .strftime("%Y-%m-%d %H:%M KST"),
        "total": {"n": total, "done": done, "open": openn},
        "app": {"n": len(app), "auto": len(auto), "manual": len(manual),
                "open": len(app_open), "auto_open": len(auto_open),
                "by_sec": by_sec, "by_type": by_type,
                "proc_rate": round(processed / max(len(app), 1) * 100, 1)},
        "web_open": web_open,
        "errors": errors,
    }

    raw = json.dumps(data, ensure_ascii=False).encode()
    salt, iv = os.urandom(16), os.urandom(12)
    key = hashlib.pbkdf2_hmac("sha256", PASS.encode(), salt, 200000, 32)
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        ct = AESGCM(key).encrypt(iv, raw, None)
    except ImportError:
        import subprocess, sys
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "cryptography"], check=True)
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        ct = AESGCM(key).encrypt(iv, raw, None)

    os.makedirs("QA/APP/data", exist_ok=True)
    with open("QA/APP/data/qa_report.enc.json", "w") as f:
        json.dump({"v": 1, "salt": base64.b64encode(salt).decode(),
                   "iv": base64.b64encode(iv).decode(),
                   "ct": base64.b64encode(ct).decode()}, f)
    print("built:", data["generated_at"], "| total", total, "| app", len(app), "| errors", len(errors))

if __name__ == "__main__":
    main()
