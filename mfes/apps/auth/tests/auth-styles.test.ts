import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

/**
 * The Auth screens' look is a handful of decisions that are easy to undo by accident and invisible to
 * a component test (`css: false` in the vitest config). Each is pinned here against the stylesheet
 * itself: the tagline that was once set too large, colours that must come from the palettes, the
 * drawing that has to stay decoration, and the narrow layouts that must keep working.
 */
const css = readFileSync(resolve(__dirname, '../app/auth.css'), 'utf8');
const rule = (selector: string): string => {
  const start = css.indexOf(`${selector} {`);
  expect(start, `${selector} is not in auth.css`).toBeGreaterThanOrEqual(0);
  return css.slice(start, css.indexOf('\n}', start) + 2);
};
const withoutComments = css.replace(/\/\*[\s\S]*?\*\//g, '');

describe('the brand panel', () => {
  it('sets the tagline at the design system\'s auth display size, not larger', () => {
    // 32px (`--janso-text-2xl`). A bigger statement out-shouts the sign-in form the screen is for.
    const tagline = rule('.auth__tagline');
    expect(tagline).toMatch(/font-size:\s*var\(--janso-text-2xl\);/);
    expect(tagline).not.toMatch(/clamp\(|vw|[3-9]\.\d+rem/);
  });

  it('keeps the drawing out of the way: behind the text, inert, and gone on a narrow split', () => {
    const sheet = rule('.auth__brand > .auth__sheet');
    expect(sheet).toMatch(/pointer-events:\s*none;/);
    expect(sheet).toMatch(/z-index:\s*0;/);
    expect(css).toMatch(/@media \(max-width: 1180px\) \{\s*\.auth__balance \{ display: none; \}/);
  });

  it('draws the logomark once and stops when the reader asks for less motion', () => {
    expect(rule('.auth__balance :is(rect, circle)')).toMatch(/animation:\s*auth-draw/);
    const reduced = css.slice(css.indexOf('@media (prefers-reduced-motion: reduce)'));
    expect(reduced).toMatch(/\.auth__balance :is\(rect, circle\) \{ stroke-dashoffset: 0; animation: none; \}/);
    expect(reduced).toMatch(/\.auth__feature \{ opacity: 1; transform: none; animation: none; \}/);
  });
});

describe('colour and size', () => {
  it('takes every colour from the palettes — none of its own, so all three themes follow', () => {
    expect(withoutComments).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
    expect(withoutComments).not.toMatch(/\b(?:rgb|rgba|hsl|hsla|hwb|lab|lch|oklab|oklch)\(/);
  });

  it('mixes the sheet\'s rules from a palette colour, and shows less of them in the dark one', () => {
    expect(css).toMatch(/color-mix\(in srgb, var\(--janso-line\) var\(--auth-rule-mix\), transparent\)/);
    expect(css).toMatch(/\[data-theme='dark'\] \.auth__brand > \.auth__sheet \{ --auth-rule-mix: \d+%; \}/);
  });
});

describe('the form card', () => {
  it('has controls tall enough for a thumb, and a button larger than the console\'s', () => {
    expect(withoutComments).toMatch(/\.auth__form \.janso-input \{\s*min-height: 2\.75rem;/);
    expect(withoutComments).toMatch(/\.auth__form \.janso-btn--block \{\s*min-height: 2\.875rem;/);
  });

  it('runs the footer band to the card\'s edges from one padding value', () => {
    expect(rule('.auth__form')).toMatch(/--auth-pad:\s*2\.5rem;/);
    expect(rule('.auth__foot--band')).toMatch(/margin:\s*var\(--janso-space-6\) calc\(-1 \* var\(--auth-pad\)\) calc\(-1 \* var\(--auth-pad\)\);/);
  });

  it('dissolves the card and its band into the page on a phone, so the negative margins cannot overflow', () => {
    const phone = css.slice(css.indexOf('@media (max-width: 520px)'));
    expect(phone).toMatch(/--auth-pad:\s*0rem;/);
    expect(phone).toMatch(/\.auth__foot--band \{[^}]*margin-bottom:\s*0;/);
  });

  it('tucks the palette switcher into the phone header instead of giving it a row', () => {
    const narrow = css.slice(css.indexOf('@media (max-width: 860px)'), css.indexOf('@media (max-width: 520px)'));
    expect(narrow).toMatch(/\.auth__panel-bar \{\s*position: absolute;/);
    expect(narrow).toMatch(/grid-template-rows: auto 1fr auto;/);
  });
});
