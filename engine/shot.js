// 复用单浏览器，把 deck.html 的 N 屏截成精确 W×H PNG（v2: 横屏 1920x1080）。
// env: DECK_PATH(文件路径), N(屏数), OUT_DIR(输出目录), W, H。
// 截图前等待 window.__deckReady（fonts.ready + WebGL 首帧），保证背景/字体已就绪。
const { chromium } = require('playwright');

const DECK = process.env.DECK_PATH;
const N = parseInt(process.env.N || '0', 10);
const OUT = process.env.OUT_DIR;
const W = parseInt(process.env.W || '1920', 10);
const H = parseInt(process.env.H || '1080', 10);
if (!DECK || !N || !OUT) { console.error('ERR missing env DECK_PATH/N/OUT_DIR'); process.exit(2); }

const URL = 'file://' + encodeURI(DECK);

(async () => {
  const browser = await chromium.launch({
    headless: true,
    args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader',
           '--ignore-gpu-blocklist', '--enable-webgl'],
  });
  const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });
  for (let c = 1; c <= N; c++) {
    await page.goto(URL + '?slide=' + c, { waitUntil: 'load' });
    try { await page.waitForFunction(() => window.__deckReady === true, { timeout: 9000 }); }
    catch (e) { /* fall through, fonts/webgl fallback still render */ }
    await page.waitForTimeout(650); // 让 WebGL 动一点，静止态稳定
    await page.screenshot({ path: OUT + '/chapter_' + c + '.png', clip: { x: 0, y: 0, width: W, height: H } });
    console.log('SHOT ' + c);
  }
  await browser.close();
  console.log('ALL_DONE');
})().catch((e) => { console.error('ERR', e && e.message); process.exit(3); });
