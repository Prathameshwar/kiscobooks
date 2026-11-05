/**
 * The checks that catch what a preview cannot show, and the presets that must never
 * create one.
 *
 * No DOM here: `checkLayout` and `applyPreset` are pure, so these are the cheap tests and
 * the panel is just a render of their output.
 */
import { describe, expect, it } from 'vitest';
import {
  drawnPageHeightMm,
  setMargins,
  setPage,
} from '../app/(editor)/invoice-designer/layout-edit';
import type {
  CanvasDefinition,
  CanvasSection,
} from '../app/(editor)/invoice-designer/layout-model';
import {
  type WarningCode,
  checkLayout,
  summarise,
} from '../app/(editor)/invoice-designer/layout-warnings';
import { PRESETS, activePreset, applyPreset } from '../app/(editor)/invoice-designer/presets';
import { SAMPLE_TEMPLATES } from '../app/(editor)/invoice-designer/sample-templates';

const GST = SAMPLE_TEMPLATES.find((template) => template.id === 'tpl-gst-a4')!;

const codes = (layout: CanvasDefinition): WarningCode[] =>
  checkLayout(layout).map((warning) => warning.code);

/** The GST fixture with one zone replaced, for isolating a single check. */
function withZone(patch: Partial<CanvasSection> & { id: string }): CanvasDefinition {
  return {
    ...GST.layout,
    sections: GST.layout.sections.map((section) =>
      section.id === patch.id ? { ...section, ...patch } : section,
    ),
  };
}

describe('checking a layout', () => {
  it('finds nothing wrong with a shipped template', () => {
    // The load-bearing assertion of the whole file. A check that fires on the four
    // fixtures is a check nobody will keep: the panel would be full on every template
    // anyone opens, and a full panel is an ignored one.
    for (const template of SAMPLE_TEMPLATES) {
      expect(checkLayout(template.layout), template.name).toEqual([]);
    }
  });

  it('reports a zone pushed past the printable edge, and by how much', () => {
    // The footer is 190mm wide at x=10 on a 190mm printable width; 4mm right takes it out.
    const warnings = checkLayout(withZone({ id: 'sec-footer', xMm: 14 }));
    expect(warnings).toHaveLength(1);
    expect(warnings[0]).toMatchObject({
      code: 'zone-outside-printable',
      severity: 'error',
      targetId: 'sec-footer',
    });
    expect(warnings[0]?.message).toContain('4mm past the right edge');
  });

  it('calls a zone that crosses the bottom a page break, not an overflow', () => {
    // A4 printable bottom is 287mm. The footer starts at 244 and is 43mm tall, so growing
    // it to 50 puts 7mm on a second page — which for a long table is the intent.
    const warnings = checkLayout(withZone({ id: 'sec-footer', heightMm: 50 }));
    expect(warnings.map((warning) => warning.code)).toEqual(['page-break-inside-zone']);
    expect(warnings[0]).toMatchObject({ severity: 'warning' });
    expect(warnings[0]?.message).toContain('7mm');
    expect(warnings[0]?.message).toContain('every copy');
  });

  it('says nothing about the bottom of a roll, which simply gets longer', () => {
    const roll = setPage(GST.layout, { size: 'THERMAL_80MM' });
    // Every zone now overflows the 74mm width, which is real and reported; none of them
    // is reported for running past the nominal 200mm length, which is not.
    expect(codes(roll)).not.toContain('page-break-inside-zone');
    expect(codes(roll).every((code) => code !== 'page-break-inside-zone')).toBe(true);
    for (const warning of checkLayout(roll)) {
      expect(warning.message).not.toContain('bottom edge');
    }
  });

  it('reports a zone left outside the paper when the paper shrinks under it', () => {
    const roll = setPage(GST.layout, { size: 'THERMAL_58MM' });
    const outside = checkLayout(roll).filter(
      (warning) => warning.code === 'zone-outside-printable',
    );
    // Seven zones, every one of them 190mm or 112mm wide on 54mm of printable width.
    expect(outside).toHaveLength(GST.layout.sections.length);
    expect(outside.every((warning) => warning.severity === 'error')).toBe(true);
  });

  it('reports an element pushed outside the zone that clips it', () => {
    const layout = {
      ...GST.layout,
      sections: GST.layout.sections.map((section) =>
        section.id === 'sec-header'
          ? {
              ...section,
              elements: section.elements.map((element) =>
                element.id === 'el-title' ? { ...element, xMm: 150 } : element,
              ),
            }
          : section,
      ),
    };
    const warnings = checkLayout(layout).filter(
      (warning) => warning.code === 'element-outside-zone',
    );
    expect(warnings).toHaveLength(1);
    expect(warnings[0]?.targetId).toBe('el-title');
    expect(warnings[0]?.message).toContain('4mm outside');
  });

  it('reports a column set that overflows its table — the error phase 1 shipped with', () => {
    const layout = {
      ...GST.layout,
      sections: GST.layout.sections.map((section) =>
        section.id === 'sec-items'
          ? {
              ...section,
              elements: section.elements.map((element) =>
                element.columns
                  ? {
                      ...element,
                      columns: element.columns.map((column) =>
                        column.key === 'description' ? { ...column, widthMm: 66 } : column,
                      ),
                    }
                  : element,
              ),
            }
          : section,
      ),
    };
    const warnings = checkLayout(layout);
    expect(warnings.map((warning) => warning.code)).toEqual(['columns-overflow']);
    expect(warnings[0]?.message).toContain('204mm inside a 190mm table');
  });

  it('reports overlapping zones once, on the one that was moved into the other', () => {
    const warnings = checkLayout(withZone({ id: 'sec-meta', yMm: 30 }));
    const overlap = warnings.filter((warning) => warning.code === 'zones-overlap');
    expect(overlap).toHaveLength(1);
    // The header is sections[0] and the meta zone sections[1], so the later one is named.
    expect(overlap[0]?.targetId).toBe('sec-meta');
  });

  it('reports a binding the sample document cannot resolve, as a warning not an error', () => {
    const layout = {
      ...GST.layout,
      sections: GST.layout.sections.map((section) =>
        section.id === 'sec-meta'
          ? {
              ...section,
              elements: section.elements.map((element) =>
                element.id === 'el-no'
                  ? { ...element, bindingPath: 'voucher.invoice_no' as const }
                  : element,
              ),
            }
          : section,
      ),
    };
    const warnings = checkLayout(layout);
    expect(warnings).toHaveLength(1);
    expect(warnings[0]).toMatchObject({ code: 'binding-unresolved', severity: 'warning' });
    // It says the preview is what is affected, not that the design is wrong: a real
    // document may carry a path this fixture does not.
    expect(warnings[0]?.message).toContain('A real document may still resolve it');
  });

  it('says nothing about a signature with no image, which is a space to sign', () => {
    // The delivery challan's "Receiver's signature" is meant to be blank, and so is every
    // invoice signed with a pen. Three of the four fixtures carry one.
    const challan = SAMPLE_TEMPLATES.find((template) => template.id === 'tpl-challan-a4')!;
    const signatures = challan.layout.sections
      .flatMap((section) => section.elements)
      .filter((element) => element.type === 'SIGNATURE' && !element.assetId);
    expect(signatures.length).toBeGreaterThan(0);
    expect(codes(challan.layout)).toEqual([]);
  });

  it('reports an asset the template does not carry, which is a dangling reference', () => {
    const layout = {
      ...GST.layout,
      sections: GST.layout.sections.map((section) =>
        section.id === 'sec-footer'
          ? {
              ...section,
              elements: section.elements.map((element) =>
                element.id === 'el-sign' ? { ...element, assetId: 'asset-gone' } : element,
              ),
            }
          : section,
      ),
    };
    expect(codes(layout)).toEqual(['asset-missing']);
  });

  it('reports an image with no asset', () => {
    const layout = {
      ...GST.layout,
      sections: GST.layout.sections.map((section) =>
        section.id === 'sec-header'
          ? {
              ...section,
              elements: section.elements.map((element) =>
                element.id === 'el-logo' ? { ...element, assetId: undefined } : element,
              ),
            }
          : section,
      ),
    };
    expect(codes(layout)).toEqual(['asset-missing']);
  });

  it('lists errors before warnings, then down the page', () => {
    let layout = withZone({ id: 'sec-meta', yMm: 30 }); // a warning, high on the page
    layout = {
      ...layout,
      sections: layout.sections.map((section) =>
        section.id === 'sec-footer' ? { ...section, xMm: 14 } : section,
      ), // an error, at the bottom
    };
    const warnings = checkLayout(layout);
    expect(warnings.map((warning) => warning.severity)).toEqual(['error', 'warning']);
  });

  it('ignores a tenth of a millimetre, because an exact fit must read as one', () => {
    // Margins leave exactly 190mm, and the footer is exactly 190mm wide.
    expect(codes(GST.layout)).toEqual([]);
    expect(codes(setMargins(GST.layout, { right: 10.2 }))).toContain('zone-outside-printable');
  });

  it('summarises for the panel heading', () => {
    expect(summarise([])).toBe('Nothing to fix');
    expect(summarise(checkLayout(withZone({ id: 'sec-footer', xMm: 14 })))).toBe('1 error');
    expect(summarise(checkLayout(withZone({ id: 'sec-meta', yMm: 30 })))).toBe('1 warning');
    expect(summarise(checkLayout(setPage(GST.layout, { size: 'THERMAL_58MM' })))).toContain(
      '7 errors',
    );
  });
});

describe('the drawn length of a roll', () => {
  it('leaves a sheet at its own height', () => {
    expect(drawnPageHeightMm(GST.layout)).toBe(297);
  });

  it('grows a roll to its content, because a receipt is as long as it is', () => {
    const roll = applyPreset(GST.layout, 'thermal-80');
    // The stack ends at 314mm, plus the 3mm bottom margin. Drawing the nominal 200mm and
    // letting the tax summary sit on the backdrop reads as a broken editor, which is what
    // phase 8's screenshots showed.
    expect(drawnPageHeightMm(roll)).toBe(317);
    expect(drawnPageHeightMm(roll)).toBeGreaterThan(200);
    // The model keeps the nominal stock: that is what the renderer is told about.
    expect(roll.page.heightMm).toBeUndefined();
  });

  it('never shrinks a roll below its nominal length', () => {
    const roll = applyPreset(GST.layout, 'thermal-80');
    const short = { ...roll, sections: roll.sections.slice(0, 1) };
    expect(drawnPageHeightMm(short)).toBe(200);
  });
});

describe('paper presets', () => {
  it('leaves no layout problem behind, starting from an A4 invoice', () => {
    // A preset that produced a layout the warnings panel complains about would be a
    // feature whose whole output needs fixing by hand. An A4 invoice is the realistic
    // starting point: it is what the three shipped sheet templates are.
    for (const preset of PRESETS) {
      const applied = applyPreset(GST.layout, preset.id);
      expect(checkLayout(applied), preset.label).toEqual([]);
    }
  });

  it('reports the page break when a roll is converted to a sheet, rather than hiding it', () => {
    // Honest limitation, stated as a test. A roll stacks its zones end to end and their
    // heights total more than an A4 page: no arithmetic fits that onto one sheet, because
    // shrinking heights would shrink text nobody could then read. So the preset reshapes
    // the width and the panel says the rest out loud.
    const roll = applyPreset(GST.layout, 'thermal-80');
    const sheet = applyPreset(roll, 'a4-invoice');
    expect(sheet.page.size).toBe('A4');
    const problems = checkLayout(sheet);
    expect(problems.map((warning) => warning.code)).toEqual(['page-break-inside-zone']);
    // Nothing is off the paper sideways and nothing is above the top margin: the parts the
    // preset can do by arithmetic, it did. What is left is a genuinely taller document
    // than one sheet holds, and the panel names the zone it breaks in.
    expect(problems[0]?.message).toMatch(/crosses the bottom of the printable area/);
  });

  it('fits an A4 invoice onto an 80mm roll', () => {
    const roll = applyPreset(GST.layout, 'thermal-80');
    expect(roll.page.size).toBe('THERMAL_80MM');
    expect(roll.page.margins).toMatchObject({ top: 3, right: 3, bottom: 3, left: 3 });
    expect(roll.theme.fontSizePt).toBe(7);
    // A counter receipt prints one copy; there is no transporter's copy of one.
    expect(roll.print.copies).toEqual(['ORIGINAL_FOR_RECIPIENT']);
    expect(roll.print.copyMarkPosition).toBe('top-center');

    // 80mm paper less 3mm each side is 74mm of printable width, and the full-width zones
    // are now exactly that.
    const header = roll.sections.find((section) => section.id === 'sec-header');
    expect(header).toMatchObject({ xMm: 3, widthMm: 74 });
  });

  it('stacks the zones on a roll, because a roll is one strip', () => {
    const roll = applyPreset(GST.layout, 'thermal-80');
    const tops = roll.sections.map((section) => section.yMm);
    // Strictly increasing, and the first starts at the top margin rather than at 10mm.
    expect(tops[0]).toBe(3);
    for (let i = 1; i < tops.length; i += 1) {
      expect(tops[i]!).toBeGreaterThan(tops[i - 1]!);
    }
    // No gaps left over from the A4 arrangement: each zone follows the previous one.
    const second = roll.sections[1]!;
    const first = roll.sections[0]!;
    expect(second.yMm).toBe(first.yMm + first.heightMm + 2);
  });

  it('cuts the receipt down to the columns 74mm can carry, summing to the table exactly', () => {
    const roll = applyPreset(GST.layout, 'thermal-80');
    const table = roll.sections
      .flatMap((section) => section.elements)
      .find((element) => element.type === 'ITEM_TABLE')!;
    expect(table.columns?.map((column) => column.key)).toEqual([
      'description',
      'quantity',
      'rate',
      'amount',
    ]);
    const total = table.columns!.reduce((sum, column) => sum + column.widthMm, 0);
    expect(total).toBe(table.widthMm);
    expect(table.widthMm).toBe(74);
  });

  it('scales element type with the base size, so a 14pt title is not left at 14pt', () => {
    // Phase 8's screenshots caught this: the box fits perfectly and the words inside it
    // do not, which no geometry check can see. 9pt base → 7pt is ×0.778.
    const roll = applyPreset(GST.layout, 'thermal-80');
    const header = roll.sections.find((section) => section.id === 'sec-header')!;
    const title = header.elements.find((element) => element.id === 'el-title')!;
    const company = header.elements.find((element) => element.id === 'el-company')!;
    expect(company.style?.fontSizePt).toBeCloseTo(10.9, 1);
    expect(title.style?.fontSizePt).toBeCloseTo(10.1, 1);
    // Never below what a printer resolves, and never above the model's ceiling.
    for (const section of roll.sections) {
      for (const element of section.elements) {
        if (element.style?.fontSizePt) {
          expect(element.style.fontSizePt).toBeGreaterThanOrEqual(4);
          expect(element.style.fontSizePt).toBeLessThanOrEqual(24);
        }
      }
    }
  });

  it('leaves element type alone when the base size does not move', () => {
    const same = applyPreset(GST.layout, 'a4-invoice');
    const title = same.sections
      .flatMap((section) => section.elements)
      .find((element) => element.id === 'el-title')!;
    expect(title.style?.fontSizePt).toBe(13);
  });

  it('keeps heights, because text does not get shorter when the page does', () => {
    const roll = applyPreset(GST.layout, 'thermal-58');
    const before = GST.layout.sections.find((section) => section.id === 'sec-header')!;
    const after = roll.sections.find((section) => section.id === 'sec-header')!;
    expect(after.heightMm).toBe(before.heightMm);
    expect(after.widthMm).toBeLessThan(before.widthMm);
    const title = after.elements.find((element) => element.id === 'el-title')!;
    expect(title.heightMm).toBe(7);
  });

  it('reshapes back to A4, without claiming to restore the original', () => {
    const there = applyPreset(GST.layout, 'thermal-58');
    const back = applyPreset(there, 'a4-invoice');
    expect(back.page.size).toBe('A4');
    expect(back.sections.find((section) => section.id === 'sec-header')?.widthMm).toBe(190);
    // Reshaping is lossy: the roll stacked the zones and A4 cannot know where they were.
    expect(back.sections.find((section) => section.id === 'sec-footer')?.yMm).not.toBe(244);
  });

  it('names the preset a layout is already on, by paper alone', () => {
    expect(activePreset(GST.layout)).toBe('a4-invoice');
    expect(activePreset(applyPreset(GST.layout, 'thermal-80'))).toBe('thermal-80');
    // Margins changed by hand do not stop it being an 80mm receipt.
    const tweaked = setMargins(applyPreset(GST.layout, 'thermal-80'), { left: 5 });
    expect(activePreset(tweaked)).toBe('thermal-80');
    expect(activePreset(setPage(GST.layout, { size: 'LETTER' }))).toBeNull();
  });
});
