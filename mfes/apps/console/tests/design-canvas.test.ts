/**
 * The service ⇄ editor canvas boundary.
 *
 * **Round-tripping is the contract.** A layout that leaves the service, is opened in the editor
 * and saved back untouched must produce the identical tree — otherwise the service computes a
 * different `layout_digest`, and a template nobody edited fills its history with revisions
 * nobody made. That is the whole reason this file exists, and the four shipped sample layouts
 * are the input because they are the richest 1.1.0 trees anyone has written: a GST tax invoice,
 * a compact A4, an 80mm roll and a delivery challan.
 *
 * The second thing asserted here is that the translation *loses* exactly one thing on purpose —
 * paper size and orientation, which belong to the template row and must not be sent back inside
 * the tree (docs/invoice-design.md, decision 2026-10-27).
 */
import { describe, expect, it } from 'vitest';
import {
  isEditableLayout,
  layoutToEditor,
  layoutToWire,
  templateToEditor,
  versionToEditor,
  type PaperRow,
} from '../app/lib/design-canvas';
import { SAMPLE_TEMPLATES } from '../app/(editor)/invoice-designer/sample-templates';
import { SCHEMA_VERSION, type CanvasDefinition } from '../app/(editor)/invoice-designer/layout-model';

/** `style: {}` says nothing; the boundary drops it and this lets a comparison ignore it. */
function withoutEmptyStyles(layout: CanvasDefinition): CanvasDefinition {
  return {
    ...layout,
    sections: layout.sections.map((section) => ({
      ...section,
      elements: section.elements.map((element) => {
        if (element.style && Object.keys(element.style).length === 0) {
          const { style: _dropped, ...rest } = element;
          return rest;
        }
        return element;
      }),
    })),
  };
}

/** The row the service would hold for a layout whose editor page says this. */
function rowFor(layout: CanvasDefinition): PaperRow {
  return {
    paper_size: layout.page.size,
    page_orientation: layout.page.orientation,
    page_width_mm: layout.page.widthMm != null ? layout.page.widthMm.toFixed(4) : null,
    page_height_mm: layout.page.heightMm != null ? layout.page.heightMm.toFixed(4) : null,
  };
}

/** One pass of the boundary: editor → service → editor. */
function roundTrip(layout: CanvasDefinition): CanvasDefinition {
  return layoutToEditor(layoutToWire(layout), rowFor(layout));
}

describe('canvas round trip', () => {
  /*
   * Idempotence, not raw equality, and the difference is the point.
   *
   * One pass is allowed to drop something meaningless — and does: several sample elements
   * carry `style: {}`, an empty object that says nothing, which the boundary collapses to an
   * absent key. Absent and empty are the same document to every reader of a style (`?.`
   * everywhere), and keeping an empty object alive across the boundary purely to match a
   * fixture would be noise defended by a test.
   *
   * What must never happen is a *second* pass changing anything again: that is the property
   * the service's `layout_digest` depends on. If the boundary kept nudging a tree, every save
   * of an untouched template would mint a new revision nobody made.
   */
  it.each(SAMPLE_TEMPLATES.map((template) => [template.code, template] as const))(
    'settles after one pass and never moves again for %s',
    (_code, template) => {
      const once = roundTrip(template.layout);

      expect(roundTrip(once)).toEqual(once);
      expect(JSON.stringify(roundTrip(once))).toBe(JSON.stringify(once));
    },
  );

  it.each(SAMPLE_TEMPLATES.map((template) => [template.code, template] as const))(
    'changes nothing of substance on the first pass either for %s',
    (_code, template) => {
      // The same comparison with the one meaningless difference removed, so this test says
      // "nothing else moved" rather than leaving idempotence to imply it.
      expect(withoutEmptyStyles(roundTrip(template.layout))).toEqual(
        withoutEmptyStyles(template.layout),
      );
    },
  );

  it.each(SAMPLE_TEMPLATES.map((template) => [template.code, template] as const))(
    'survives service → editor → service unchanged for %s',
    (_code, template) => {
      const wire = layoutToWire(template.layout);
      const again = layoutToWire(layoutToEditor(wire, rowFor(template.layout)));

      // Deep equality is not enough here: the service digests the *serialised* tree with
      // sorted keys, so an added `null` would change the digest while still comparing equal
      // to a caller that only looks at values.
      expect(JSON.stringify(again)).toBe(JSON.stringify(wire));
    },
  );

  it('carries the item-table column set through without reshaping it', () => {
    const invoice = SAMPLE_TEMPLATES.find((template) =>
      template.layout.sections.some((section) =>
        section.elements.some((element) => element.columns?.length),
      ),
    );
    expect(invoice, 'a sample layout with an item table').toBeDefined();

    const wire = layoutToWire(invoice!.layout);
    const columns = wire.sections
      ?.flatMap((section) => section.elements ?? [])
      .find((element) => element.columns)?.columns;

    expect(columns?.length).toBeGreaterThan(3);
    // `widthMm` on the editor's side, `width_mm` on the service's — the case difference the
    // service validates the column total against.
    expect(columns!.every((column) => typeof column.width_mm === 'number')).toBe(true);
    expect(columns!.some((column) => column.key === 'description')).toBe(true);
  });

  it('carries print copies and the totals vocabulary', () => {
    const wire = layoutToWire(SAMPLE_TEMPLATES[0]!.layout);

    expect(wire.print_options?.copies?.length).toBeGreaterThanOrEqual(1);
    expect(wire.schema_version).toBe(SCHEMA_VERSION);
  });
});

describe('what the boundary deliberately drops', () => {
  it('never sends paper size or orientation back inside the layout', () => {
    // Sending them would recreate the two-sources-of-truth problem 1.1.0 removed: the row
    // and the tree disagreeing about what paper a document prints on.
    const wire = layoutToWire(SAMPLE_TEMPLATES[0]!.layout);
    const page = wire.page as Record<string, unknown>;

    expect(page).not.toHaveProperty('size');
    expect(page).not.toHaveProperty('orientation');
    expect(page).not.toHaveProperty('width_mm');
    expect(page).toHaveProperty('grid_step_mm');
    expect(page).toHaveProperty('margins');
  });

  it('reads paper back from the row, so nothing is lost overall', () => {
    const source = SAMPLE_TEMPLATES.find((template) => template.layout.page.size !== 'A4');
    expect(source, 'a sample on something other than A4').toBeDefined();

    const back = layoutToEditor(layoutToWire(source!.layout), rowFor(source!.layout));
    expect(back.page.size).toBe(source!.layout.page.size);
    expect(back.page.orientation).toBe(source!.layout.page.orientation);
  });

  it('parses the row’s decimal page measurements without inventing numbers', () => {
    const row: PaperRow = {
      paper_size: 'CUSTOM',
      page_orientation: 'PORTRAIT',
      page_width_mm: '200.0000',
      page_height_mm: '150.0000',
    };
    const page = layoutToEditor({ schema_version: SCHEMA_VERSION }, row).page;

    expect(page.widthMm).toBe(200);
    expect(page.heightMm).toBe(150);
  });

  it('omits a page measurement the row does not carry, rather than defaulting it', () => {
    const page = layoutToEditor(
      { schema_version: SCHEMA_VERSION },
      { paper_size: 'A4', page_orientation: 'PORTRAIT', page_width_mm: null },
    ).page;

    expect(page).not.toHaveProperty('widthMm');
    expect(page).not.toHaveProperty('heightMm');
    // The defaults the service itself applies, so an empty layout opens on a usable page.
    expect(page.margins).toEqual({ top: 10, right: 10, bottom: 10, left: 10, unit: 'mm' });
    expect(page.gridSnap).toBe(true);
    expect(page.gridStepMm).toBe(5);
  });
});

describe('which stored layouts the editor may open', () => {
  it('edits 1.1.0 and refuses to pretend it can edit 1.0.0', () => {
    // A 1.0.0 tree still prints and its history is intact, but it cannot express a column
    // set, a totals block or a zone box — so opening it would mean inventing geometry and
    // then saving that invention back as if the author had chosen it.
    expect(isEditableLayout({ schema_version: SCHEMA_VERSION })).toBe(true);
    expect(isEditableLayout({ schema_version: '1.0.0' })).toBe(false);
  });
});

describe('template and version projections', () => {
  const row = {
    id: '01990000-0000-7000-8000-000000000001',
    company_id: '01990000-0000-7000-8000-00000000000c',
    code: 'gst-invoice',
    name: 'GST tax invoice',
    description: 'The full one',
    paper_size: 'A4',
    page_orientation: 'PORTRAIT',
    status: 'PUBLISHED',
    is_system: false,
    current_version_id: '01990000-0000-7000-8000-000000000002',
    updated_at: '2026-10-27T00:00:00Z',
  };

  it('maps a detail row onto what the editor renders', () => {
    const template = templateToEditor(row, SAMPLE_TEMPLATES[0]!.layout, []);

    expect(template.code).toBe('gst-invoice');
    expect(template.isSystem).toBe(false);
    expect(template.liveVersionId).toBe('01990000-0000-7000-8000-000000000002');
    expect(template.versions).toEqual([]);
  });

  it('reads an unpublished template as printing nothing', () => {
    const draft = templateToEditor(
      { ...row, status: 'DRAFT', current_version_id: null },
      SAMPLE_TEMPLATES[0]!.layout,
    );

    expect(draft.status).toBe('DRAFT');
    expect(draft.liveVersionId).toBeNull();
  });

  it('maps a version row, keeping published_at as the liveness fact', () => {
    expect(
      versionToEditor({
        id: '01990000-0000-7000-8000-000000000003',
        template_id: row.id,
        version_number: 4,
        schema_version: SCHEMA_VERSION,
        layout_digest: 'ab'.repeat(32),
        change_summary: 'Widened the description column',
        published_at: '2026-10-27T10:00:00Z',
        created_at: '2026-10-27T09:00:00Z',
      }),
    ).toEqual({
      id: '01990000-0000-7000-8000-000000000003',
      versionNumber: 4,
      changeSummary: 'Widened the description column',
      createdAt: '2026-10-27T09:00:00Z',
      publishedAt: '2026-10-27T10:00:00Z',
    });
  });

  it('omits an absent change summary rather than carrying null into the UI', () => {
    const version = versionToEditor({
      id: '01990000-0000-7000-8000-000000000004',
      template_id: row.id,
      version_number: 1,
      schema_version: SCHEMA_VERSION,
      layout_digest: 'cd'.repeat(32),
      change_summary: null,
      published_at: null,
      created_at: '2026-10-27T09:00:00Z',
    });

    expect(version).not.toHaveProperty('changeSummary');
    expect(version).not.toHaveProperty('publishedAt');
  });
});
