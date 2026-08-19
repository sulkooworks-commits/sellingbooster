#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
encrypt_index.py — 인덱스 페이지 암호화 잠금 생성기
사용법:
    python3 encrypt_index.py index-source.html index.html "비밀번호"

- index-source.html : 원본(잠금 전) 인덱스. ⚠️ 저장소에 올리지 말 것!
- index.html        : 출력되는 잠금 페이지 (이 파일만 배포)
- 비밀번호 변경 시 이 스크립트를 다시 실행하면 됨.

방식: PBKDF2-HMAC-SHA256(310,000회) → AES-256-GCM
브라우저 WebCrypto로 복호화하므로 서버 불필요 (GitHub Pages 호환).
"""
import sys, os, json, base64
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ITER = 310000

def encrypt(html: str, password: str) -> dict:
    salt = os.urandom(16)
    iv = os.urandom(12)
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt,
                     iterations=ITER).derive(password.encode("utf-8"))
    ct = AESGCM(key).encrypt(iv, html.encode("utf-8"), None)
    b64 = lambda b: base64.b64encode(b).decode()
    return {"salt": b64(salt), "iv": b64(iv), "ct": b64(ct), "iter": ITER}

LOCK_TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>sulkoo.works</title>
<style>
:root{--bg:#0f1117;--card:#171a21;--line:#262b36;--tx:#e6e8ee;--dim:#9aa3b2;--acc:#5b8cff;--bad:#e06060}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--tx);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans KR",sans-serif;min-height:100vh;display:flex;align-items:center;justify-content:center}
.lock{width:min(360px,calc(100vw - 48px));background:var(--card);border:1px solid var(--line);border-radius:14px;padding:32px 28px;text-align:center}
.lock .ico{font-size:28px;margin-bottom:10px}
.lock h1{font-size:18px;margin:0 0 4px;letter-spacing:-.01em}
.lock p{color:var(--dim);font-size:13px;margin:0 0 20px}
.lock input{width:100%;background:var(--bg);border:1px solid var(--line);color:var(--tx);font-family:inherit;font-size:15px;padding:11px 14px;border-radius:9px;outline:none;text-align:center;letter-spacing:.15em;transition:border-color .15s}
.lock input:focus{border-color:var(--acc)}
.lock button{width:100%;margin-top:10px;background:var(--acc);border:none;color:#fff;font-family:inherit;font-size:14px;font-weight:600;padding:11px;border-radius:9px;cursor:pointer;transition:opacity .15s}
.lock button:hover{opacity:.9}
.lock button:disabled{opacity:.5;cursor:wait}
.msg{min-height:18px;margin-top:12px;font-size:12.5px;color:var(--bad)}
.msg.dim{color:var(--dim)}
</style>
</head>
<body>
<div class="lock">
  <div class="ico">🔒</div>
  <h1>sulkoo.works</h1>
  <p>비밀번호를 입력하면 대시보드가 열립니다<br>인증은 이 브라우저에서 30분간 유지됩니다</p>
  <input type="password" id="pw" autocomplete="current-password" autofocus aria-label="비밀번호">
  <button id="go" type="button">열기</button>
  <div class="msg" id="msg"></div>
</div>
<script>
var PAYLOAD = __PAYLOAD__;
var SKEY="ckUnlockSession",SESSION_MS=30*60*1000; /* 인증 유지 30분 */
var pw=document.getElementById("pw"),go=document.getElementById("go"),msg=document.getElementById("msg");
function b64(s){var bin=atob(s),a=new Uint8Array(bin.length);for(var i=0;i<bin.length;i++)a[i]=bin.charCodeAt(i);return a;}
function ab2b64(buf){var y=new Uint8Array(buf),bin="",CH=8192;for(var i=0;i<y.length;i+=CH)bin+=String.fromCharCode.apply(null,y.subarray(i,i+CH));return btoa(bin);}
function render(html){document.open();document.write(html);document.close();}
async function decryptWith(key){
  var plain=await crypto.subtle.decrypt({name:"AES-GCM",iv:b64(PAYLOAD.iv)},key,b64(PAYLOAD.ct));
  return new TextDecoder().decode(plain);
}
/* 30분 세션: 저장된 키가 유효하면 비밀번호 없이 자동 열림
   ⚠️ document.write 는 반드시 파싱 완료 후 실행 — 파싱 중 실행하면
   새 문서로 교체되지 않고 잠금 페이지 안에 끼어들어 화면이 깨짐 */
async function tryCached(){
  try{
    var s=JSON.parse(localStorage.getItem(SKEY)||"null");
    if(!s||Date.now()>s.exp){localStorage.removeItem(SKEY);return;}
    msg.className="msg dim";msg.textContent="자동 인증 확인 중…";
    var key=await crypto.subtle.importKey("raw",b64(s.k),{name:"AES-GCM"},false,["decrypt"]);
    var html=await decryptWith(key);
    render(html);
  }catch(e){
    localStorage.removeItem(SKEY); /* 만료·비밀번호 변경 시 폐기 */
    msg.textContent="";
  }
}
if(document.readyState==="loading"){
  document.addEventListener("DOMContentLoaded",function(){setTimeout(tryCached,0);});
}else{
  setTimeout(tryCached,0);
}
async function unlock(){
  var v=pw.value;
  if(!v){msg.textContent="비밀번호를 입력해주세요.";return;}
  go.disabled=true;msg.className="msg dim";msg.textContent="확인 중…";
  try{
    var keyMat=await crypto.subtle.importKey("raw",new TextEncoder().encode(v),"PBKDF2",false,["deriveKey"]);
    var key=await crypto.subtle.deriveKey(
      {name:"PBKDF2",salt:b64(PAYLOAD.salt),iterations:PAYLOAD.iter,hash:"SHA-256"},
      keyMat,{name:"AES-GCM",length:256},true,["decrypt"]);
    var html=await decryptWith(key);
    try{
      var raw=await crypto.subtle.exportKey("raw",key);
      localStorage.setItem(SKEY,JSON.stringify({k:ab2b64(raw),salt:PAYLOAD.salt,iter:PAYLOAD.iter,exp:Date.now()+SESSION_MS}));
    }catch(e){}
    render(html);
  }catch(e){
    go.disabled=false;msg.className="msg";
    msg.textContent="비밀번호가 올바르지 않습니다.";
    pw.value="";pw.focus();
  }
}
go.addEventListener("click",unlock);
pw.addEventListener("keydown",function(e){if(e.key==="Enter")unlock();});
</script>
</body>
</html>
"""

def main():
    if len(sys.argv) != 4:
        print(__doc__); sys.exit(1)
    src, out, password = sys.argv[1], sys.argv[2], sys.argv[3]
    html = open(src, encoding="utf-8").read()
    payload = encrypt(html, password)
    locked = LOCK_TEMPLATE.replace("__PAYLOAD__", json.dumps(payload))
    open(out, "w", encoding="utf-8").write(locked)
    print(f"OK: {out} 생성 (원본 {len(html):,}자 → 암호문 {len(payload['ct']):,}b64자)")
    print(f"⚠️  {src} 는 저장소에 올리지 마세요 (로컬 보관용)")

if __name__ == "__main__":
    main()
