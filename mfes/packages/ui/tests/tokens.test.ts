/**
 * System-level tests for the token architecture (docs/design-system.md §8).
 *
 * These read the stylesheets as text on purpose. Three palettes stay in step only if
 * something mechanical checks them — "we were careful" is how the second theme ends up
 * missing a key and silently inheriting a light value, or how one hardcoded hex survives
 * a refactor and stays white in dark mode.
 */
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const STYLES = join(__dirname, '..', 'src', 'styles');
const COMPONENTS = join(__dirname, '..', 'src', 'components');

const THEME_FILES = ['theme-light.css', 'theme-dark.css', 'theme-ledger.css'] as const;

/** Every stylesheet that must contain no colour value of its own. */
const COLOUR_FREE = [
  'tokens.css',
  'canvas-tokens.css',
  'janso-ui.css',
  'theme.css',
  'shell.css',
  'data.css',
  'search-select.css',
  'file-upload.css',
  'chart.css',
  'designer.css',
  'controls.css',
  'entry.css',
  'overlay.css',
  'table.css',
] as const;

/**
 * The documented exceptions (design-system §1): the logomark carries its own gradient so
 * it needs no context, and third-party brand glyphs have mandated colours.
 */
const COLOUR_ALLOWED_COMPONENTS = new Set(['JansoMark.tsx', 'icons.tsx']);

const COLOUR_LITERAL = /#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(/;

function read(dir: string, file: string): string {
  return readFileSync(join(dir, file), 'utf8');
}

it('gives disabled secondary buttons a muted theme state while preserving busy styling', () => {
  const css = read(STYLES, 'janso-ui.css');
  const state = css.match(/\.janso-btn--ghost:disabled:not\(\[aria-busy='true'\]\)\s*\{([^}]+)\}/)?.[1];
  expect(state).toBeDefined();
  expect(state).toContain('var(--janso-disabled-surface)');
  expect(state).toContain('var(--janso-disabled-ink)');
  expect(state).toContain('cursor: not-allowed');
});

/** Custom-property declarations in a file, as a `--janso-*` name set. */
function tokenNames(css: string): Set<string> {
  return new Set([...css.matchAll(/^\s*(--janso-[a-z0-9-]+)\s*:/gm)].map((m) => m[1] as string));
}

describe('token architecture', () => {
  it('keeps tokens.css free of colour — type, space and radius are theme-invariant', () => {
    const lines = read(STYLES, 'tokens.css').split('\n');
    const offenders = lines
      .map((line, i) => ({ line, n: i + 1 }))
      .filter(({ line }) => COLOUR_LITERAL.test(line));
    expect(offenders).toEqual([]);
  });

  it.each(COLOUR_FREE)('%s declares no colour literal — every colour is a token', (file) => {
    const offenders = read(STYLES, file)
      .split('\n')
      .map((line, i) => `${file}:${i + 1}: ${line.trim()}`)
      .filter((entry) => COLOUR_LITERAL.test(entry.slice(entry.indexOf(': ') + 2)));
    expect(offenders).toEqual([]);
  });

  it('defines the identical token key set in all three palettes', () => {
    const sets = THEME_FILES.map((file) => ({ file, keys: tokenNames(read(STYLES, file)) }));
    const canonical = sets[0]!;

    expect(canonical.keys.size).toBeGreaterThan(50);

    for (const { file, keys } of sets.slice(1)) {
      const missing = [...canonical.keys].filter((k) => !keys.has(k));
      const extra = [...keys].filter((k) => !canonical.keys.has(k));
      expect({ file, missing, extra }).toEqual({ file, missing: [], extra: [] });
    }
  });

  it('scopes each palette to its own data-theme attribute', () => {
    for (const file of THEME_FILES) {
      const theme = file.replace('theme-', '').replace('.css', '');
      expect(read(STYLES, file)).toContain(`[data-theme='${theme}']`);
    }
  });

  it('falls back to light when no data-theme is set, so nothing renders unstyled', () => {
    expect(read(STYLES, 'theme-light.css')).toContain(':root:not([data-theme])');
  });

  it('leaves colour literals only in the components documented as owning their colour', () => {
    const offenders = readdirSync(COMPONENTS)
      .filter((file) => file.endsWith('.tsx') && !COLOUR_ALLOWED_COMPONENTS.has(file))
      .filter((file) => COLOUR_LITERAL.test(read(COMPONENTS, file)));
    expect(offenders).toEqual([]);
  });
});


it('uses the locally hosted font without a blocking external stylesheet import', () => {
  const css = readFileSync(join(__dirname, '..', 'src', 'styles', 'tokens.css'), 'utf8');
  expect(css).not.toMatch(/@import\s+(?:url\()?['"]?https?:/);
});
