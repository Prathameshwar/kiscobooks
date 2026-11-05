import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

/** Standalone page reviews use the actual import order, palettes and self-hosted font. */
export function consoleLayoutCss() {
  const imports = [...readFileSync(resolve('app/layout.tsx'), 'utf8').matchAll(/import '@janso\/ui\/styles\/([^']+)'/g)];
  const styles = imports.map(([, name]) => {
    const css = readFileSync(resolve('../../packages/ui/src/styles', name!), 'utf8');
    if (name !== 'fonts.css') return css;
    const font = readFileSync(resolve('../../packages/ui/src/assets/fonts/InterVariable.woff2')).toString('base64');
    return css.replace('../assets/fonts/InterVariable.woff2', 'data:font/woff2;base64,' + font);
  }).join('\n');
  // There is no app shell in this fixture: the document scrolls for full-page captures.
  return styles + readFileSync(resolve('app/globals.css'), 'utf8') + readFileSync(resolve('app/console.css'), 'utf8') + '\nbody { overflow: auto; }';
}
