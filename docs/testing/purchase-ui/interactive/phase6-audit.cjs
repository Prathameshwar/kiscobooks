const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const root = path.resolve(__dirname, '../../../..');
process.env.PLAYWRIGHT_BROWSERS_PATH ||= path.join(root, '.tools/purchase-ui-browsers');
const { chromium, firefox, webkit } = require(path.join(root, '.tools/ui-review-runner/node_modules/playwright'));
const axePath = path.join(root, '.tools/purchase-ui-audit/axe-4.10.3.min.js');
assert.equal(crypto.createHash('sha256').update(fs.readFileSync(axePath)).digest('hex'), '880970c081707360e64f34cea25ff91892f5bc95675b0776925b9709dd8a68bb');
const output = path.join(__dirname, '../phase6');
fs.mkdirSync(output, { recursive: true });
const base = process.env.PURCHASE_REVIEW_URL || 'http://127.0.0.1:4418';
const results = [];

async function audit(page, name, query, panel, nativeZoom = false) {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(`${base}/?${query}`);
  await page.getByRole('heading', { level: 1 }).waitFor();
  await page.evaluate(() => document.fonts.ready);
  if (panel === 'line') await page.getByRole('button', { name: 'Edit line 1', exact: true }).click();
  else if (panel === 'validate') await page.getByRole('button', { name: 'Save demo draft', exact: true }).click();
  else if (panel === 'review') await page.getByRole('button', { name: 'Review & submit demo', exact: true }).click();
  else if (panel) await page.getByRole('button', { name: new RegExp('^' + panel) }).click();
  // Theme changes and drawers animate; audit the completed presentation rather
  // than a frame with dark text tokens and a still-transitioning light surface.
  await page.evaluate(async () => {
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    for (const animation of document.getAnimations()) {
      if (animation.effect?.getComputedTiming().iterations !== Infinity && animation.playbackRate !== 0) animation.finish();
    }
  });
  await page.addScriptTag({ path: axePath });
  const accessibility = await page.evaluate(async () => {
    const report = await window.axe.run(document, { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa', 'best-practice'] } });
    return { violations: report.violations.map(issue => ({ id: issue.id, nodes: issue.nodes.map(node => ({ target: node.target, summary: node.failureSummary })) })), incomplete: report.incomplete.map(issue => ({ id: issue.id, targets: issue.nodes.map(node => node.target) })), passes: report.passes.length };
  });
  const geometry = await page.evaluate(() => ({
    innerWidth, innerHeight, outerWidth, dpr: devicePixelRatio, visualScale: visualViewport.scale, cssZoom: getComputedStyle(document.body).zoom,
    pageWidth: document.documentElement.scrollWidth,
    dialogs: [...document.querySelectorAll('[role="dialog"]')].map(element => ({ width: element.clientWidth, scrollWidth: element.scrollWidth, height: element.getBoundingClientRect().height })),
    compact: !!document.querySelector('[data-purchase-mobile-line]'),
  }));
  if (nativeZoom && geometry.dpr === 4 && panel) {
    assert(await page.locator('[role="dialog"]').evaluate(element => getComputedStyle(element).overflowY === 'auto'), name + ': a short zoomed dialog must scroll as a whole so its controls are not crushed between header and footer');
    const field = page.getByLabel('Supplier-declared bill total', { exact: true });
    await field.focus();
    await page.waitForFunction(() => {
      const rect = document.activeElement.getBoundingClientRect();
      return rect.top >= 0 && rect.bottom <= innerHeight;
    });
    assert(await field.evaluate(element => element.getBoundingClientRect().height >= 32), 'Zoomed field keeps its usable control height');
    await page.getByRole('button', { name: 'Cancel', exact: true }).focus();
    await page.keyboard.press('Shift+Tab');
    assert(await page.getByRole('dialog').evaluate(element => element.contains(document.activeElement)), 'Zoomed dialog retains its focus trap');
    await field.focus();
  }
  if (nativeZoom) {
    // Capture the physical browser surface directly: Playwright's CSS-scale
    // screenshot also divides a null viewport by the native zoom on this setup.
    const cdp = await page.context().newCDPSession(page);
    const capture = await cdp.send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false, fromSurface: true });
    fs.writeFileSync(path.join(output, name + '.png'), Buffer.from(capture.data, 'base64'));
    await cdp.detach();
  } else await page.screenshot({ path: path.join(output, name + '.png'), animations: 'disabled', scale: 'css' });
  // The browser-exposed accessible names, roles, live announcements and dialog tree.
  // This is automated semantic evidence, not a claim of NVDA/VoiceOver use.
  fs.writeFileSync(path.join(output, name + '.aria.txt'), await page.locator('body').ariaSnapshot());
  assert.deepEqual(errors, [], name + ' runtime errors');
  assert.deepEqual(accessibility.violations, [], name + ' accessibility violations');
  assert(accessibility.incomplete.every(issue => issue.id === 'color-contrast'), name + ' new incomplete audit requires review');
  assert(geometry.pageWidth <= geometry.innerWidth, name + ' horizontal page overflow');
  assert(geometry.dialogs.every(dialog => dialog.scrollWidth <= dialog.width && dialog.height <= geometry.innerHeight + 1), name + ' dialog overflow');
  console.log(name + ': passed');
  return { name, query, panel, geometry, accessibility, errors };
}

(async () => {
  const onlyZoom = process.env.PURCHASE_REVIEW_SCOPE === 'zoom';
  if (onlyZoom) results.push(...JSON.parse(fs.readFileSync(path.join(output, 'audit.json'), 'utf8')).results.filter(result => !result.nativeZoomPercent));
  for (const [engine, browserType] of onlyZoom ? [] : [['firefox', firefox], ['webkit', webkit]]) {
    const browser = await browserType.launch({ headless: true });
    try {
      for (const [label, width, height, query, panel] of [
        ['desktop', 1440, 1000, 'workflow=NEW'],
        ['tablet-dark', 768, 1024, 'workflow=NEW&theme=dark'],
        ['phone', 390, 844, 'workflow=NEW'],
        ['narrow-ledger', 320, 740, 'workflow=NEW&theme=ledger&locale&long'],
        ['line', 390, 844, 'workflow=NEW', 'line'],
        ['receipt', 390, 844, 'workflow=NEW&scenario=receipt', 'Goods receipt'],
        ['tracking', 390, 844, 'workflow=NEW&scenario=tracking', 'Line tracking'],
        ['evidence', 390, 844, 'workflow=NEW&theme=dark', 'Supplier bill & attachments'],
        ['validation', 390, 844, 'workflow=NEW&blank', 'validate'],
        ['submission', 390, 844, 'workflow=DRAFT', 'review'],
        ['approved', 390, 844, 'workflow=APPROVED&theme=ledger'],
      ]) {
        const page = await browser.newPage({ viewport: { width, height } });
        results.push({ engine, browser: browser.version(), ...await audit(page, engine + '-' + label, query, panel) });
        await page.close();
      }
    } finally { await browser.close(); }
  }
  for (const channel of ['msedge', 'chrome']) {
    let baselineWidth;
    for (const percent of [100, 200, 400]) {
      for (const theme of ['light', 'dark', 'ledger']) {
        // Chromium's real persisted zoom preference. The 'x' key represents the
        // default storage partition. No CSS zoom, DPR/viewport override or pinch.
        const profile = path.join(root, '.tools/purchase-ui-native-zoom', `${channel}-${percent}-${theme}`);
        fs.mkdirSync(path.join(profile, 'Default'), { recursive: true });
        fs.writeFileSync(path.join(profile, 'Default/Preferences'), JSON.stringify({ partition: { default_zoom_level: { x: Math.log(percent / 100) / Math.log(1.2) } } }));
        const context = await chromium.launchPersistentContext(profile, { channel, headless: true, viewport: null, args: ['--window-size=1440,1000'] });
        try {
          const page = context.pages()[0];
          const result = await audit(page, `${channel}-zoom-${percent}-${theme}`, `workflow=NEW&theme=${theme}`, percent === 400 ? 'Supplier bill & attachments' : undefined, true);
          assert.equal(result.geometry.outerWidth, 1440);
          assert.equal(result.geometry.dpr, percent / 100, 'Native zoom must change the device-pixel ratio');
          assert.equal(result.geometry.visualScale, 1, 'Pinch zoom must stay off');
          assert.equal(result.geometry.cssZoom, '1', 'CSS zoom must stay off');
          if (percent === 100 && !baselineWidth) baselineWidth = result.geometry.innerWidth;
          assert(Math.abs(result.geometry.innerWidth * percent / 100 - baselineWidth) <= 3, 'Native zoom must reflow the actual browser layout viewport');
          if (percent > 100) assert(result.geometry.compact, 'Native zoom must select the compact line editor');
          results.push({ engine: channel, browser: context.browser().version(), nativeZoomPercent: percent, baselineWidth, ...result });
        } finally { await context.close(); }
      }
    }
  }
  fs.writeFileSync(path.join(output, 'audit.json'), JSON.stringify({ checkedAt: new Date().toISOString(), surface: base, axe: '4.10.3', note: 'Firefox/WebKit phone/tablet viewport profiles on Windows; not physical iOS/Safari. Semantic snapshots are not a human screen-reader session. Native Chromium zoom uses isolated review profiles.', results }, null, 2) + '\n');
  console.log(`PASS ${results.length} cases: Firefox, WebKit and native Edge/Chrome 100/200/400% zoom; no automated accessibility, overflow or runtime findings.`);
})().catch(error => { console.error(error); process.exitCode = 1; });
