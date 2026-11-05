const path = require('node:path');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '../../../..');
const { chromium } = require(path.join(root, '.tools/ui-review-runner/node_modules/playwright'));
const output = path.join(__dirname, '../phase6');
const base = process.env.PURCHASE_REVIEW_URL || 'http://127.0.0.1:4418';
(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true, args: ['--force-renderer-accessibility'] });
  const results = [];
  try {
    for (const name of ['invoice', 'line-editor', 'validation', 'restricted']) {
      const page = await browser.newPage({ viewport: { width: name === 'invoice' ? 1440 : 390, height: 844 } });
      await page.goto(base + '/?workflow=NEW' + (name === 'validation' ? '&blank' : name === 'restricted' ? '&restricted' : ''));
      if (name === 'line-editor') {
        await page.getByRole('button', { name: 'Edit line 1', exact: true }).click();
        await page.getByLabel('Line description', { exact: true }).focus();
      } else if (name === 'validation') await page.getByRole('button', { name: 'Save demo draft', exact: true }).click();
      else if (name === 'invoice') await page.getByLabel('Supplier invoice number', { exact: true }).focus();
      else await page.getByText('Purchase costs are restricted').waitFor();
      const session = await page.context().newCDPSession(page);
      const tree = await session.send('Accessibility.getFullAXTree');
      const nodes = tree.nodes.filter(node => !node.ignored).map(node => ({ role: node.role?.value, name: node.name?.value, value: node.value?.value, properties: node.properties }));
      const focused = nodes.filter(node => node.properties?.some(property => property.name === 'focused' && property.value.value === true)).map(node => node.name);
      if (name === 'invoice') assert(nodes.some(node => node.role === 'textbox' && node.name === 'Supplier invoice number' && node.properties?.some(property => property.name === 'required' && property.value.value === true)));
      if (name === 'line-editor') {
        assert(nodes.some(node => node.role === 'dialog' && node.name === 'Edit purchase line 1'));
        assert(focused.includes('Line description'));
      }
      if (name === 'validation') assert(nodes.some(node => node.role === 'combobox' && node.name === 'Supplier' && node.properties?.some(property => property.name === 'invalid' && property.value.value === 'true')));
      if (name === 'restricted') {
        assert(nodes.some(node => node.role === 'heading' && node.name === 'Purchase voucher'));
        assert(!nodes.some(node => node.name === 'Supplier invoice number' || node.name === 'Bill total'));
      }
      fs.writeFileSync(path.join(output, name + '.browser-ax.json'), JSON.stringify(nodes, null, 2) + '\n');
      results.push({ name, nodes: nodes.length, focused, passed: true });
      await page.close();
    }
    fs.writeFileSync(path.join(output, 'accessibility.json'), JSON.stringify({ checkedAt: new Date().toISOString(), browser: browser.version(), method: 'Chromium Accessibility.getFullAXTree with renderer accessibility enabled; roles, required/invalid/focused properties, dialog names and denied data withholding. Browser semantic checks, not an OS screen-reader speech session.', humanScreenReader: 'NVDA is not installed; no NVDA/VoiceOver or physical iOS acceptance claimed.', results }, null, 2) + '\n');
    console.log('PASS: four actual browser accessibility-tree checks.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
