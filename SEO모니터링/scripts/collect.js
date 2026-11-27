// 셀링부스터 블로그 일일 수집 스크립트 (GitHub Actions에서 실행)
// v7: 유튜브 쇼츠(RSS) + 인스타그램(베스트에포트) 수집 추가 — 각각 주 2회 발행 채널
// v6: 카페24 스토리 수집 추가 + 채널별 실패 격리 (한 채널이 실패해도 나머지는 수집)
//     Playwright 브라우저 렌더링 기반 — 사이트가 클라이언트 렌더링(Nuxt)이라
//     단순 fetch로는 빈 셸만 내려오므로 실제 브라우저로 렌더 후 DOM에서 추출한다.
// - data/posts.json 에 신규 글 누적, data/meta.json 에 전체 건수 이력 기록
// - 실패 시 데이터는 건드리지 않고 lastStatus 로 기록
'use strict';
const fs = require('fs');
const path = require('path');

const PAGE_URL = 'https://sellingbooster.io/community/blog';
const CATS = ['K트렌드 매거진', '지식', '이용사례', '뉴스룸'];
const ROOT = path.join(__dirname, '..');
const p = (...s) => path.join(ROOT, ...s);

function todayKST() {
  return new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Seoul' }).format(new Date());
}
function normDate(s) {
  const m = String(s).match(/(\d{4})[.\-\/](\d{1,2})[.\-\/](\d{1,2})/);
  if (!m) return null;
  return `${m[1]}-${m[2].padStart(2, '0')}-${m[3].padStart(2, '0')}`;
}
const key = (x) => x.date + '|' + String(x.title).slice(0, 40);

// 데이터 정리: 과거 파서가 본문을 제목으로 저장한 항목(150자 초과)과 중복 제거
function sanitize(posts) {
  // 1) 같은 url이 여러 개면 제목이 짧은(정상) 항목 유지
  const byUrl = new Map();
  const noUrl = [];
  for (const x of posts) {
    if (x.url) {
      const prev = byUrl.get(x.url);
      if (!prev || String(x.title).length < String(prev.title).length) byUrl.set(x.url, x);
    } else noUrl.push(x);
  }
  let out = [...byUrl.values(), ...noUrl];
  // 2) 제목 150자 초과 항목: 같은 날짜+카테고리의 정상 항목이 있으면 제거
  out = out.filter((x) => {
    if (String(x.title).length <= 150) return true;
    return !out.some((y) => y !== x && y.date === x.date && y.category === x.category && String(y.title).length <= 150);
  });
  // 3) 날짜+제목(40자) 중복 제거
  const seen = new Set();
  return out.filter((x) => { const k = key(x); if (seen.has(k)) return false; seen.add(k); return true; })
    .sort((a, b) => a.date.localeCompare(b.date));
}

async function collectWithBrowser() {
  const { chromium } = require('playwright');
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1400, height: 2200 } });
    await page.goto(PAGE_URL, { waitUntil: 'networkidle', timeout: 60000 });
    await page.waitForTimeout(3000);
    // 스크롤해서 로드 가능한 글 더 확보
    for (let i = 0; i < 8; i++) { await page.mouse.wheel(0, 3000); await page.waitForTimeout(700); }

    const bodyText = await page.evaluate(() => document.body.innerText);
    fs.mkdirSync(p('debug'), { recursive: true });
    fs.writeFileSync(p('debug', 'last-fetch.txt'), bodyText.slice(0, 300000));

    const mTotal = bodyText.match(/전체\s*\(\s*(\d+)\s*\)/);
    const total = mTotal ? parseInt(mTotal[1], 10) : null;

    const items = await page.evaluate((CATS) => {
      const out = [];
      const seen = new Set();
      document.querySelectorAll('a[href*="/community/blog/"]').forEach((a) => {
        const href = a.href || '';
        if (href.replace(/\/$/, '').endsWith('/community/blog')) return; // 목록 자신
        const lines = (a.innerText || '').split('\n').map((s) => s.trim()).filter(Boolean);
        if (!lines.length) return;
        const category = lines.find((l) => CATS.includes(l)) || null;
        const dateLine = lines.find((l) => /\d{4}[.\-\/]\d{1,2}[.\-\/]\d{1,2}/.test(l)) || null;
        // 제목: 카테고리·날짜 제외, 8~150자 범위의 "첫 번째" 줄 (본문 미리보기는 150자 초과라 제외됨)
        // 주의: "2026 코리아 이커머스 페어…"처럼 숫자로 시작하는 제목이 있으므로
        //       숫자 시작 전체 제외가 아니라 날짜 형식·순수 숫자 줄만 제외한다
        const title = lines
          .find((l) => l !== category && l !== dateLine && l.length >= 8 && l.length <= 150
            && !/^\d{4}[.\-\/]\d{1,2}[.\-\/]\d{1,2}/.test(l) && !/^[\d,.\s]+$/.test(l)) || null;
        // 조회수: 카드 하단의 독립된 숫자 줄 (예: "6", "1,024")
        let views = null;
        for (let i = lines.length - 1; i >= 0; i--) {
          const m2 = lines[i].match(/^([\d,]{1,9})$/);
          if (m2) { views = parseInt(m2[1].replace(/,/g, ''), 10); break; }
        }
        if (category && dateLine && title && !seen.has(href)) {
          seen.add(href);
          out.push({ href, category, dateLine, title, views });
        }
      });
      return out;
    }, CATS);

    return {
      total,
      posts: items.map((it) => ({
        date: normDate(it.dateLine),
        category: it.category,
        title: it.title,
        url: it.href,
        views: it.views,
      })).filter((x) => x.date && x.title),
    };
  } finally {
    await browser.close();
  }
}

// 네이버 블로그 RSS 수집 (policy.json의 naver 채널 url 사용)
async function collectNaver(policy) {
  const ch = (policy.channels || []).find((c) => c.id === 'naver');
  if (!ch || !ch.url) return null; // 미등록
  let rssUrl = ch.url;
  const m = rssUrl.match(/blog\.naver\.com\/([A-Za-z0-9_-]+)/);
  if (!/rss\.blog\.naver\.com/.test(rssUrl) && m) rssUrl = 'https://rss.blog.naver.com/' + m[1] + '.xml';
  const res = await fetch(rssUrl, { headers: { 'User-Agent': 'Mozilla/5.0 (compatible; seo-monitor/1.0)' } });
  if (!res.ok) throw new Error('naver rss HTTP ' + res.status);
  const xml = await res.text();
  const items = [];
  const re = /<item>([\s\S]*?)<\/item>/g;
  let mm;
  while ((mm = re.exec(xml)) !== null) {
    const block = mm[1];
    const pick = (tag) => {
      const r = block.match(new RegExp('<' + tag + '>(?:<!\\[CDATA\\[)?([\\s\\S]*?)(?:\\]\\]>)?<\\/' + tag + '>'));
      return r ? r[1].trim() : '';
    };
    const title = pick('title');
    const link = pick('link');
    const pub = pick('pubDate');
    const d = pub ? new Date(pub) : null;
    const date = d && !isNaN(d) ? new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Seoul' }).format(d) : null;
    if (title && date) items.push({ date, category: '네이버 블로그', title, url: link });
  }
  return items;
}

// 카페24 스토리 수집 (policy.json의 cafe24 채널 url 사용) — 월 2회 발행 채널
// 목록이 클라이언트 렌더링이라 브라우저로 렌더 후 /kr/story/ 상세 링크를 파싱한다.
// 카드에 날짜가 없으면 "처음 발견된 날"을 발행일로 기록한다 (매일 수집하므로 ±1일 오차).
async function collectCafe24(policy) {
  const ch = (policy.channels || []).find((c) => c.id === 'cafe24');
  if (!ch || !ch.url) return null; // 미등록
  const { chromium } = require('playwright');
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1400, height: 2200 } });
    await page.goto(ch.url, { waitUntil: 'networkidle', timeout: 60000 });
    await page.waitForTimeout(4000);
    for (let i = 0; i < 4; i++) { await page.mouse.wheel(0, 2500); await page.waitForTimeout(600); }

    const bodyText = await page.evaluate(() => document.body.innerText);
    fs.mkdirSync(p('debug'), { recursive: true });
    fs.writeFileSync(p('debug', 'cafe24-last.txt'), bodyText.slice(0, 200000));

    const items = await page.evaluate(() => {
      const out = [];
      const seen = new Set();
      const NAV = ['/kr/story', '/kr/story/', '/kr/story/app', '/kr/story/diy'];
      // 카드 상단의 카테고리 라벨은 제목이 아니므로 제외
      const CAFE_CATS = ['사용팁', '업데이트', '가이드', '성공 사례 / 간증 후기', '앱 사용 레시피', '활용백서', '지식창고 / 아이디어 맛집', '요즘 트렌드'];
      document.querySelectorAll('a[href*="/kr/story/"]').forEach((a) => {
        let href = a.href || '';
        const path = href.replace(/^https?:\/\/[^/]+/, '').replace(/[?#].*$/, '').replace(/\/$/, '');
        if (NAV.indexOf(path) >= 0 || NAV.indexOf(path + '/') >= 0) return; // 목록·탭 자신
        if (!/\/kr\/story\/.+/.test(path)) return;
        const lines = (a.innerText || '').split('\n').map((s) => s.trim()).filter(Boolean);
        if (!lines.length) return;
        const dateLine = lines.find((l) => /\d{4}[.\-\/]\d{1,2}[.\-\/]\d{1,2}/.test(l)) || null;
        // 제목: 카드의 <strong class="title"> 요소를 최우선으로 사용
        const titleEl = a.querySelector('strong.title, .title');
        let title = titleEl ? (titleEl.innerText || '').replace(/\s+/g, ' ').trim() : '';
        if (!title) { // 폴백: 카테고리 라벨·날짜·숫자 줄을 제외한 첫 번째 줄
          title = lines.find((l) => l !== dateLine && CAFE_CATS.indexOf(l) < 0 && l.length >= 8 && l.length <= 150
            && !/^\d{4}[.\-\/]\d{1,2}[.\-\/]\d{1,2}/.test(l) && !/^[\d,.\s]+$/.test(l)) || null;
        }
        if (title && title.length <= 200 && !seen.has(href)) { seen.add(href); out.push({ href, dateLine, title }); }
      });
      return out;
    });

    const today = todayKST();
    return items.map((it) => ({
      date: it.dateLine ? (normDate(it.dateLine) || today) : today,
      category: '카페24 스토리',
      title: it.title,
      url: it.href,
      dateApprox: !it.dateLine || undefined, // 날짜 미표기 카드는 발견일 기준
    })).filter((x) => x.date && x.title);
  } finally {
    await browser.close();
  }
}

// 유튜브 쇼츠 수집 (채널 RSS — 발행일·조회수 포함)
// 시작점: policy의 baselineTitle 영상(「상품 소싱 전, 키워드부터!」)부터. 그보다 오래된 영상은 제외.
async function collectYoutube(policy, posts) {
  const ch = (policy.channels || []).find((c) => c.id === 'youtube');
  if (!ch || !ch.channelId) return null; // 미등록
  const rssUrl = 'https://www.youtube.com/feeds/videos.xml?channel_id=' + ch.channelId;
  const res = await fetch(rssUrl, { headers: { 'User-Agent': 'Mozilla/5.0 (compatible; seo-monitor/1.0)' } });
  if (!res.ok) throw new Error('youtube rss HTTP ' + res.status);
  const xml = await res.text();
  const items = [];
  const re = /<entry>([\s\S]*?)<\/entry>/g;
  let mm;
  while ((mm = re.exec(xml)) !== null) {
    const block = mm[1];
    const pick = (tag) => {
      const r = block.match(new RegExp('<' + tag + '>([\\s\\S]*?)<\\/' + tag + '>'));
      return r ? r[1].trim() : '';
    };
    const title = pick('title').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'");
    const vid = pick('yt:videoId');
    const pub = pick('published');
    const vm = block.match(/<media:statistics[^>]*views="(\d+)"/);
    const d = pub ? new Date(pub) : null;
    const date = d && !isNaN(d) ? new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Seoul' }).format(d) : null;
    if (title && date && vid) {
      items.push({ date, category: '유튜브 쇼츠', title, url: 'https://www.youtube.com/shorts/' + vid, views: vm ? parseInt(vm[1], 10) : null });
    }
  }
  // 시작점 필터: baselineTitle 영상의 발행일 이후만 수집
  let startDate = null;
  if (ch.baselineTitle) {
    const base = items.find((x) => x.title.indexOf(ch.baselineTitle) >= 0);
    if (base) startDate = base.date;
  }
  if (!startDate) {
    const existing = posts.filter((p) => p.category === '유튜브 쇼츠').map((p) => p.date).sort();
    startDate = existing.length ? existing[0] : (ch.startDate || todayKST());
  }
  return items.filter((x) => x.date >= startDate);
}

// 인스타그램 수집 전략 A: 공개 프로필 JSON API — 실제 발행일(taken_at_timestamp)과 캡션 제공
// (인스타 웹앱이 쓰는 공개 엔드포인트. 차단되면 null을 돌려 전략 B(브라우저)로 폴백)
async function collectInstaApi(ch) {
  const m = String(ch.url).match(/instagram\.com\/([A-Za-z0-9_.]+)/);
  if (!m) return null;
  const res = await fetch('https://i.instagram.com/api/v1/users/web_profile_info/?username=' + m[1], {
    headers: {
      'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36',
      'x-ig-app-id': '936619743392459',
      'Accept': 'application/json',
    },
  });
  if (!res.ok) { console.log('insta api HTTP', res.status); return null; }
  let j;
  try { j = await res.json(); } catch (e) { return null; }
  const edges = (((j || {}).data || {}).user || {}).edge_owner_to_timeline_media;
  if (!edges || !Array.isArray(edges.edges) || !edges.edges.length) return null;
  const out = [];
  for (const e of edges.edges) {
    const n = e.node || {};
    const ts = n.taken_at_timestamp ? new Date(n.taken_at_timestamp * 1000) : null;
    const date = ts && !isNaN(ts) ? new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Seoul' }).format(ts) : null;
    const capEdges = ((n.edge_media_to_caption || {}).edges || []);
    const cap = capEdges.length && capEdges[0].node ? String(capEdges[0].node.text || '') : '';
    let title = cap.split('\n')[0].replace(/\s+/g, ' ').trim();
    if (title.length > 150) title = title.slice(0, 147) + '…';
    if (title.length < 4) title = '(캡션 없음) ' + (n.shortcode || '');
    if (date && n.shortcode) {
      out.push({ date, category: '인스타그램', title, url: 'https://www.instagram.com/p/' + n.shortcode + '/' });
    }
  }
  console.log('insta api parsed:', out.length);
  return out.length ? out : null;
}

// 인스타그램 수집 (전략 A: 공개 JSON API → 전략 B: 브라우저 그리드 베스트에포트)
// 그리드 경로에는 날짜가 없어 "처음 발견된 날"을 발행일로 기록한다 (dateApprox).
async function collectInsta(policy) {
  const ch = (policy.channels || []).find((c) => c.id === 'insta');
  if (!ch || !ch.url) return null; // 미등록
  // 전략 A 먼저 — 성공하면 실제 발행일 포함
  try {
    const api = await collectInstaApi(ch);
    if (api) return api;
  } catch (e) { console.error('insta api failed:', e.message); }
  const { chromium } = require('playwright');
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1400, height: 2200 } });
    await page.goto(ch.url, { waitUntil: 'networkidle', timeout: 60000 });
    await page.waitForTimeout(5000);
    for (let i = 0; i < 3; i++) { await page.mouse.wheel(0, 2000); await page.waitForTimeout(800); }

    const bodyText = await page.evaluate(() => document.body.innerText);
    fs.mkdirSync(p('debug'), { recursive: true });
    fs.writeFileSync(p('debug', 'insta-last.txt'), bodyText.slice(0, 150000));

    const items = await page.evaluate(() => {
      const out = [];
      const seen = new Set();
      document.querySelectorAll('a[href*="/p/"], a[href*="/reel/"]').forEach((a) => {
        const href = (a.href || '').replace(/[?#].*$/, '');
        if (!/\/(p|reel)\/[^/]+/.test(href) || seen.has(href)) return;
        const img = a.querySelector('img');
        let title = img && img.alt ? img.alt.replace(/\s+/g, ' ').trim() : '';
        if (title.length > 150) title = title.slice(0, 147) + '…';
        if (title.length < 4) title = '(캡션 없음) ' + href.split('/').filter(Boolean).pop();
        seen.add(href);
        out.push({ href, title });
      });
      return out;
    });

    const today = todayKST();
    return items.map((it) => ({
      date: today, category: '인스타그램', title: it.title, url: it.href, dateApprox: true,
    }));
  } finally {
    await browser.close();
  }
}

async function main() {
  const meta = JSON.parse(fs.readFileSync(p('data', 'meta.json'), 'utf8'));
  const posts = JSON.parse(fs.readFileSync(p('data', 'posts.json'), 'utf8'));
  let policy = { channels: [] };
  try { policy = JSON.parse(fs.readFileSync(p('data', 'policy.json'), 'utf8')); } catch (e) {}
  const today = todayKST();
  meta.lastRun = new Date().toISOString();

  // 본 수집 실패가 네이버·카페24 수집까지 막지 않도록 격리 (v6)
  let result = null;
  try {
    result = await collectWithBrowser();
  } catch (e) {
    console.error('browser collect failed:', e.message);
  }

  if (result && result.total) {
    const totals = meta.totals.filter((t) => t.date !== today);
    totals.push({ date: today, total: result.total });
    totals.sort((a, b) => a.date.localeCompare(b.date));
    meta.totals = totals.slice(-180);
  }

  if (result) console.log('parsed posts:', result.posts.length, result.total !== null ? `(total ${result.total})` : '(total not found)');

  // 네이버 블로그 RSS 수집 (실패해도 본 수집에는 영향 없음)
  let naverPosts = [];
  let naverStatus = '';
  try {
    const nv = await collectNaver(policy);
    if (nv === null) naverStatus = ''; // URL 미등록
    else { naverPosts = nv; naverStatus = '+nv'; console.log('naver posts parsed:', nv.length); }
  } catch (e) {
    console.error('naver collect failed:', e.message);
    naverStatus = '|naver_failed';
  }

  // 카페24 스토리 수집 (실패해도 다른 수집에는 영향 없음)
  let cafePosts = [];
  let cafeStatus = '';
  try {
    const cf = await collectCafe24(policy);
    if (cf === null) cafeStatus = ''; // URL 미등록
    else { cafePosts = cf; cafeStatus = '+cf'; console.log('cafe24 posts parsed:', cf.length); }
  } catch (e) {
    console.error('cafe24 collect failed:', e.message);
    cafeStatus = '|cafe24_failed';
  }
  // 카페24 보정 (매 실행 시 자동, 멱등):
  //  1) 같은 url의 기존 글 제목이 최신 파싱 결과와 다르면 갱신 (과거 파서가 카테고리 라벨을 제목으로 저장한 경우 복구)
  //  2) 발견일 기준(dateApprox)으로 기록된 글 중 가장 오래된 1건의 발행일을 firstPostDate(예: 2026-10-22)로 고정
  try {
    const cafeCh = (policy.channels || []).find((c) => c.id === 'cafe24');
    if (cafeCh) {
      const byUrl = new Map(cafePosts.filter((x) => x.url).map((x) => [x.url, x]));
      for (const p of posts) {
        if (p.category === '카페24 스토리' && p.url && byUrl.has(p.url)) {
          const nt = byUrl.get(p.url).title;
          if (nt && nt !== p.title) { console.log('cafe24 title fixed:', p.title, '->', nt); p.title = nt; }
        }
      }
      if (cafeCh.firstPostDate) {
        const existingUrls = new Set(posts.filter((p) => p.url).map((p) => p.url));
        const all = posts.filter((p) => p.category === '카페24 스토리')
          .concat(cafePosts.filter((x) => !(x.url && existingUrls.has(x.url))));
        const approx = all.filter((p) => p.dateApprox).sort((a, b) => a.date.localeCompare(b.date));
        const hasFixed = all.some((p) => p.date === cafeCh.firstPostDate && !p.dateApprox);
        if (approx.length && !hasFixed) {
          approx[0].date = cafeCh.firstPostDate;
          delete approx[0].dateApprox;
          console.log('cafe24 first post date set to', cafeCh.firstPostDate, '-', approx[0].title);
        }
      }
    }
  } catch (e) { console.error('cafe24 backfill failed:', e.message); }

  // 유튜브 쇼츠 수집 (RSS — 실패해도 다른 수집에는 영향 없음)
  let ytPosts = [];
  let ytStatus = '';
  try {
    const yt = await collectYoutube(policy, posts);
    if (yt === null) ytStatus = ''; // 미등록
    else { ytPosts = yt; ytStatus = '+yt'; console.log('youtube posts parsed:', yt.length); }
  } catch (e) {
    console.error('youtube collect failed:', e.message);
    ytStatus = '|yt_failed';
  }

  // 인스타그램 수집 (실패해도 다른 수집에는 영향 없음)
  let igPosts = [];
  let igStatus = '';
  try {
    const ig = await collectInsta(policy);
    if (ig === null) igStatus = ''; // 미등록
    else if (ig.length === 0) { igStatus = '|ig_empty'; console.log('instagram: 0 items (로그인 월 가능성)'); }
    else {
      igPosts = ig; igStatus = '+ig'; console.log('instagram posts parsed:', ig.length);
      // 첫 수집 보정: 기존 인스타 글이 전혀 없으면 "발견일 기준(dateApprox)" 항목만 과거 게시물로 간주해
      // startDate(기본 2026-11-21)로 기록 — 현재 주 실적 오산입 방지. API 경로로 실제 날짜가 있는 항목은 그대로 둔다.
      const igCh = (policy.channels || []).find((c) => c.id === 'insta');
      if (igCh && !posts.some((pp) => pp.category === '인스타그램')) {
        const backDate = igCh.startDate || todayKST();
        let nBack = 0;
        igPosts.forEach((x) => { if (x.dateApprox) { x.date = backDate; nBack++; } });
        if (nBack) console.log('instagram initial batch backdated to', backDate, '(' + nBack + ' items)');
      }
    }
  } catch (e) {
    console.error('instagram collect failed:', e.message);
    igStatus = '|ig_failed';
  }

  const collected = (result ? result.posts : []).concat(naverPosts, cafePosts, ytPosts, igPosts);
  if (collected.length === 0) {
    meta.lastStatus = (result ? (result.total !== null ? 'parse_failed_total_ok' : 'parse_failed') : 'fetch_failed') + naverStatus + cafeStatus + ytStatus + igStatus;
  } else {
    const known = new Set(posts.map(key));
    const knownUrls = new Set(posts.filter((x) => x.url).map((x) => x.url));
    const base = result ? '' : '|site_fetch_failed';
    const fresh = collected.filter((x) => !known.has(key(x)) && !(x.url && knownUrls.has(x.url)));
    for (const f of fresh) posts.push(f);
    // 기존 글의 조회수 최신화 (효과 검증용)
    const byKey = new Map(posts.map((x) => [key(x), x]));
    for (const c of collected) {
      if (c.views == null) continue;
      const ex = byKey.get(key(c));
      if (ex) ex.views = c.views;
    }
    // 조회수 일별 스냅샷 누적 (data/views.json, 최근 120일)
    try {
      let vh = [];
      try { vh = JSON.parse(fs.readFileSync(p('data', 'views.json'), 'utf8')); } catch (e) {}
      const entries = {};
      for (const c of collected) if (c.views != null) entries[key(c)] = c.views;
      if (Object.keys(entries).length) {
        vh = vh.filter((r) => r.date !== today);
        vh.push({ date: today, entries });
        fs.writeFileSync(p('data', 'views.json'), JSON.stringify(vh.slice(-120), null, 1));
      }
    } catch (e) { console.error('views history failed:', e.message); }
    meta.lastStatus = 'ok:' + fresh.length + naverStatus + cafeStatus + ytStatus + igStatus + base;
    if (fresh.length) console.log('new posts:\n' + fresh.map((f) => `${f.date} [${f.category}] ${f.title}`).join('\n'));
  }
  // 병합 후 정리(오염·중복 제거) — 수집 결과가 없어도 기존 데이터 정리는 수행
  const before = posts.length;
  const cleaned = sanitize(posts);
  if (cleaned.length !== before) console.log('sanitized:', before, '->', cleaned.length);
  fs.writeFileSync(p('data', 'posts.json'), JSON.stringify(cleaned, null, 2));
  fs.writeFileSync(p('data', 'meta.json'), JSON.stringify(meta, null, 2));
}

main();
