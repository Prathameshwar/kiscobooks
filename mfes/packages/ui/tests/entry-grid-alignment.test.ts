/**
 * A right-aligned column heading and the figure typed under it have to meet at the same edge.
 *
 * The numeric cell is a fixed-width wrapper (so a unit or provenance chip cannot widen the column)
 * inside a table cell that is often wider — a column takes the width of its heading or of its
 * widest row. `text-align: end` on the cell moves text, not a block, so without an explicit push the
 * wrapper sat at the start of the cell while the heading sat at the end: on the purchase page the
 * entered amount was about 70px left of its "Amount" heading. This reads the stylesheet because
 * the component tests run with CSS off; the measured check was made against the live page.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const css = readFileSync(join(__dirname, '..', 'src', 'styles', 'entry.css'), 'utf8');

/** The declarations of the first rule whose selector list contains `selector`, comments removed. */
function declarations(selector: string): string | null {
  const stripped = css.replace(/\/\*[\s\S]*?\*\//g, '');
  const rule = new RegExp('(?:^|\\})\\s*([^{}]*' + selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '[^{}]*)\\{([^}]*)\\}').exec(stripped);
  return rule ? (rule[2] ?? null) : null;
}

describe('numeric entry cells', () => {
  it('pushes the fixed-width numeric wrapper to the end of a right-aligned cell', () => {
    const rule = declarations("td[data-align='end'] .janso-entry-cell__numeric-wrap");
    expect(rule, 'no rule aligns the numeric wrapper inside an end-aligned cell').not.toBeNull();
    expect(rule).toMatch(/margin-inline-start:\s*auto/);
  });

  it('keeps the heading and the cell on the same end alignment', () => {
    const rule = declarations("thead th[data-align='end']");
    expect(rule).toMatch(/text-align:\s*end/);
  });

  it('keeps the numbers themselves end-aligned inside the wrapper', () => {
    expect(declarations('.janso-entry-cell--numeric')).toMatch(/text-align:\s*end/);
  });
});
