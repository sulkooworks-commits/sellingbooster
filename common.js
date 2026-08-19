/* ============================================================
   sulkoo.works 공통영역 스크립트 (GNB 헤더 + 검색)
   - 각 페이지 </body> 직전에 아래 한 줄만 추가하면
     인덱스·하위 페이지 어디서든 동일한 GNB가 상단에 부착됨:
     <script src="common.js" defer></script>
   - 하위 폴더 페이지: <script src="../common.js" defer></script>
     + <body data-root="../"> 로 경로 지정
   - 메뉴/검색 대상 수정은 MENU 배열 한 곳만 고치면 전 페이지 반영
     (kw: 검색 보조 키워드 — 화면에는 표시되지 않음)
   ============================================================ */

(function () {
  var ROOT = document.body.getAttribute("data-root") || "";

  /* ---------- 사이트 메뉴 정의 (단일 소스 · kw = 검색 키워드) ---------- */
  var MENU = [
    {
      no: "01", title: "콘텐츠 운영",
      items: [
        { t: "CMS 워싱 표준 워크플로", href: "content-washing.html", kw: "블로그 워싱 하이훅 초안 에디터 형식 키워드 링크 이미지 표 FAQ" },
        { t: "편집 캘린더 (8–9월)", href: "content-calendar.html", kw: "발행 일정 월수금 주3회 시즌 콘텐츠 선점" },
        { t: "네이버 블로그 발행 표준", href: "content-naver.html", kw: "스마트에디터 유사문서 2주 시차 ALT 대조표 경어체 해시태그" }
      ]
    },
    {
      no: "02", title: "SEO 모니터링",
      items: [
        { t: "발행 정책 (기준 문서)", href: "seo-policy.html", kw: "모니터링 기준 채널 목표 판정 규칙 주5회" },
        { t: "발행 로그 (일일 스냅샷)", href: "seo-log.html", kw: "자동 모니터링 베이스라인 94건 스냅샷 증분" },
        { t: "주간 달성 리포트", href: "seo-weekly.html", kw: "주간 집계 정상 주의 미달 월요일" },
        { t: "하이훅 연동 검토", href: "highook-review.html", kw: "highook GEO 가이드 콘텐츠 생성 솔루션 검토의견 8개 제안" }
      ]
    },
    {
      no: "03", title: "기획·어드민",
      items: [
        { t: "어드민 화면 기능 명세", href: "admin-spec.html", kw: "배너 팝업 셀링플래너 온보딩 와이어프레임 명세서" },
        { t: "셀링스파크 통합 기획", href: "sellingspark-plan.html", kw: "블로그페이 블로그마켓 틱톡샵 TikTok Shop 10월 통합" }
      ]
    },
    {
      no: "04", title: "분석·리서치",
      items: [
        { t: "국내 25종 벤치마킹", href: "research-kr.html", kw: "아이템스카웃 판다랭크 경쟁 서비스 비교 최적가 추천" },
        { t: "일본 커머스 서비스 조사", href: "research-jp.html", kw: "Nint Keepa Kalodata 일본 리서치" }
      ]
    },
    {
      no: "05", title: "도구",
      items: [
        { t: "해외 광고비 정산 툴", href: "tool-adcost.html", kw: "환율 하나은행 수출입은행 API 메타 구글 엑셀 ExcelJS 정산" }
      ]
    },
    {
      no: "06", title: "팀 관리",
      items: [
        { t: "셀링부스터 팀 업무 정리", href: "셀링부스터_팀업무정리.html", kw: "이슬기 안지호 기획 마케팅 업무 분장" },
        { t: "협업·커뮤니케이션 기준", href: "team-comms.html", kw: "검토 문서 문체 기술 문의 개발팀 보고" }
      ]
    },
    {
      no: "07", title: "운영 계획",
      items: [
        { t: "하반기 제품 로드맵", href: "plan-roadmap.html", kw: "멀티마켓 쿠팡 11번가 앱 출시 커머스솔루션마켓 cafe24 TTJ 랭킹" },
        { t: "일정·기한 체크리스트", href: "plan-deadlines.html", kw: "네이버 착수 8월26일 주5회 전환 기한 데드라인" }
      ]
    }
  ];

  /* ---------- 사이트맵 그리드 HTML (전체 메뉴 패널·푸터 공용) ---------- */
  function sitemapHTML() {
    return MENU.map(function (g) {
      var lis = g.items.map(function (it) {
        return '<li><a href="' + ROOT + it.href + '">' + it.t + "</a></li>";
      }).join("");
      return '<div class="ck-sm-col"><h3><span class="no">' + g.no + "</span>" + g.title + "</h3><ul>" + lis + "</ul></div>";
    }).join("");
  }

  /* ---------- 공통 스타일 주입 ---------- */
  var css = ""
    /* GNB 바 */
    + ".ck-gnb{position:sticky;top:0;z-index:50;background:rgba(15,17,23,.94);backdrop-filter:blur(8px);border-bottom:1px solid var(--line,#262b36)}"
    + ".ck-gnb-in{max-width:960px;margin:0 auto;padding:0 24px;display:flex;align-items:stretch;gap:2px}"
    + ".ck-gnb a,.ck-gnb button,.ck-gnb input{font-family:inherit}"
    + ".ck-home{display:flex;align-items:center;text-decoration:none;color:var(--tx,#e6e8ee);font-weight:700;font-size:14px;letter-spacing:-.01em;padding:14px 14px 14px 0;margin-right:6px;white-space:nowrap}"
    + ".ck-home::before{content:'⌂';margin-right:6px;color:var(--acc,#5b8cff)}"
    /* GNB 1뎁스 */
    + ".ck-gnb-menu{display:flex;align-items:stretch;list-style:none;margin:0;padding:0;min-width:0}"
    + ".ck-gnb-item{position:relative}"
    + ".ck-gnb-top{display:flex;align-items:center;gap:5px;height:100%;padding:14px 11px;background:none;border:none;color:var(--dim,#9aa3b2);font-size:13px;cursor:pointer;white-space:nowrap;border-bottom:2px solid transparent;transition:color .15s,border-color .15s}"
    + ".ck-gnb-top .caret{font-size:9px;color:var(--dim,#9aa3b2);transition:transform .15s}"
    + ".ck-gnb-item:hover .ck-gnb-top,.ck-gnb-top:focus-visible,.ck-gnb-item.open .ck-gnb-top{color:var(--tx,#e6e8ee);border-bottom-color:var(--acc,#5b8cff);outline:none}"
    + ".ck-gnb-item.open .ck-gnb-top .caret{transform:rotate(180deg)}"
    /* GNB 2뎁스 드롭다운 */
    + ".ck-gnb-drop{position:absolute;top:100%;left:0;min-width:220px;background:var(--card,#171a21);border:1px solid var(--line,#262b36);border-radius:0 0 10px 10px;box-shadow:0 12px 28px rgba(0,0,0,.45);padding:8px 0;margin:0;list-style:none;display:none}"
    + ".ck-gnb-item:hover .ck-gnb-drop,.ck-gnb-item.open .ck-gnb-drop,.ck-gnb-item:focus-within .ck-gnb-drop{display:block}"
    + ".ck-gnb-drop a{display:block;padding:8px 16px;color:var(--tx,#e6e8ee);opacity:.8;text-decoration:none;font-size:13px}"
    + ".ck-gnb-drop a:hover,.ck-gnb-drop a:focus-visible{opacity:1;background:rgba(91,140,255,.12);color:var(--acc,#5b8cff);outline:none}"
    /* 검색 */
    + ".ck-search{position:relative;display:flex;align-items:center;margin-left:auto;align-self:center}"
    + ".ck-search input{width:170px;background:var(--card,#171a21);border:1px solid var(--line,#262b36);color:var(--tx,#e6e8ee);font-size:13px;padding:6px 10px 6px 30px;border-radius:8px;outline:none;transition:border-color .15s,width .2s}"
    + ".ck-search input::placeholder{color:var(--dim,#9aa3b2)}"
    + ".ck-search input:focus{border-color:var(--acc,#5b8cff);width:220px}"
    + ".ck-search .ico{position:absolute;left:10px;color:var(--dim,#9aa3b2);font-size:13px;pointer-events:none}"
    + ".ck-search-res{position:absolute;top:calc(100% + 6px);right:0;width:320px;max-height:340px;overflow-y:auto;background:var(--card,#171a21);border:1px solid var(--line,#262b36);border-radius:10px;box-shadow:0 12px 28px rgba(0,0,0,.45);padding:6px 0;margin:0;list-style:none;display:none}"
    + ".ck-search-res.open{display:block}"
    + ".ck-search-res a{display:block;padding:9px 14px;text-decoration:none}"
    + ".ck-search-res .rt{color:var(--tx,#e6e8ee);font-size:13px;font-weight:600}"
    + ".ck-search-res .rt mark{background:none;color:var(--acc,#5b8cff)}"
    + ".ck-search-res .rc{color:var(--dim,#9aa3b2);font-size:11.5px;margin-top:1px}"
    + ".ck-search-res li.active a,.ck-search-res a:hover{background:rgba(91,140,255,.12)}"
    + ".ck-search-res .empty{padding:12px 14px;color:var(--dim,#9aa3b2);font-size:13px}"
    /* 전체 메뉴 버튼 */
    + ".ck-map-btn{margin-left:8px;align-self:center;background:var(--card,#171a21);border:1px solid var(--line,#262b36);color:var(--tx,#e6e8ee);font-size:13px;padding:6px 12px;border-radius:8px;cursor:pointer;display:inline-flex;align-items:center;gap:6px;white-space:nowrap;transition:border-color .15s}"
    + ".ck-map-btn:hover,.ck-map-btn:focus-visible{border-color:var(--acc,#5b8cff);outline:none}"
    + ".ck-map-btn .ic{color:var(--acc,#5b8cff);font-size:12px;line-height:1}"
    + ".ck-map-btn[aria-expanded=true] .ic{transform:rotate(180deg)}"
    /* 전체 메뉴(사이트맵) 패널 */
    + ".ck-map-panel{display:none;border-top:1px solid var(--line,#262b36);background:rgba(15,17,23,.98)}"
    + ".ck-map-panel.open{display:block}"
    + ".ck-map-panel-in{max-width:960px;margin:0 auto;padding:22px 24px 26px}"
    + ".ck-map-panel .ck-sitemap{margin-bottom:0}"
    /* 좁은 화면: 1뎁스 숨기고 검색+전체 메뉴만 */
    + "@media(max-width:900px){.ck-gnb-menu{display:none}.ck-search input{width:130px}.ck-search input:focus{width:170px}}"
    /* 사이트맵 그리드 (패널·푸터 공용) */
    + ".ck-sitemap{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:20px 28px;margin-bottom:28px}"
    + ".ck-sm-col h3{margin:0 0 8px;font-size:12px;text-transform:uppercase;letter-spacing:.08em;color:var(--dim,#9aa3b2);font-weight:600}"
    + ".ck-sm-col h3 .no{color:var(--acc,#5b8cff);margin-right:6px}"
    + ".ck-sm-col ul{list-style:none;margin:0;padding:0}"
    + ".ck-sm-col li{margin:4px 0}"
    + ".ck-sm-col a{color:var(--tx,#e6e8ee);opacity:.75;text-decoration:none;font-size:13px}"
    + ".ck-sm-col a:hover{opacity:1;color:var(--acc,#5b8cff)}"
    + "@media print{.ck-gnb{display:none}}";
  var st = document.createElement("style");
  st.textContent = css;
  document.head.appendChild(st);

  /* ---------- GNB 헤더 ---------- */
  var gnb = document.createElement("header");
  gnb.className = "ck-gnb";
  var menuLis = MENU.map(function (g, i) {
    var drop = g.items.map(function (it) {
      return '<li><a href="' + ROOT + it.href + '">' + it.t + "</a></li>";
    }).join("");
    return '<li class="ck-gnb-item" data-i="' + i + '">'
      + '<button type="button" class="ck-gnb-top" aria-expanded="false" aria-haspopup="true">'
      + g.title + ' <span class="caret">▾</span></button>'
      + '<ul class="ck-gnb-drop">' + drop + "</ul></li>";
  }).join("");
  gnb.innerHTML =
    '<div class="ck-gnb-in">'
    + '<a class="ck-home" href="' + ROOT + 'index.html">sulkoo.works</a>'
    + '<ul class="ck-gnb-menu">' + menuLis + "</ul>"
    + '<div class="ck-search"><span class="ico">⌕</span>'
    + '<input type="search" placeholder="페이지 검색 ( / )" aria-label="페이지 검색" autocomplete="off">'
    + '<ul class="ck-search-res" role="listbox"></ul></div>'
    + '<button type="button" class="ck-map-btn" aria-expanded="false" aria-controls="ck-map-panel">전체 메뉴 <span class="ic">▾</span></button>'
    + "</div>"
    + '<div class="ck-map-panel" id="ck-map-panel">'
    + '<div class="ck-map-panel-in"><div class="ck-sitemap">' + sitemapHTML() + "</div></div>"
    + "</div>";
  document.body.insertBefore(gnb, document.body.firstChild);

  /* ---------- 1뎁스 클릭 토글 (터치 대응) ---------- */
  var items = gnb.querySelectorAll(".ck-gnb-item");
  function closeMenus() {
    items.forEach(function (el) {
      el.classList.remove("open");
      el.querySelector(".ck-gnb-top").setAttribute("aria-expanded", "false");
    });
  }
  items.forEach(function (el) {
    el.querySelector(".ck-gnb-top").addEventListener("click", function () {
      var willOpen = !el.classList.contains("open");
      closeMenus();
      if (willOpen) { el.classList.add("open"); this.setAttribute("aria-expanded", "true"); }
    });
  });

  /* ---------- 전체 메뉴(사이트맵) 패널 ---------- */
  var btn = gnb.querySelector(".ck-map-btn");
  var panel = gnb.querySelector(".ck-map-panel");
  function setPanel(open) {
    panel.classList.toggle("open", open);
    btn.setAttribute("aria-expanded", open ? "true" : "false");
  }
  btn.addEventListener("click", function () {
    closeMenus(); closeSearch();
    setPanel(!panel.classList.contains("open"));
  });

  /* ---------- 검색 ---------- */
  /* 검색 인덱스: 페이지 제목 + 섹션명 + 보조 키워드(kw) */
  var INDEX = [];
  MENU.forEach(function (g) {
    g.items.forEach(function (it) {
      INDEX.push({
        t: it.t, href: ROOT + it.href, sec: g.no + " " + g.title,
        hay: (it.t + " " + g.title + " " + (it.kw || "")).toLowerCase()
      });
    });
  });

  var sInput = gnb.querySelector(".ck-search input");
  var sRes = gnb.querySelector(".ck-search-res");
  var sActive = -1;

  function esc(s) { return s.replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function highlight(title, terms) {
    var out = esc(title);
    terms.forEach(function (term) {
      if (!term) return;
      var re = new RegExp("(" + term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + ")", "gi");
      out = out.replace(re, "<mark>$1</mark>");
    });
    return out;
  }
  function closeSearch() {
    sRes.classList.remove("open");
    sRes.innerHTML = "";
    sActive = -1;
  }
  function runSearch() {
    var q = sInput.value.trim().toLowerCase();
    if (!q) { closeSearch(); return; }
    var terms = q.split(/\s+/);
    var hits = INDEX.filter(function (p) {
      return terms.every(function (term) { return p.hay.indexOf(term) !== -1; });
    }).slice(0, 8);
    sActive = -1;
    if (!hits.length) {
      sRes.innerHTML = '<li class="empty">"' + esc(sInput.value.trim()) + '" 검색 결과 없음</li>';
    } else {
      sRes.innerHTML = hits.map(function (p) {
        return '<li role="option"><a href="' + p.href + '">'
          + '<div class="rt">' + highlight(p.t, terms) + "</div>"
          + '<div class="rc">' + esc(p.sec) + "</div></a></li>";
      }).join("");
    }
    sRes.classList.add("open");
  }
  sInput.addEventListener("input", runSearch);
  sInput.addEventListener("focus", function () { closeMenus(); setPanel(false); if (sInput.value.trim()) runSearch(); });
  sInput.addEventListener("keydown", function (e) {
    var opts = sRes.querySelectorAll("li[role=option]");
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!opts.length) return;
      sActive = e.key === "ArrowDown"
        ? (sActive + 1) % opts.length
        : (sActive - 1 + opts.length) % opts.length;
      opts.forEach(function (o, i) { o.classList.toggle("active", i === sActive); });
      opts[sActive].scrollIntoView({ block: "nearest" });
    } else if (e.key === "Enter") {
      if (sActive >= 0 && opts[sActive]) {
        location.href = opts[sActive].querySelector("a").href;
      } else if (opts.length === 1) {
        location.href = opts[0].querySelector("a").href;
      }
    } else if (e.key === "Escape") {
      closeSearch(); sInput.blur();
    }
  });
  /* "/" 단축키로 검색창 포커스 */
  document.addEventListener("keydown", function (e) {
    if (e.key === "/" && document.activeElement !== sInput
        && !/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName)
        && !document.activeElement.isContentEditable) {
      e.preventDefault();
      sInput.focus();
    }
  });

  /* ---------- 바깥 클릭·ESC로 모두 닫기 ---------- */
  document.addEventListener("click", function (e) {
    if (!gnb.contains(e.target)) { closeMenus(); setPanel(false); closeSearch(); }
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") { closeMenus(); setPanel(false); closeSearch(); }
  });

})();
