import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { expect, it } from 'vitest';

// CSS contracts supplement jsdom, which cannot verify browser geometry.
const css = readFileSync(resolve(__dirname, '../src/styles/data.css'), 'utf8');
it('opts into a prominent panel and stacks milestones on narrow screens', () => {
  expect(css).toMatch(/\.janso-preparation-progress\[data-variant='panel'\]\s*\{[^}]*grid-template-columns:\s*minmax\(0,1fr\)[^}]*box-shadow:\s*var\(--janso-shadow-card\)/);
  expect(css).toMatch(/@media\s*\(max-width:\s*600px\)\s*\{[^\n]*\[data-variant='panel'\] ol\s*\{[^}]*grid-template-columns:\s*minmax\(0,1fr\)/);
});
it('respects reduced motion and keeps confirmed completion visually distinct', () => {
  expect(css).toMatch(/@media\s*\(prefers-reduced-motion:\s*reduce\)\s*\{[^\n]*\[data-active='true'\] > div:first-child::before\s*\{\s*animation:\s*none/);
  expect(css).toMatch(/\[data-variant='panel'\]\[data-complete='true'\]\s*\{[^}]*var\(--janso-success-line\)[^}]*var\(--janso-success-tint\)/);
});
