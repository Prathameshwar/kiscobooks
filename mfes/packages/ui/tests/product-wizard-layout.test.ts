import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { expect, it } from 'vitest';

// jsdom does not lay out grid columns. Check the CSS contracts responsible for
// the reviewed offsets; browser geometry remains a separate verification.
const css = readFileSync(process.env.QA_PRODUCT_WIZARD_CSS ?? resolve(__dirname, '../src/styles/product-wizard.css'), 'utf8');
it('lets grid gaps own spacing and aligns field contents at the top', () => {
  expect(css).toMatch(/\.product-wizard__fields\s*\{[^}]*align-items:\s*start/);
  expect(css).toMatch(/\.product-wizard__fields > \.janso-field \+ \.janso-field\s*\{[^}]*margin-top:\s*0/);
});
it('gives the SKU editor its full row before tablet widths become cramped', () => {
  expect(css).toMatch(/@media\s*\(max-width:\s*1100px\)\s*\{\s*\.product-wizard__sku-layout\s*\{[^}]*grid-template-columns:\s*1fr/);
});
it('keeps step labels readable and actions available during long forms', () => {
  expect(css).toMatch(/\.product-wizard__step strong\s*\{[^}]*white-space:\s*normal/);
  expect(css).toMatch(/\.product-wizard__actions\s*\{[^}]*position:\s*sticky/);
});

it('lets SKU status cards fit narrow screens and wrap long codes and messages', () => {
  expect(css).toMatch(/\.product-wizard__sku-progress-grid\s*\{[^}]*grid-template-columns:\s*repeat\(auto-fit,minmax\(min\(100%,20rem\),1fr\)\)/);
  expect(css).toMatch(/\.product-wizard__sku-progress-card\s*\{[^}]*min-width:\s*0/);
  expect(css).toMatch(/\.product-wizard__sku-progress-card dd\s*\{[^}]*overflow-wrap:\s*anywhere/);
});
