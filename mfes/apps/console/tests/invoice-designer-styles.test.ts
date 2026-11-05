/**
 * Every `janso-` class the designer's own components emit must be styled in `@janso/ui`.
 *
 * `packages/ui` has this check for its own components and says why: the component tests
 * run with `css: false`, so a misspelt class name passes every behavioural assertion and
 * renders unstyled in a browser — the one class of UI defect the rest of the suite cannot
 * see. But that check scans `packages/ui/src/components`, and most of the designer's
 * markup is here, in the editor route group. Phase 2's review found exactly this defect by
 * hand (`janso-editor__node--element` was a class name pretending to be a style); a test
 * is cheaper than finding the next one by reading.
 *
 * It also enforces the rule from the other direction: the designer styles through the
 * shared stylesheets and never its own, so a class that is not in `packages/ui/src/styles`
 * is either a typo or CSS that has been written in the wrong place.
 */
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const STYLES = join(__dirname, '..', '..', '..', 'packages', 'ui', 'src', 'styles');
const EDITOR = join(__dirname, '..', 'app', '(editor)', 'invoice-designer');

function definedClasses(): Set<string> {
  const defined = new Set<string>();
  for (const file of readdirSync(STYLES).filter((name) => name.endsWith('.css'))) {
    const css = readFileSync(join(STYLES, file), 'utf8');
    for (const match of css.matchAll(/\.(janso-[A-Za-z0-9_-]+)/g)) {
      defined.add(match[1] as string);
    }
  }
  return defined;
}

/**
 * Classes in a `className` value. Deliberately crude, the same way the `@janso/ui` check
 * is: it also picks up template-literal fragments, which is why a prefix match counts as
 * defined below.
 */
function usedClasses(): Map<string, string> {
  const used = new Map<string, string>();
  for (const file of readdirSync(EDITOR).filter((name) => name.endsWith('.tsx'))) {
    const source = readFileSync(join(EDITOR, file), 'utf8');
    for (const match of source.matchAll(/className=(?:"([^"]*)"|\{`([^`]*)`\}|\{'([^']*)'\})/g)) {
      const chunk = match[1] ?? match[2] ?? match[3] ?? '';
      for (const token of chunk.matchAll(/janso-[A-Za-z0-9_-]+/g)) {
        if (!used.has(token[0])) used.set(token[0], file);
      }
    }
  }
  return used;
}

describe('designer classes', () => {
  it('emits only classes the shared stylesheets define', () => {
    const defined = definedClasses();
    const unstyled = [...usedClasses()]
      .filter(([name]) => ![...defined].some((candidate) => candidate.startsWith(name)))
      .map(([name, file]) => `${name} (${file})`);

    expect(unstyled).toEqual([]);
  });

  it('finds classes at all, so a broken scan cannot pass silently', () => {
    const used = usedClasses();
    expect(used.size).toBeGreaterThan(30);
    expect(used.has('janso-editor__issue')).toBe(true);
    expect(used.has('janso-doc-binding')).toBe(true);
  });
});
