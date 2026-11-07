/**
 * The wizard layout's spacing and scrolling, asserted against the stylesheet.
 *
 * Component tests run with `css: false`, so a layout rule that is missing — or that assumes
 * something about the host application's `body` — is invisible to every other test in this
 * suite. Both defects fixed here were exactly that: measured in a browser, unfindable in jsdom.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const setup = readFileSync(join(__dirname, '..', 'src/styles/setup.css'), 'utf8');
const ui = readFileSync(join(__dirname, '..', 'src/styles/janso-ui.css'), 'utf8');

it('lets the form grid own field spacing without adding stacked-field margins', () => {
  expect(setup).toMatch(/\.janso-setup__fields\s*\{[^}]*gap:\s*var\(--janso-space-4\)/);
  expect(setup).toMatch(/\.janso-setup__fields > \.janso-field \+ \.janso-field\s*\{\s*margin-top:\s*0;/);
});

describe('the wizard scrolls itself', () => {
  /*
   * `/companies/new` is a six-step form inside `apps/console`, which sets
   * `body { overflow: hidden }` so the app shell's main region owns the only scrollbar. That
   * rule reaches every shell-less route too, and `overflow: hidden` on the body propagates to
   * the viewport: the page kept its full height, nothing was clipped, and no wheel, trackpad or
   * scrollbar could move it — only programmatic scrolling and Tab-into-view still worked. Four
   * of the six steps are taller than a 768px viewport, so most of the form was unreachable.
   *
   * The layout therefore owns its scrolling, the way `.janso-shell` does, instead of trusting
   * the host's `body`.
   */
  it('keeps the frame to one viewport with a separate scrolling row', () => {
    expect(setup).toMatch(/\.janso-setup\s*\{[^}]*block-size:\s*100dvh/);
    expect(setup).toMatch(/\.janso-setup--wizard\s*\{[^}]*grid-template-rows:\s*minmax\(0, 1fr\) auto/);
    expect(setup).toMatch(/\.janso-setup__scroll\s*\{[^}]*overflow:\s*auto/);
  });

  it('gives focused fields clearance inside the actual scroll container', () => {
    expect(setup).toMatch(/\.janso-setup__scroll\s*\{[^}]*scroll-padding-block:/);
    expect(setup).not.toMatch(/html:has\(\.janso-setup\)/);
  });
});

describe('grid field containers', () => {
  /*
   * `.janso-field + .janso-field` spaces a stacked column. In a two-column row it offsets the
   * second field by 16px, which is what put "Incorporation date" below "Entity type" rather
   * than beside it; inside a group it doubled a 16px gap to 32px. `.janso-form-grid` was given
   * this reset when it was written, and these two were not.
   */
  it('reset the stacked-field margin the grid gap replaces', () => {
    expect(ui).toMatch(/\.janso-fieldpair > \.janso-field \+ \.janso-field,\s*\n\s*\.janso-fieldgroup__fields > \.janso-field \+ \.janso-field\s*\{\s*margin-top:\s*0;/);
    expect(ui).toMatch(/\.janso-form-grid > \.janso-field \+ \.janso-field\s*\{\s*margin-top:\s*0;/);
  });

  it('tops-aligns a pair, so a field with a hint does not stretch its neighbour', () => {
    expect(ui).toMatch(/\.janso-fieldpair\s*\{[^}]*align-items:\s*start/);
  });
});
