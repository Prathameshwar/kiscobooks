import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

/**
 * Component tests run without CSS, so they cannot see this: a checkbox that is ticked and disabled
 * is painted with the disabled surface, and its tick is the inverse ink meant for the brand fill.
 * White on pale grey reads as an empty box — a saved, read-only "yes" shown as "no".
 */
const css = readFileSync(join(__dirname, '..', 'src', 'styles', 'janso-ui.css'), 'utf8').replace(/\/\*[\s\S]*?\*\//g, '');
/** The body of the first rule whose selector list contains `selector`. */
const rule = (selector: string) => {
  for (const block of css.matchAll(/([^{}]+)\{([^{}]*)\}/g))
    if (block[1]!.split(',').some(part => part.trim().replace(/\s+/g, ' ') === selector)) return block[2];
  return undefined;
};

describe('a disabled checkbox that is ticked', () => {
  it('draws its tick in an ink that is visible on the disabled surface', () => {
    const tick = rule('.janso-check input:disabled:checked + .janso-check__box svg');
    expect(tick, 'a rule for the ticked, disabled tick').toBeDefined();
    expect(tick).toMatch(/color:\s*var\(--janso-ink-soft\)/);
    expect(tick).not.toMatch(/ink-invert/);
  });

  it('keeps the disabled surface, so it still reads as unavailable', () => {
    const box = rule('.janso-check input:disabled + .janso-check__box');
    expect(box).toMatch(/background:\s*var\(--janso-surface-2\)/);
    const ticked = rule('.janso-check input:disabled:checked + .janso-check__box');
    expect(ticked).toMatch(/background:\s*var\(--janso-surface-2\)/);
  });
});
