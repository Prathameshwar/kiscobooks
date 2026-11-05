import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

/**
 * Component tests run without CSS, so a misspelt class or token renders an unstyled page and no
 * test notices. These read the stylesheet and the components together, for the live Purchase page.
 */
const STYLES = join(__dirname, '..', '..', '..', 'packages', 'ui', 'src', 'styles');
const COMPONENTS = join(__dirname, '..', 'app', 'components');
const entry = readFileSync(join(STYLES, 'entry.css'), 'utf8');
const MARKER = '/* ---------- the live Purchase page ---------- */';
const section = entry.slice(entry.indexOf(MARKER));
const tokens = readdirSync(STYLES).filter(file => /^(tokens|theme-light|theme-dark|theme-ledger)\.css$/.test(file))
  .map(file => readFileSync(join(STYLES, file), 'utf8')).join('\n');
const sources = ['PurchasePageHeader', 'PurchaseDraftsDrawer', 'PurchaseTermsCard', 'PurchaseTaxSection', 'PurchaseCalculationCard', 'PurchaseLifecycle', 'PurchaseDuplicateBill', 'PurchaseEntryConnected', 'PurchaseWorkspace', 'PurchaseWorkspaceHeader', 'PurchaseSupplierBalance']
  .map(name => [name, readFileSync(join(COMPONENTS, name + '.tsx'), 'utf8')] as const);

describe('live Purchase page styles', () => {
  it('has its own section in the shared entry stylesheet', () => expect(entry.indexOf(MARKER)).toBeGreaterThan(0));

  it('names no literal colour, so all three palettes apply', () => {
    expect(section).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
    expect(section).not.toMatch(/\b(?:rgb|rgba|hsl|hsla|oklch|color-mix)\(/);
  });

  it('uses only design tokens that exist in the shared token and palette files', () => {
    const used = [...new Set([...section.matchAll(/var\((--janso-[a-z0-9-]+)/g)].map(match => match[1]!))];
    expect(used.length).toBeGreaterThan(10);
    const missing = used.filter(token => !new RegExp(`${token}\\s*:`).test(tokens));
    expect(missing).toEqual([]);
  });

  it('styles every Purchase page class the components emit', () => {
    const emitted = new Set<string>();
    for (const [, source] of sources) for (const match of source.matchAll(/janso-(?:purchase-[a-z0-9_-]+|entry-workspace__layout--single)/g)) emitted.add(match[0]);
    expect(emitted.size).toBeGreaterThan(10);
    const defined = new Set([...entry.matchAll(/\.(janso-[A-Za-z0-9_-]+)/g)].map(match => match[1]!));
    expect([...emitted].filter(name => !defined.has(name))).toEqual([]);
  });

  it('has no Purchase page rule that no component uses', () => {
    const emitted = new Set<string>();
    for (const [, source] of sources) for (const match of source.matchAll(/janso-purchase-[a-z0-9_-]+/g)) emitted.add(match[0]);
    const defined = [...new Set([...section.matchAll(/\.(janso-purchase-[a-z0-9_-]+)/g)].map(match => match[1]!))];
    expect(defined.filter(name => !emitted.has(name))).toEqual([]);
  });

  it('uses logical, not physical, edges, so the page mirrors in a right-to-left language', () => {
    expect(section).not.toMatch(/\b(?:margin|padding|border)-(?:left|right)\b/);
    expect(section).not.toMatch(/\b(?:left|right)\s*:/);
    expect(section).not.toMatch(/\b(?:padding|margin):\s*(?:var\([^)]+\)\s+){3}var\(/);
  });

  it('keeps the track states distinguishable by more than colour', () => {
    const track = sources.find(([name]) => name === 'PurchaseLifecycle')![1];
    expect(track).toContain('janso-purchase-track__mark');
    expect(track).toContain('janso-visually-hidden');
    for (const state of ['done', 'current', 'stopped']) expect(section).toContain(`data-state='${state}'`);
  });

  it('collapses its twelve-column grid by the frame width, not the window', () => {
    expect(section).toMatch(/@container \(max-width: 60rem\)[^}]*janso-purchase-fields/s);
    expect(section).toMatch(/@container \(max-width: 42rem\)/);
    expect(section).not.toMatch(/@media \(max-width/);
  });
});
