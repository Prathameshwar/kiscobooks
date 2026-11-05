/* Static P1 review only. Uses the workspace's existing browser review installation. */
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '../../..');
const {chromium} = require(path.join(root, '.tools/ui-review-runner/node_modules/playwright'));

(async () => {
  const browser = await chromium.launch({channel: 'msedge', headless: true});
  const results = [];
  try {
    for (const name of ['desktop-light', 'desktop-dark', 'desktop-ledger', 'mobile-light']) {
      const mobile = name.startsWith('mobile');
      const page = await browser.newPage({viewport: {width: mobile ? 390 : 1440, height: mobile ? 1400 : 1080}, deviceScaleFactor: 1});
      await page.route('**/*', route => {
        const protocol = new URL(route.request().url()).protocol;
        return protocol === 'file:' || protocol === 'data:' ? route.continue() : route.abort();
      });
      // An HTML host avoids Edge's standalone-SVG screenshot timeout.
      const svg = fs.readFileSync(path.join(__dirname, name + '.svg'), 'utf8');
      await page.setContent('<!doctype html><html><head><meta charset="utf-8"><style>html,body{margin:0;padding:0}svg{display:block}</style></head><body>' + svg + '</body></html>');
      await page.evaluate(() => document.fonts.ready);
      const checks = await page.evaluate(() => {
        const svg = document.querySelector('svg');
        const bounds = svg.getBoundingClientRect();
        const textNodes = [...svg.querySelectorAll('text')];
        const backgrounds = [...svg.querySelectorAll('rect')];
        function luminance(hex) {
          const channels = hex.match(/[0-9a-f]{2}/gi).map(value => parseInt(value, 16) / 255);
          const linear = channels.map(value => value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4);
          return linear[0] * 0.2126 + linear[1] * 0.7152 + linear[2] * 0.0722;
        }
        const overflow = [], contrast = [], overlaps = [];
        for (const node of textNodes) {
          const box = node.getBoundingClientRect();
          if (box.left < bounds.left || box.top < bounds.top || box.right > bounds.right || box.bottom > bounds.bottom) overflow.push(node.textContent);
          const x = box.left + box.width / 2, y = box.top + box.height / 2;
          const background = backgrounds.filter(rect => {
            const b = rect.getBoundingClientRect();
            return !!(rect.compareDocumentPosition(node) & Node.DOCUMENT_POSITION_FOLLOWING) && x >= b.left && x <= b.right && y >= b.top && y <= b.bottom;
          }).at(-1);
          const foreground = luminance(node.getAttribute('fill'));
          const behind = luminance(background.getAttribute('fill'));
          const ratio = (Math.max(foreground, behind) + 0.05) / (Math.min(foreground, behind) + 0.05);
          const size = Number(node.getAttribute('font-size')), weight = Number(node.getAttribute('font-weight'));
          const required = size >= 24 || size >= 18.67 && weight >= 700 ? 3 : 4.5;
          if (ratio < required) contrast.push({text: node.textContent, ratio, required});
        }
        for (let i = 0; i < textNodes.length; i++) {
          const a = textNodes[i].getBoundingClientRect();
          for (let j = i + 1; j < textNodes.length; j++) {
            const b = textNodes[j].getBoundingClientRect();
            if (Math.min(a.right, b.right) - Math.max(a.left, b.left) > 1 && Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top) > 1) overlaps.push([textNodes[i].textContent, textNodes[j].textContent]);
          }
        }
        return {text_nodes: textNodes.length, overflow, contrast, overlaps};
      });
      await page.screenshot({path: path.join(__dirname, name + '.png'), fullPage: true});
      results.push({composition: name, viewport: mobile ? '390x1400' : '1440x1080', ...checks});
      await page.close();
    }
    fs.writeFileSync(path.join(__dirname, 'render-review.json'), JSON.stringify({scope: 'Static P1 compositions only; not application or WCAG certification.', browser: browser.version(), fixture: 'PU02', results}, null, 2) + '\n');
    for (const result of results) {
      assert.deepEqual(result.overflow, [], result.composition + ': text outside composition');
      assert.deepEqual(result.contrast, [], result.composition + ': text contrast');
      assert.deepEqual(result.overlaps, [], result.composition + ': overlapping text');
    }
    console.log('PASS: four static browser renders; text bounds, text contrast and text overlap checks. PNGs and render-review.json written.');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
