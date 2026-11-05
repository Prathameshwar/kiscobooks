/**
 * Contrast, computed rather than claimed (design-system §2.4, §7 — "each is a test").
 *
 * §2.4 has always stated the gates — body text ≥ 4.5:1, large text and UI boundaries ≥ 3:1,
 * in all three palettes — and nothing checked them. That is decision log #13's failure mode
 * exactly: the chart tokens were hue-picked, the doc asserted they passed, and they did not.
 * Anything about colour that can be computed gets computed, or the next re-tint quietly
 * reintroduces a 2.6:1 axis label.
 *
 * The theme files are read as text, never imported: these are the values that ship, and
 * jsdom resolves no custom properties anyway.
 *
 * WHY THE PAIRING TABLE IS WRITTEN OUT BY HAND, rather than crossing every ink with every
 * surface: a cross-product asserts pairings that never render — `--janso-warn-ink` on
 * `--janso-success-tint`, `--janso-chart-6` on `--janso-danger-tint` — and every one of them
 * would then need an individual suppression. A suppression list is a place for a real
 * pairing to hide. So each row below is a pairing some stylesheet actually produces, and it
 * carries the gate that *that use* owes: 4.5 where the token is text, 3 where it is the
 * boundary of a control or a graphic that carries meaning. Adding a row is the cost of
 * introducing a new pairing, and that is the point.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const STYLES = join(__dirname, '..', 'src', 'styles');

const THEMES = ['light', 'dark', 'ledger'] as const;
type Theme = (typeof THEMES)[number];

/** The gates of §2.4. `TEXT` is body text; `GRAPHIC` is large text, a control edge, a mark. */
const TEXT = 4.5;
const GRAPHIC = 3;

type Rgb = readonly [number, number, number];

// ---------- WCAG 2.1 relative luminance and contrast ratio ----------

/** 8-bit sRGB channel → linear-light, per WCAG 2.1 relative-luminance definition. */
function toLinear(channel: number): number {
  const c = channel / 255;
  return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

function luminance([r, g, b]: Rgb): number {
  return 0.2126 * toLinear(r) + 0.7152 * toLinear(g) + 0.0722 * toLinear(b);
}

function contrast(a: Rgb, b: Rgb): number {
  const la = luminance(a);
  const lb = luminance(b);
  const [lighter, darker] = la > lb ? [la, lb] : [lb, la];
  return (lighter + 0.05) / (darker + 0.05);
}

/**
 * The gates are stated to one decimal ("4.5:1", "3:1") and that is the precision they are
 * compared at, so a measured 4.48 counts as meeting 4.5. This absorbs the rounding in the
 * theme files' own recorded numbers and nothing more — a real miss (3.95 against 4.5) is
 * half a point away and still fails.
 */
function meets(ratio: number, gate: number): boolean {
  return Math.round(ratio * 10) / 10 >= gate;
}

// ---------- colour parsing ----------

function parseHex(hex: string): Rgb {
  const h = hex.replace('#', '');
  const full =
    h.length === 3
      ? h
          .split('')
          .map((c) => c + c)
          .join('')
      : h;
  return [
    Number.parseInt(full.slice(0, 2), 16),
    Number.parseInt(full.slice(2, 4), 16),
    Number.parseInt(full.slice(4, 6), 16),
  ];
}

/** `rgba(r, g, b, a)` composited over an opaque backdrop — a translucent token has no
 * contrast of its own, only one against the thing stated to be behind it. */
function compositeRgba(value: string, backdrop: Rgb): Rgb {
  const parts = (value.match(/rgba?\(([^)]+)\)/)?.[1] ?? '')
    .split(',')
    .map((p) => Number.parseFloat(p.trim()));
  const alpha = parts.length > 3 ? (parts[3] as number) : 1;
  return [0, 1, 2].map(
    (i) => (parts[i] as number) * alpha + (backdrop[i] as number) * (1 - alpha),
  ) as unknown as Rgb;
}

/** Every `--janso-*` declaration in one theme file, as written. */
function declarations(theme: Theme): Map<string, string> {
  const css = readFileSync(join(STYLES, `theme-${theme}.css`), 'utf8');
  const map = new Map<string, string>();
  for (const match of css.matchAll(/(--janso-[a-z0-9-]+)\s*:\s*([^;]+);/g)) {
    map.set(match[1] as string, (match[2] as string).trim());
  }
  return map;
}

const TOKENS: Record<Theme, Map<string, string>> = {
  light: declarations('light'),
  dark: declarations('dark'),
  ledger: declarations('ledger'),
};

/** A token's colour, composited over `backdrop` when the token is translucent. */
function resolve(theme: Theme, token: string, backdrop: Rgb): Rgb {
  const value = TOKENS[theme].get(token);
  if (value === undefined) throw new Error(`${theme}: ${token} is not declared`);
  if (value.startsWith('#')) return parseHex(value);
  if (value.startsWith('rgb')) return compositeRgba(value, backdrop);
  throw new Error(`${theme}: ${token} is not a flat colour (${value})`);
}

/** The colour stops of a gradient token, in order. */
function gradientStops(theme: Theme, token: string): Rgb[] {
  const value = TOKENS[theme].get(token);
  if (value === undefined) throw new Error(`${theme}: ${token} is not declared`);
  const stops = [...value.matchAll(/#[0-9a-fA-F]{3,8}\b/g)].map((m) => parseHex(m[0]));
  if (stops.length < 2) throw new Error(`${theme}: ${token} has no colour stops`);
  return stops;
}

/**
 * The layers of a `box-shadow` token: the drop shadow cast outside the box, and the `inset`
 * edge drawn just inside it. A dark palette spends its elevation on the second, because the
 * first does not render on near-black — so both have to be readable separately.
 */
function shadowLayers(theme: Theme, token: string): { drop?: string; inset?: string } {
  const value = TOKENS[theme].get(token);
  if (value === undefined) throw new Error(`${theme}: ${token} is not declared`);
  const layers = value.split(/,(?![^(]*\))/).map((layer) => layer.trim());
  const colour = (layer: string) => layer.match(/rgba?\([^)]*\)/)?.[0];
  return {
    drop: colour(layers.find((layer) => !layer.startsWith('inset')) ?? ''),
    inset: colour(layers.find((layer) => layer.startsWith('inset')) ?? ''),
  };
}

/** The alpha of an `rgba()` value, or 1 for an opaque one. */
function alphaOf(value: string): number {
  const parts = value.match(/rgba?\(([^)]+)\)/)?.[1]?.split(',') ?? [];
  return parts.length > 3 ? Number.parseFloat(parts[3] as string) : 1;
}

// ---------- the pairings ----------

type Pair = {
  /** The foreground token. */
  fg: string;
  /** What is behind it. */
  bg: string;
  gate: number;
  /** Where this pairing comes from — so a future edit can find the rule it protects. */
  why: string;
};

const SURFACES = ['--janso-paper', '--janso-surface', '--janso-surface-2', '--janso-overlay'];

const PAIRS: Pair[] = [
  ...SURFACES.flatMap((bg) => ['--janso-brand-ink', '--janso-wordmark-books'].map((fg) => ({
    fg, bg, gate: TEXT, why: 'KiscoBooks wordmark in the rail and compact header',
  }))),
  // — Text on every surface it can land on. The four surfaces are the page, a card, a tile
  //   nested in a card, and a menu, and body copy appears on all four.
  ...SURFACES.map((bg) => ({ fg: '--janso-ink', bg, gate: TEXT, why: 'body text' })),
  ...SURFACES.map((bg) => ({
    fg: '--janso-ink-soft',
    bg,
    gate: TEXT,
    why: 'secondary text — lede, hints, card subtitles, chart ticks and the chart annotation',
  })),
  // `ink-faint` carries 11px overlines, input placeholders and list ranks…
  {
    fg: '--janso-ink-faint',
    bg: '--janso-paper',
    gate: TEXT,
    why: 'page overlines and the footer copyright, on the page surface',
  },
  {
    fg: '--janso-ink-faint',
    bg: '--janso-surface',
    gate: TEXT,
    why: 'rail section labels, input placeholders, list-row ranks, on a card or the rail',
  },
  // …and it is held to the text gate on `surface-2` and `overlay` too. These two were
  // briefly relaxed to the graphic gate on the argument that only glyphs land there, but the
  // token was then lifted so it clears 4.5 on every surface — and the argument was fragile:
  // it depended on nobody ever putting `ink-faint` text on a nested tile or in a menu, which
  // is not a property anything enforces.
  {
    fg: '--janso-ink-faint',
    bg: '--janso-surface-2',
    gate: TEXT,
    why: 'the org code and nested-tile labels, on a nested surface',
  },
  {
    fg: '--janso-ink-faint',
    bg: '--janso-overlay',
    gate: TEXT,
    why: 'user-menu item labels and icons, on a popover',
  },

  // — Disabled. Kept at the text gate rather than leaning on WCAG's inactive-component
  //   exemption: a disabled total is still a number someone needs to read.
  {
    fg: '--janso-disabled-ink',
    bg: '--janso-disabled-surface',
    gate: TEXT,
    why: 'a disabled input or button',
  },

  // — `SearchSelect` (§5.5). Its list is an overlay, and its highlighted row introduces a
  //   surface no other component uses — `--janso-selected` — so every colour that lands on it
  //   is measured rather than assumed.
  {
    fg: '--janso-ink',
    bg: '--janso-selected',
    gate: TEXT,
    why: 'the highlighted option in a SearchSelect list',
  },
  {
    fg: '--janso-ink-soft',
    bg: '--janso-selected',
    gate: TEXT,
    why: 'the meta line of a highlighted option — a code, a place, a status',
  },
  {
    fg: '--janso-brand-ink',
    bg: '--janso-selected',
    gate: TEXT,
    why: 'an already-selected option that is also highlighted',
  },
  {
    fg: '--janso-brand',
    bg: '--janso-overlay',
    gate: TEXT,
    why: 'the “Add …” create row, and the check mark on a selected option',
  },
  {
    fg: '--janso-brand',
    bg: '--janso-selected',
    gate: GRAPHIC,
    why: 'the 2px marker on the highlighted row — the non-colour cue that survives greyscale',
  },
  {
    fg: '--janso-disabled-ink',
    bg: '--janso-overlay',
    gate: TEXT,
    why: 'an option present but not selectable — an inactive customer still has to be readable',
  },
  {
    fg: '--janso-brand',
    bg: '--janso-selected',
    gate: TEXT,
    why: 'the “Add …” create row while it is the highlighted row',
  },
  {
    fg: '--janso-disabled-ink',
    bg: '--janso-selected',
    gate: TEXT,
    why: 'a disabled option under the highlight — hovering one is allowed, selecting it is not',
  },
  {
    fg: '--janso-brand',
    bg: '--janso-hover',
    gate: TEXT,
    why: 'the “Load more” control on hover',
  },

  // — Links and brand text.
  { fg: '--janso-brand', bg: '--janso-surface', gate: TEXT, why: 'links, the selected tab' },
  { fg: '--janso-brand', bg: '--janso-paper', gate: TEXT, why: 'links in page-level copy' },
  {
    fg: '--janso-brand-ink',
    bg: '--janso-brand-tint',
    gate: TEXT,
    why: 'the selected rail item, a brand badge, an avatar’s initials',
  },

  // — A toast is a neutral overlay that carries its tone on the icon: the signal ink is a meaningful
  //   graphic there, so it owes 3:1 on `--janso-overlay`.
  ...(['success', 'warn', 'danger', 'info'] as const).map((signal) => ({
    fg: `--janso-${signal}-ink`,
    bg: '--janso-overlay',
    gate: GRAPHIC,
    why: `the ${signal} toast icon`,
  })),
  // — Signals are used as triplets, so each `-ink` is only ever measured on its own `-tint`
  //   (design-system §3.2). This is why the table is not a cross-product.
  ...(['success', 'warn', 'danger', 'info', 'neutral'] as const).map((signal) => ({
    fg: `--janso-${signal}-ink`,
    bg: `--janso-${signal}-tint`,
    gate: TEXT,
    why: `the ${signal} badge, stat tile and list row`,
  })),

  // — Control boundaries (WCAG 1.4.11). An empty input, an unchecked checkbox, an icon-only
  //   outline button and the theme-switcher group are defined by nothing but this hairline.
  {
    fg: '--janso-control-line',
    bg: '--janso-surface',
    gate: GRAPHIC,
    why: 'input, checkbox and icon-outline button edges on a card',
  },
  {
    fg: '--janso-control-line',
    bg: '--janso-paper',
    gate: GRAPHIC,
    why: 'the same controls sitting straight on the page',
  },
  {
    fg: '--janso-control-line',
    bg: '--janso-surface-2',
    gate: GRAPHIC,
    why: 'the theme-switcher group border against its own fill',
  },

  // — Focus is visible at every stop (§6), so the ring is measured on every surface a
  //   focusable thing can sit on.
  ...SURFACES.map((bg) => ({
    fg: '--janso-focus',
    bg,
    gate: GRAPHIC,
    why: 'the 2px solid stop of --janso-focus-ring',
  })),

  // — Charts: eight series and the zero line, all against the card they are drawn on.
  ...Array.from({ length: 8 }, (_, i) => ({
    fg: `--janso-chart-${i + 1}`,
    bg: '--janso-surface',
    gate: GRAPHIC,
    why: `series ${i + 1} bars — data ink`,
  })),
  {
    fg: '--janso-chart-axis',
    bg: '--janso-surface',
    gate: GRAPHIC,
    why: 'the zero line the bars grow out of',
  },

  // — The invoice designer (phases 1-8 of `docs/invoice-design-ui-todo.md`). The editor
  //   introduces two surfaces no other screen has: the **paper**, which must look like
  //   paper in all three palettes, and the **chrome** around it. None of it had ever been
  //   measured, which is decision log #13's failure mode again — a palette hand-tuned to
  //   look right on one theme.
  {
    fg: '--janso-canvas-page-ink',
    bg: '--janso-canvas-page',
    gate: TEXT,
    why: 'the document’s own text on the page',
  },
  {
    fg: '--janso-canvas-page-ink-soft',
    bg: '--janso-canvas-page',
    gate: TEXT,
    why: 'a field label, an address line, the meta row of a printed table',
  },
  {
    fg: '--janso-canvas-page-ink-soft',
    bg: '--janso-canvas-page-tint',
    gate: TEXT,
    why: 'a binding shown as `{{party.name}}` in placeholder mode',
  },
  {
    fg: '--janso-canvas-ruler-ink',
    bg: '--janso-canvas-ruler-bg',
    gate: TEXT,
    why: 'the millimetre numerals on the rulers',
  },
  {
    fg: '--janso-canvas-badge-ink',
    bg: '--janso-canvas-badge-bg',
    gate: TEXT,
    why: 'the paper chip — "A4 · 210 × 297 mm"',
  },
  {
    fg: '--janso-canvas-zone-label-ink',
    bg: '--janso-canvas-zone-label-bg',
    gate: TEXT,
    why: 'the name chip on a hovered zone',
  },
  {
    fg: '--janso-editor-chrome-ink',
    bg: '--janso-editor-chrome',
    gate: TEXT,
    why: 'inspector rows, the rail, the toolbar title',
  },
  {
    fg: '--janso-editor-chrome-ink-soft',
    bg: '--janso-editor-chrome',
    gate: TEXT,
    why: 'a row hint, a group label, the sample value beside a palette field',
  },
  {
    fg: '--janso-editor-chrome-ink',
    bg: '--janso-editor-chrome-2',
    gate: TEXT,
    why: 'the status bar, and a rail item under the pointer',
  },
  {
    fg: '--janso-editor-chrome-ink-soft',
    bg: '--janso-editor-chrome-2',
    gate: TEXT,
    why: 'the status bar’s keys — "Cursor", "Zoom", "Selected"',
  },

  // — Editing affordances drawn *on the paper*. Each is a graphic that carries meaning:
  //   which element is selected, what it is aligned to, where the page stops printing.
  //   A 2.4:1 selection ring is a selection nobody can see.
  {
    fg: '--janso-canvas-ring',
    bg: '--janso-canvas-page',
    gate: GRAPHIC,
    why: 'the selection ring and the hover outline',
  },
  {
    fg: '--janso-canvas-handle-line',
    bg: '--janso-canvas-page',
    gate: GRAPHIC,
    why: 'the edge of a resize handle',
  },
  {
    fg: '--janso-canvas-guide',
    bg: '--janso-canvas-page',
    gate: GRAPHIC,
    why: 'an alignment guide during a drag',
  },
  {
    fg: '--janso-canvas-zone-line',
    bg: '--janso-canvas-page',
    gate: GRAPHIC,
    why: 'a zone boundary',
  },
  {
    fg: '--janso-canvas-margin-line',
    bg: '--janso-canvas-page',
    gate: GRAPHIC,
    why: 'the printable-area guide — the line content must not cross',
  },
  {
    fg: '--janso-control-line',
    bg: '--janso-editor-chrome',
    gate: GRAPHIC,
    why: 'the edge of an inspector input, select, textarea, segmented control or zoom group',
  },

  /*
   * NOT measured, deliberately: `--janso-editor-chrome-line`.
   *
   * It is the divider between two regions — the rail from the stage, the toolbar from the
   * canvas, one palette group from the next — and a divider carries no information:
   * remove every one of them and the editor still says what is what, through position and
   * through the surfaces either side. WCAG 1.4.11 is about boundaries that *identify* a
   * component, which is why control edges moved to `--janso-control-line` above and are
   * measured there. Phase 8 found the two conflated, with every editor input drawn at
   * 1.26:1 — invisible to the users the rule exists for.
   */

  /*
   * NOT measured, deliberately: `--janso-canvas-page-edge` on `--janso-canvas-backdrop`.
   *
   * The sheet is identified by its fill against the backdrop and by its drop shadow, both
   * of which survive greyscale; the hairline is the third cue, not the only one. A 3:1
   * hairline here would be a near-black outline around a sheet of paper, which no document
   * editor draws and which would read as a border printed on the page rather than the edge
   * of it. Recorded as a finding in `docs/invoice-design-ui-todo.md` phase 8 rather than
   * suppressed quietly.
   */

  /*
   * NOT measured, deliberately: `--janso-canvas-copy-mark`.
   *
   * It is a 7%-alpha diagonal watermark, and no gate it could meet would still look like a
   * watermark — 3:1 on white is a heavy grey stamp that fights the invoice's own text. It
   * is excluded here rather than given a suppression, with the finding recorded in
   * `docs/invoice-design-ui-todo.md` phase 8: choosing `watermark` currently *replaces* the
   * readable top-of-page copy label rather than accompanying it, which is a document-
   * rendering decision for `docs/invoice-design.md` and not something a polish pass should
   * change on its own. The other two positions print the label as page ink and are covered
   * by the `--janso-canvas-page-ink` row above.
   */


  // — The required mark, the choice card and the format preview, added with the company
  //   wizard's rework. Each is a pairing those three put on screen and nothing measured.
  {
    fg: '--janso-danger-ink',
    bg: '--janso-surface',
    gate: TEXT,
    why: 'the required mark beside a field label, on a card',
  },
  {
    fg: '--janso-danger-ink',
    bg: '--janso-paper',
    gate: TEXT,
    why: 'the required mark on a form sitting straight on the page',
  },
  {
    fg: '--janso-ink',
    bg: '--janso-brand-tint',
    gate: TEXT,
    why: 'the title of a selected ChoiceCard, which tints when it is on',
  },
  {
    fg: '--janso-ink-soft',
    bg: '--janso-brand-tint',
    gate: TEXT,
    why: 'the description of a selected ChoiceCard',
  },
  {
    fg: '--janso-brand',
    bg: '--janso-surface',
    gate: GRAPHIC,
    why: 'the border that marks a ChoiceCard selected — the state, not decoration',
  },
  {
    fg: '--janso-ink',
    bg: '--janso-surface-2',
    gate: TEXT,
    why: 'a formatted value in the presentation preview',
  },
  {
    fg: '--janso-ink-soft',
    bg: '--janso-surface-2',
    gate: TEXT,
    why: 'its label, and the preview caption',
  },

  // — The document entry surface (`entry.css`, sales bill S7). A dense grid puts colours on
  //   surfaces no form does: a hovered row, a focused cell, the grid's own header tile.
  {
    fg: '--janso-danger-ink',
    bg: '--janso-surface-2',
    gate: TEXT,
    why: 'the required mark in an entry grid column heading',
  },
  ...(['danger', 'warn'] as const).flatMap((signal) =>
    (['--janso-surface', '--janso-hover'] as const).map((bg) => ({
      fg: `--janso-${signal}-ink`,
      bg,
      gate: TEXT,
      why: `a ${signal} row note under its line, at rest and under the pointer`,
    })),
  ),
  ...(['danger', 'warn', 'success'] as const).map((signal) => ({
    fg: `--janso-${signal}-ink`,
    bg: '--janso-surface',
    gate: GRAPHIC,
    why: `the ${signal} row-state edge — the marker that survives greyscale with its note`,
  })),
  {
    fg: '--janso-success-ink',
    bg: '--janso-surface-2',
    gate: GRAPHIC,
    why: 'the edge of “Return ₹X in change” in the rail',
  },
  ...(['--janso-ink', '--janso-ink-soft', '--janso-ink-faint'] as const).map((fg) => ({
    fg,
    bg: '--janso-hover',
    gate: TEXT,
    why: 'a cell, a derived figure and the line number on a hovered row',
  })),
  {
    fg: '--janso-ink-faint',
    bg: '--janso-selected',
    gate: TEXT,
    why: 'a placeholder in the focused cell',
  },
  {
    fg: '--janso-focus',
    bg: '--janso-selected',
    gate: GRAPHIC,
    why: 'the inset ring of the focused cell, drawn on its own fill',
  },
];

/** The primary action is a gradient, so its label is measured against both stops. */
const GRADIENT_PAIRS = [
  {
    fg: '--janso-brand-ink', gradient: '--janso-grad-panel', gate: TEXT,
    why: 'Kisco wordmark on the login brand panel',
  },
  {
    fg: '--janso-wordmark-books', gradient: '--janso-grad-panel', gate: TEXT,
    why: 'Books wordmark on the login brand panel',
  },
  {
    fg: '--janso-ink-invert',
    gradient: '--janso-grad-action',
    gate: TEXT,
    why: 'the primary button label and the checked tick',
  },
] as const;

// ---------- the assertions ----------

describe('contrast (design-system §2.4)', () => {
  it('computes the WCAG reference ratios correctly — the measuring stick first', () => {
    expect(contrast([0, 0, 0], [255, 255, 255])).toBeCloseTo(21, 5);
    expect(contrast([255, 255, 255], [255, 255, 255])).toBeCloseTo(1, 5);
    // The documented mid-grey: #767676 is the canonical 4.54:1 on white.
    expect(contrast(parseHex('#767676'), [255, 255, 255])).toBeCloseTo(4.54, 2);
    // A translucent value has contrast only against a stated backdrop.
    expect(compositeRgba('rgba(0, 0, 0, 0.5)', [255, 255, 255])).toEqual([127.5, 127.5, 127.5]);
  });

  describe.each(THEMES)('%s', (theme) => {
    it.each(['--janso-brand-ink', '--janso-wordmark-books'])('keeps %s readable over the auth panel glow', fg => {
      // Conservative bound: the full glow over either gradient endpoint.
      for (const stop of gradientStops(theme, '--janso-grad-panel')) {
        const background = resolve(theme, '--janso-brand-glow', stop);
        expect(contrast(resolve(theme, fg, background), background)).toBeGreaterThanOrEqual(TEXT);
      }
    });
    it.each(PAIRS)('$fg on $bg ≥ $gate:1 — $why', ({ fg, bg, gate, why }) => {
      const background = resolve(theme, bg, [255, 255, 255]);
      const foreground = resolve(theme, fg, background);
      const ratio = contrast(foreground, background);

      // The failure message is the deliverable: theme, pair, what it is for, and the number.
      expect(
        meets(ratio, gate)
          ? 'meets gate'
          : `${theme}: ${fg} on ${bg} measures ${ratio.toFixed(2)}:1, gate ${gate}:1 (${why})`,
      ).toBe('meets gate');
    });

    it.each(GRADIENT_PAIRS)(
      '$fg on both stops of $gradient ≥ $gate:1 — $why',
      ({ fg, gradient, gate, why }) => {
        const failures = gradientStops(theme, gradient)
          .map((stop) => ({ stop, ratio: contrast(resolve(theme, fg, stop), stop) }))
          .filter(({ ratio }) => !meets(ratio, gate))
          .map(
            ({ stop, ratio }) =>
              `${theme}: ${fg} on ${gradient} stop rgb(${stop.join(', ')}) measures ` +
              `${ratio.toFixed(2)}:1, gate ${gate}:1 (${why})`,
          );

        expect(failures).toEqual([]);
      },
    );
  });

  /*
   * Dark only, deliberately. In light and ledger the popover edge is a quiet hairline because the
   * shadow lifts the surface; on near-black the shadow renders as nothing, so the edge is the only
   * thing separating a menu or dialog from the page and owes the graphic gate (§2.4).
   */
  it('gives dark popovers a 3:1 edge, since a shadow cannot separate them there', () => {
    const background = resolve('dark', '--janso-overlay', [0, 0, 0]);
    const edge = resolve('dark', '--janso-overlay-line', background);
    expect(meets(contrast(edge, background), GRAPHIC)).toBe(true);
    const page = resolve('dark', '--janso-paper', [0, 0, 0]);
    expect(meets(contrast(edge, page), GRAPHIC)).toBe(true);
  });

  /*
   * The same argument as the popover rule above, which had never been carried across to the
   * things that are not popovers. A card, a stat tile, a table shell and the rail are separated
   * by `--janso-line` plus `--janso-shadow-card`, and on near-black that shadow measures 1.03:1
   * against the page — so the line is the entire separation budget. It shipped at 1.23:1, which
   * is why the administration pages read as one undivided surface.
   *
   * The floor is 1.8 rather than the graphic gate: this token is also every table row divider,
   * and 3:1 on fifty consecutive rows is a wireframe. 3:1 is `line-strong`'s job and
   * `control-line`'s, both of which the pairing table already measures. What this guards is
   * that the structural hairline never falls back toward invisible.
   */
  it('keeps the dark structural line visible, since a shadow cannot separate a card there', () => {
    const FLOOR = 1.8;
    const failures = ['--janso-paper', '--janso-surface', '--janso-surface-2']
      .map((surface) => {
        const background = resolve('dark', surface, [0, 0, 0]);
        return { surface, ratio: contrast(resolve('dark', '--janso-line', background), background) };
      })
      .filter(({ ratio }) => Math.round(ratio * 10) / 10 < FLOOR)
      .map(
        ({ surface, ratio }) =>
          `dark: --janso-line on ${surface} measures ${ratio.toFixed(2)}:1, floor ${FLOOR}:1`,
      );

    expect(failures).toEqual([]);
  });

  /*
   * An ActionCard is filled with `--janso-grad-panel`, and the administration landing pages are
   * grids of them. The dark gradient used to *descend toward* `--janso-paper`, ending at 1.01:1
   * against the page — the card dissolved from the bottom up, taking its call to action with it.
   * So the direction is the assertion: every stop lifts clear of the page, never reaches for it.
   */
  it('lifts the dark panel gradient clear of the page rather than sinking into it', () => {
    const page = resolve('dark', '--janso-paper', [0, 0, 0]);
    const failures = gradientStops('dark', '--janso-grad-panel')
      .map((stop) => ({ stop, lifts: luminance(stop) > luminance(page), ratio: contrast(stop, page) }))
      .filter(({ lifts, ratio }) => !lifts || ratio < 1.05)
      .map(
        ({ stop, ratio }) =>
          `dark: --janso-grad-panel stop rgb(${stop.join(', ')}) measures ${ratio.toFixed(3)}:1 ` +
          `against --janso-paper and must lift clear of it`,
      );

    expect(failures).toEqual([]);
  });

  /*
   * Which token a boundary *uses* is the other half of the guarantee: the pairing table proves
   * `--janso-control-line` clears 3:1 on a card and on the page in all three palettes, and these
   * two rules are what connect that proof to an interactive edge. Both are links drawn as
   * outline controls — WCAG 1.4.11 territory — and both had been reaching for the decorative
   * rule, which is 1.23:1 on dark.
   */
  it('draws interactive container edges with the control-line token, not the decorative rule', () => {
    const css = readFileSync(join(STYLES, 'data.css'), 'utf8');
    for (const selector of ['.janso-action-card', '.janso-page-navigation__back']) {
      const block = css.slice(css.indexOf(selector + ' {'));
      const border = block.slice(0, block.indexOf('}')).match(/border:\s*1px solid var\((--[a-z-]+)\)/);
      expect({ selector, token: border?.[1] }).toEqual({ selector, token: '--janso-control-line' });
    }
  });

  /*
   * Dark spends its card elevation on an inset lit edge, because the drop half does not render:
   * both halves are measured here, so the premise and the replacement stay honest together. If
   * someone later deletes the inset, the first expectation fails and the second explains why it
   * was there.
   */
  it('gives a dark card a lit top edge, since its drop shadow cannot separate it', () => {
    const surface = resolve('dark', '--janso-surface', [0, 0, 0]);
    const page = resolve('dark', '--janso-paper', [0, 0, 0]);
    const { drop, inset } = shadowLayers('dark', '--janso-shadow-card');

    expect(inset).toBeDefined();
    const lip = compositeRgba(inset as string, surface);
    expect(Math.round(contrast(lip, surface) * 100) / 100).toBeGreaterThanOrEqual(1.2);

    // The premise: the cast shadow is indistinguishable from the page it falls on.
    expect(drop).toBeDefined();
    expect(contrast(compositeRgba(drop as string, page), page)).toBeLessThan(1.05);
  });

  /*
   * `.janso-btn--primary:active` swaps `--janso-shadow-action` for `--janso-shadow-card`, so the
   * card's lit edge has to stay below the button's resting one — otherwise raising the card's
   * elevation silently takes a cue away from the press. Only palettes that light both are
   * compared; light and ledger give the card no inset at all, so the press simply loses it.
   */
  it('keeps a pressed primary button lit less than a resting one', () => {
    const failures = THEMES.map((theme) => {
      const resting = shadowLayers(theme, '--janso-shadow-action').inset;
      const pressed = shadowLayers(theme, '--janso-shadow-card').inset;
      if (!resting || !pressed) return null;
      return alphaOf(pressed) < alphaOf(resting)
        ? null
        : `${theme}: --janso-shadow-card lights its top edge at ${alphaOf(pressed)}, not below ` +
          `--janso-shadow-action's ${alphaOf(resting)} — a pressed button would stop reading as pressed`;
    }).filter(Boolean);

    expect(failures).toEqual([]);
  });

  it('measures every token the table names, in every palette', () => {
    const named = new Set([
      ...PAIRS.flatMap(({ fg, bg }) => [fg, bg]),
      ...GRADIENT_PAIRS.flatMap(({ fg, gradient }) => [fg, gradient]),
    ]);
    for (const theme of THEMES) {
      const missing = [...named].filter((token) => !TOKENS[theme].has(token));
      expect({ theme, missing }).toEqual({ theme, missing: [] });
    }
  });
});
