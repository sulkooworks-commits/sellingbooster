// 셀링부스터 블로그 일일 수집 스크립트 (GitHub Actions에서 실행)
// v2: Playwright 브라우저 렌더링 기반 — 이 사이트는 클라이언트 렌더링(Nuxt)이라
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
        const title = lines
          .filter((l) => l !== category && l !== dateLine && l.length >= 8 && !/^\d/.test(l))
          .sort((x, y) => y.length - x.length)[0] || null;
        if (category && dateLine && title && !seen.has(href)) {
          seen.add(href);
          out.push({ href, category, dateLine, title });
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

async function main() {
  const meta = JSON.parse(fs.readFileSync(p('data', 'meta.json'), 'utf8'));
  const posts = JSON.parse(fs.readFileSync(p('data', 'posts.json'), 'utf8'));
  let policy = { channels: [] };
  try { policy = JSON.parse(fs.readFileSync(p('data', 'policy.json'), 'utf8')); } catch (e) {}
  const today = todayKST();
  meta.lastRun = new Date().toISOString();

  let result;
  try {
    result = await collectWithBrowser();
  } catch (e) {
    console.error('browser collect failed:', e.message);
    meta.lastStatus = 'fetch_failed';
    fs.writeFileSync(p('data', 'meta.json'), JSON.stringify(meta, null, 2));
    process.exit(0); // 실패해도 워크플로는 성공 처리(메타 커밋)
  }

  if (result.total) {
    const totals = meta.totals.filter((t) => t.date !== today);
    totals.push({ date: today, total: result.total });
    totals.sort((a, b) => a.date.localeCompare(b.date));
    meta.totals = totals.slice(-180);
  }

  console.log('parsed posts:', result.posts.length, result.total !== null ? `(total ${result.total})` : '(total not found)');

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

  const collected = result.posts.concat(naverPosts);
  if (collected.length === 0) {
    meta.lastStatus = (result.total !== null ? 'parse_failed_total_ok' : 'parse_failed') + naverStatus;
  } else {
    const known = new Set(posts.map(key));
    const fresh = collected.filter((x) => !known.has(key(x)));
    for (const f of fresh) posts.push(f);
    posts.sort((a, b) => a.date.localeCompare(b.date));
    meta.lastStatus = 'ok:' + fresh.length + naverStatus;
    if (fresh.length) console.log('new posts:\n' + fresh.map((f) => `${f.date} [${f.category}] ${f.title}`).join('\n'));
    fs.writeFileSync(p('data', 'posts.json'), JSON.stringify(posts, null, 2));
  }
  fs.writeFileSync(p('data', 'meta.json'), JSON.stringify(meta, null, 2));
}

main();
