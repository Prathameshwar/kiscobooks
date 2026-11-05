import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { renderToStaticMarkup } from 'react-dom/server';
import { expect, it } from 'vitest';
import { DesignerShell } from '../app/(editor)/invoice-designer/DesignerShell';
import { SAMPLE_TEMPLATES } from '../app/(editor)/invoice-designer/sample-templates';
const { chromium } = createRequire(resolve('../../../.tools/ui-review-runner/package.json'))('playwright');
const css = ['tokens.css', 'theme-light.css', 'janso-ui.css', 'canvas-tokens.css', 'designer.css'].map(name => readFileSync(resolve('../../packages/ui/src/styles', name), 'utf8')).join('\n');
it.each([1440, 768, 390])('keeps the designer stage and toolbar usable at %ipx', async width => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width, height: 900 } });
    const html = renderToStaticMarkup(<DesignerShell templates={SAMPLE_TEMPLATES} initialTemplateId="tpl-gst-a4" />);
    await page.setContent('<!doctype html><html data-theme="light"><head><style>' + css + '</style></head><body class="janso-root">' + html + '</body></html>');
    const geometry = await page.evaluate(() => {
      const stage = document.querySelector('.janso-editor__stage')!.getBoundingClientRect();
      const toolbar = document.querySelector('.janso-editor__toolbar')!.getBoundingClientRect();
      const clipped = [...document.querySelectorAll('.janso-editor__toolbar button,.janso-editor__toolbar select')].filter(el => {
        const r = el.getBoundingClientRect();
        return r.width > 0 && (r.left < 0 || r.right > innerWidth + 1 || r.bottom > toolbar.bottom + 1);
      }).map(el => el.getAttribute('aria-label') || el.textContent);
      return { stageWidth: stage.width, stageHeight: stage.height, clipped };
    });
    expect(geometry.stageWidth).toBeGreaterThanOrEqual(width < 1100 ? width - 2 : 400);
    expect(geometry.stageHeight).toBeGreaterThan(400);
    expect(geometry.clipped).toEqual([]);
  } finally { await browser.close(); }
}, 60000);
