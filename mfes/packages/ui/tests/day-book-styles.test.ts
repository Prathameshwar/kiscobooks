import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { expect, it } from 'vitest';

const styles = join(__dirname, '..', 'src', 'styles');
const css = readFileSync(join(styles, 'day-book.css'), 'utf8').replace(/\/\*[\s\S]*?\*\//g, '');
it('resolves every Day Book palette and dimension token and preserves the standalone print stylesheet', () => {
  const sources = ['tokens.css', 'theme-light.css', 'theme-dark.css', 'theme-ledger.css'].map(name => readFileSync(join(styles, name), 'utf8')).join('\n');
  const defined = new Set([...sources.matchAll(/(--janso-[\w-]+)\s*:/g)].map(match => match[1]));
  for (const match of css.matchAll(/var\((--janso-[\w-]+)/g)) expect(defined.has(match[1]), match[1]).toBe(true);
  expect(css).not.toMatch(/#[\da-f]{3,8}\b|\brgba?\(|\bhsla?\(/i);
  expect(readFileSync(join(styles, 'report.css'), 'utf8')).toContain('.report-document');
});
it('keeps labels aligned, report headings sticky and mobile filters and touch targets usable', () => {
  expect(css).toContain('.janso-day-book .janso-field + .janso-field { margin-block-start: 0; }');
  expect(css).toContain("data-mobile-open='false'");
  expect(css).toContain('--janso-control-h: var(--janso-space-7)');
  expect(css).toMatch(/thead[^}]*position:\s*sticky/);
  expect(css).toContain('.janso-day-book__entry-scroll:focus-visible');
});
