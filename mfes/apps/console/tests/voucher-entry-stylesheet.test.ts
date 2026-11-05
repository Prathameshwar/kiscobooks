import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { dirname, join, relative, resolve, sep } from 'node:path';
import { describe, expect, it } from 'vitest';

/*
 * The Sales and Purchase entry workspaces are styled by `entry.css`, which is deliberately not in
 * the root layout. Every route that renders one has to sit under a layout that imports it, or the
 * page renders its markup with no styling at all — which is what `/vouchers/entry` did.
 */
const APP = resolve(__dirname, '..', 'app');
const ENTRY_WORKSPACES = /\b(SalesEntryConnected|PurchaseEntryConnected|SalesEntryPage|PurchaseEntryPage)\b/;
const ENTRY_STYLESHEET = "@janso/ui/styles/entry.css";

function pages(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap(item => {
    const path = join(dir, item.name);
    if (item.isDirectory()) return pages(path);
    return item.name === 'page.tsx' ? [path] : [];
  });
}

/** The page's own folder up to `app/`: the layouts Next applies to it, innermost first. */
function layouts(page: string): string[] {
  const found: string[] = [];
  for (let dir = dirname(page); dir.startsWith(APP); dir = dirname(dir)) {
    const layout = join(dir, 'layout.tsx');
    if (existsSync(layout)) found.push(layout);
    if (dir === APP) break;
  }
  return found;
}

const rendering = pages(APP).filter(page => ENTRY_WORKSPACES.test(readFileSync(page, 'utf8')));

describe('the entry stylesheet', () => {
  it('finds the one route that renders an entry workspace, and it is not the generic selection route', () => {
    const names = rendering.map(page => relative(APP, page).split(sep).join('/'));
    expect(names).toContain('vouchers/new/[kind]/page.tsx');
    // two routes for one screen is how one of them lost its styling: Sales and Purchase live in one place
    expect(names).not.toContain('vouchers/entry/page.tsx');
  });

  it.each(rendering.map(page => [relative(APP, page).split(sep).join('/'), page] as const))('is loaded for %s', (_name, page) => {
    const loaded = layouts(page).some(layout => readFileSync(layout, 'utf8').includes(ENTRY_STYLESHEET));
    expect(loaded, 'no layout above this page imports ' + ENTRY_STYLESHEET).toBe(true);
  });

  it('stays out of the root layout, so ordinary pages do not carry the entry grid rules', () => {
    expect(readFileSync(join(APP, 'layout.tsx'), 'utf8')).not.toContain(ENTRY_STYLESHEET);
  });
});
