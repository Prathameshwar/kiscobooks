/**
 * The invoice designer's shell and document renderer.
 *
 * The load-bearing properties for this phase: the page is drawn in millimetres so the
 * preview is what prints; the layout tree decides what appears and in what order; zoom and
 * the copy switch work from the keyboard as well as the pointer; and an unresolved binding
 * shows itself rather than leaving a blank box a designer would read as a layout bug.
 */
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { DocumentLayer } from '../app/(editor)/invoice-designer/DocumentLayer';
import { DesignerShell } from '../app/(editor)/invoice-designer/DesignerShell';
import {
  SAMPLE_TEMPLATES,
  templateById,
} from '../app/(editor)/invoice-designer/sample-templates';
import {
  SAMPLE_DOCUMENT,
  sampleBindingPaths,
  sampleValue,
} from '../app/(editor)/invoice-designer/sample-document';
import {
  BINDING_ROOTS,
  COLUMN_LABELS,
  type CanvasDefinition,
  SCHEMA_VERSION,
} from '../app/(editor)/invoice-designer/layout-model';

const GST = templateById('tpl-gst-a4')!;

function renderShell(initialTemplateId = GST.id) {
  return render(
    <DesignerShell templates={SAMPLE_TEMPLATES} initialTemplateId={initialTemplateId} />,
  );
}

describe('designer shell', () => {
  it('names the template and says whether it is printing', () => {
    renderShell();
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('GST tax invoice — A4');
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Live · version 4');
  });

  it('says plainly that a draft is not printing yet', () => {
    renderShell('tpl-compact-a4');
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Draft · not printing yet');
  });

  it('marks a shipped template as read-only', () => {
    renderShell('tpl-thermal-80');
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('read-only');
  });

  it('renders the page at its millimetre size, so the preview is what prints', () => {
    renderShell();
    expect(screen.getByTestId('design-canvas-paper')).toHaveStyle({
      width: '210mm',
      height: '297mm',
    });
  });

  it('switches template from the rail, and the paper follows', async () => {
    renderShell();
    await userEvent.setup().click(screen.getByRole('button', { name: /Retail receipt/ }));
    // A roll, not a sheet: 80mm wide and a different nominal length.
    expect(screen.getByTestId('design-canvas-paper')).toHaveStyle({ width: '80mm' });
  });

  it('lists the zones with how many elements each carries', () => {
    // Phase 2 replaced the read-only zone list with the selectable page tree; the rail
    // still has to show every zone and its element count, which is what this asserts.
    renderShell();
    const tree = screen.getByRole('tree', { name: 'Page structure' });
    expect(within(tree).getAllByRole('treeitem', { expanded: true })).toHaveLength(
      GST.layout.sections.length,
    );
    const details = within(tree).getByRole('treeitem', { name: /Document details/ });
    expect(details).toHaveTextContent('8');
  });

  it('steps zoom from the control and reports it in the status bar', async () => {
    renderShell();
    const user = userEvent.setup();
    const control = screen.getByRole('group', { name: 'Canvas zoom' });
    const status = screen.getByTestId('zoom-readout');
    await user.click(screen.getByRole('button', { name: 'Zoom in' }));
    expect(within(control).getByText('125%')).toBeInTheDocument();
    expect(status).toHaveTextContent('125%');
    await user.click(screen.getByRole('button', { name: 'Zoom out' }));
    expect(status).toHaveTextContent('100%');
  });

  it('zooms from the keyboard, because the canvas owns the whole screen', async () => {
    renderShell();
    const user = userEvent.setup();
    const status = screen.getByTestId('zoom-readout');
    await user.keyboard('{Control>}={/Control}');
    expect(status).toHaveTextContent('125%');
    await user.keyboard('{Control>}-{/Control}');
    expect(status).toHaveTextContent('100%');
    await user.keyboard('{Control>}+{/Control}');
    expect(status).toHaveTextContent('125%');
    // `ctrl`+0 is "actual size" — the stop everyone returns to.
    await user.keyboard('{Control>}0{/Control}');
    expect(status).toHaveTextContent('100%');
  });

  it('reports the cursor position in millimetres, as text a screen reader can read', async () => {
    renderShell();
    const paper = screen.getByTestId('design-canvas-paper');
    paper.getBoundingClientRect = () => ({ left: 0, top: 0, width: 794, height: 1123 }) as DOMRect;
    expect(screen.getByTestId('cursor-readout')).toHaveTextContent('off page');

    await userEvent.setup().pointer({ target: paper, coords: { clientX: 38, clientY: 76 } });
    expect(screen.getByTestId('cursor-readout')).toHaveTextContent('10.1, 20.1 mm');
  });

  it('previews a chosen copy and marks the page with it', async () => {
    renderShell();
    const user = userEvent.setup();
    await user.selectOptions(
      screen.getByRole('combobox', { name: 'Printed copy to preview' }),
      'DUPLICATE_FOR_TRANSPORTER',
    );
    const page = screen.getByTestId('design-canvas-paper');
    expect(
      within(page).getByText('Duplicate for Transporter', { selector: '[data-element]' }),
    ).toBeInTheDocument();
  });

  /*
   * Changed in phase 6, when the copy set became editable. Phase 1 hid this switch for a
   * one-copy template, which was right while the set was fixed: a two-option control
   * nobody could act on. The mark is printed content, so a designer of a single-copy
   * receipt needs to see whether it collides with the header — and the set they are now
   * able to edit starts at one.
   */
  it('offers the copy switch even for a single copy, since the mark still prints', () => {
    renderShell('tpl-compact-a4');
    const preview = screen.getByRole('combobox', { name: 'Printed copy to preview' });
    expect(within(preview).getByRole('option', { name: 'No mark' })).toBeInTheDocument();
    expect(
      within(preview).getByRole('option', { name: 'Original for Recipient' }),
    ).toBeInTheDocument();
  });

  it('drops a selected copy that the next template does not print', async () => {
    const { container } = renderShell();
    const user = userEvent.setup();
    const preview = () => screen.getByRole('combobox', { name: 'Printed copy to preview' });
    await user.selectOptions(preview(), 'TRIPLICATE_FOR_SUPPLIER');
    expect(container.querySelector('[data-element="copy-mark"]')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /Compact invoice/ }));
    // The switch itself, not the page: phase 6's add-copy menu offers every copy the
    // template does *not* print, so "Triplicate for Supplier" is legitimately on screen
    // as something addable while being no longer previewed.
    expect(preview()).toHaveValue('');
    expect(container.querySelector('[data-element="copy-mark"]')).toBeNull();
  });

  it('says that nothing is persisted, rather than implying a save happened', () => {
    renderShell();
    expect(screen.getByText(/nothing is saved yet/i)).toBeInTheDocument();
  });

  it('survives a template list it cannot resolve instead of rendering a blank screen', () => {
    render(<DesignerShell templates={[]} initialTemplateId="missing" />);
    expect(screen.getByText('No template to design.')).toBeInTheDocument();
  });
});

describe('document renderer', () => {
  it('positions every zone and element in millimetres from the layout', () => {
    const { container } = render(<DocumentLayer layout={GST.layout} />);
    const header = container.querySelector('[data-section="sec-header"]') as HTMLElement;
    expect(header).toHaveStyle({ left: '10mm', top: '10mm', width: '190mm' });
    const title = container.querySelector('[data-element="el-title"]') as HTMLElement;
    expect(title).toHaveStyle({ left: '146mm', width: '44mm' });
  });

  it('prints static text as text, never as markup', () => {
    const hostile: CanvasDefinition = {
      ...GST.layout,
      sections: [
        {
          id: 'sec-x',
          type: 'CUSTOM',
          xMm: 0,
          yMm: 0,
          widthMm: 100,
          heightMm: 10,
          elements: [
            {
              id: 'el-x',
              type: 'TEXT',
              xMm: 0,
              yMm: 0,
              widthMm: 100,
              heightMm: 10,
              content: '<script>alert(1)</script>',
            },
          ],
        },
      ],
    };
    const { container } = render(<DocumentLayer layout={hostile} />);
    expect(container.querySelector('script')).toBeNull();
    expect(screen.getByText('<script>alert(1)</script>')).toBeInTheDocument();
  });

  it('resolves a binding to the sample document', () => {
    render(<DocumentLayer layout={GST.layout} />);
    expect(screen.getByText(SAMPLE_DOCUMENT.voucher.documentNumber)).toBeInTheDocument();
    expect(screen.getByText(SAMPLE_DOCUMENT.party.name)).toBeInTheDocument();
  });

  it('shows the path in brackets when a binding cannot be resolved', () => {
    const layout: CanvasDefinition = {
      ...GST.layout,
      sections: [
        {
          id: 'sec-x',
          type: 'CUSTOM',
          xMm: 0,
          yMm: 0,
          widthMm: 60,
          heightMm: 6,
          elements: [
            {
              id: 'el-unknown',
              type: 'FIELD_BINDING',
              xMm: 0,
              yMm: 0,
              widthMm: 60,
              heightMm: 6,
              bindingPath: 'voucher.not_a_real_field',
            },
          ],
        },
      ],
    };
    render(<DocumentLayer layout={layout} />);
    expect(screen.getByText('[voucher.not_a_real_field]')).toBeInTheDocument();
  });

  it('renders exactly the item columns the layout shows, in order', () => {
    const { container, unmount } = render(<DocumentLayer layout={GST.layout} />);
    const items = container.querySelector('[data-element="el-items"]') as HTMLElement;
    expect(
      within(items)
        .getAllByRole('columnheader')
        .map((cell) => cell.textContent),
    ).toEqual([
      '#',
      COLUMN_LABELS.description,
      COLUMN_LABELS.hsn_sac,
      COLUMN_LABELS.quantity,
      COLUMN_LABELS.unit,
      COLUMN_LABELS.rate,
      COLUMN_LABELS.taxable_value,
      COLUMN_LABELS.cgst_amount,
      COLUMN_LABELS.sgst_amount,
      COLUMN_LABELS.amount,
    ]);
    unmount();

    // A challan moves goods, not money: no tax column anywhere on it.
    const challan = render(<DocumentLayer layout={templateById('tpl-challan-a4')!.layout} />);
    const challanItems = challan.container.querySelector(
      '[data-element="el-items"]',
    ) as HTMLElement;
    expect(
      within(challanItems).queryByRole('columnheader', { name: COLUMN_LABELS.cgst_amount }),
    ).toBeNull();
  });

  it('prints a row per document line, plus the filler rows the layout asks for', () => {
    const { container } = render(<DocumentLayer layout={GST.layout} />);
    const table = container.querySelector('.janso-doc-table') as HTMLElement;
    const bodyRows = table.querySelectorAll('tbody tr');
    expect(bodyRows).toHaveLength(SAMPLE_DOCUMENT.lines.length + 2);
    expect(table.querySelectorAll('.janso-doc-table__blank')).toHaveLength(2);
  });

  it('puts the second description line under the item when the layout says so', () => {
    render(<DocumentLayer layout={GST.layout} />);
    expect(screen.getByText(/Lot NTC-RICE-0925/)).toBeInTheDocument();
  });

  it('renders the totals rows the layout lists, and the grand total stands out', () => {
    const { container } = render(<DocumentLayer layout={GST.layout} />);
    expect(screen.getByText(SAMPLE_DOCUMENT.totals.grandTotal)).toBeInTheDocument();
    expect(container.querySelector('.janso-doc-totals__row--grand')).not.toBeNull();
    expect(screen.getByText(/Amount in words:/)).toHaveTextContent(
      SAMPLE_DOCUMENT.totals.amountInWords,
    );
    // Subtotal is not in this template's row set, so it must not appear.
    expect(screen.queryByText('Subtotal')).not.toBeInTheDocument();
  });

  it('groups the tax summary the way the element asks', () => {
    const { container } = render(<DocumentLayer layout={GST.layout} />);
    const summary = container.querySelector('[data-element="el-tax"]') as HTMLElement;
    expect(within(summary).getByRole('columnheader', { name: 'HSN/SAC' })).toBeInTheDocument();
    expect(within(summary).getByText('10063020')).toBeInTheDocument();
    // Grouped by HSN, so a code appears once however many lines carry it.
    expect(within(summary).getAllByRole('row')).toHaveLength(
      SAMPLE_DOCUMENT.taxSummary.length + 1,
    );
  });

  it('draws the copy mark as part of the page', () => {
    const { container } = render(
      <DocumentLayer layout={GST.layout} copy="ORIGINAL_FOR_RECIPIENT" />,
    );
    expect(
      container.querySelector('[data-element="copy-mark"]')?.textContent,
    ).toBe('Original for Recipient');
  });

  it('uses a diagonal watermark when the layout chooses one', () => {
    const { container } = render(
      <DocumentLayer
        layout={templateById('tpl-challan-a4')!.layout}
        copy="DUPLICATE_FOR_TRANSPORTER"
      />,
    );
    expect(container.querySelector('.janso-doc-copymark')).toHaveTextContent(
      'Duplicate for Transporter',
    );
  });

  it('leaves the header blank on pre-printed stationery', () => {
    const layout: CanvasDefinition = {
      ...GST.layout,
      print: { ...GST.layout.print, prePrintedStationery: true },
    };
    const { container } = render(<DocumentLayer layout={layout} />);
    expect(container.querySelector('[data-element="el-company"]')).toBeNull();
    // The rest of the document is untouched.
    expect(container.querySelector('[data-element="el-items"]')).not.toBeNull();
  });

  it('places an asset by its id and names it for assistive technology', () => {
    render(<DocumentLayer layout={GST.layout} />);
    expect(screen.getByAltText('Nandini wordmark')).toBeInTheDocument();
  });

  it('says so when an element names an asset that is not there', () => {
    const layout: CanvasDefinition = {
      ...GST.layout,
      sections: [
        {
          id: 'sec-x',
          type: 'CUSTOM',
          xMm: 0,
          yMm: 0,
          widthMm: 40,
          heightMm: 20,
          elements: [
            {
              id: 'el-img',
              type: 'IMAGE',
              xMm: 0,
              yMm: 0,
              widthMm: 40,
              heightMm: 20,
              assetId: 'asset-missing',
            },
          ],
        },
      ],
    };
    render(<DocumentLayer layout={layout} />);
    expect(screen.getByText('No asset')).toBeInTheDocument();
  });

  it('renders a real upload through the signed download proxy, never the asset storage path', () => {
    const company = '01990000-0000-7000-8000-000000000001';
    const assetId = '01990000-0000-7000-8000-000000000002';
    const layout: CanvasDefinition = {
      ...GST.layout,
      sections: [
        {
          id: 'sec-x',
          type: 'CUSTOM',
          xMm: 0,
          yMm: 0,
          widthMm: 40,
          heightMm: 20,
          elements: [
            { id: 'el-img', type: 'IMAGE', xMm: 0, yMm: 0, widthMm: 40, heightMm: 20, assetId },
          ],
        },
      ],
    };
    render(
      <DocumentLayer
        layout={layout}
        company={company}
        assets={{ [assetId]: { downloadToken: 'signed-token', mimeType: 'image/png' } }}
      />,
    );
    expect(screen.getByAltText('Brand asset')).toHaveAttribute(
      'src',
      `/api/design-asset?company=${company}&asset=${assetId}&token=signed-token`,
    );
  });

  it('shows the empty state for a real asset id when no company or token is available', () => {
    const assetId = '01990000-0000-7000-8000-000000000002';
    const layout: CanvasDefinition = {
      ...GST.layout,
      sections: [
        {
          id: 'sec-x',
          type: 'CUSTOM',
          xMm: 0,
          yMm: 0,
          widthMm: 40,
          heightMm: 20,
          elements: [
            { id: 'el-img', type: 'IMAGE', xMm: 0, yMm: 0, widthMm: 40, heightMm: 20, assetId },
          ],
        },
      ],
    };
    render(<DocumentLayer layout={layout} />);
    expect(screen.getByText('No asset')).toBeInTheDocument();
  });

  it('shows a placeholder for a barcode rather than drawing a fake one', () => {
    render(<DocumentLayer layout={templateById('tpl-thermal-80')!.layout} />);
    expect(screen.getByText('CODE128')).toBeInTheDocument();
  });
});

describe('fixtures and model', () => {
  it('states the schema version the service will validate against', () => {
    expect(SCHEMA_VERSION).toBe('1.1.0');
    for (const template of SAMPLE_TEMPLATES) {
      expect(template.layout.schemaVersion).toBe(SCHEMA_VERSION);
    }
  });

  it('keeps every fixture binding inside the allowlisted roots', () => {
    const roots = new Set<string>(BINDING_ROOTS);
    for (const path of sampleBindingPaths()) {
      expect(roots.has(path.split('.')[0] as string)).toBe(true);
    }
    for (const template of SAMPLE_TEMPLATES) {
      for (const section of template.layout.sections) {
        for (const element of section.elements) {
          if (!element.bindingPath) continue;
          expect(roots.has(element.bindingPath.split('.')[0] as string)).toBe(true);
        }
      }
    }
  });

  it('resolves every binding a fixture template uses, so no preview has a hole', () => {
    const unresolved: string[] = [];
    for (const template of SAMPLE_TEMPLATES) {
      for (const section of template.layout.sections) {
        for (const element of section.elements) {
          if (element.bindingPath && sampleValue(element.bindingPath) === null) {
            unresolved.push(`${template.code}:${element.bindingPath}`);
          }
        }
      }
    }
    expect(unresolved).toEqual([]);
  });

  it('lays every element inside its page, so no fixture prints off the sheet', () => {
    const offPage: string[] = [];
    for (const template of SAMPLE_TEMPLATES) {
      const { page, sections } = template.layout;
      const width = page.widthMm ?? (page.size === 'THERMAL_80MM' ? 80 : 210);
      const height = page.heightMm ?? (page.size === 'THERMAL_80MM' ? 200 : 297);
      for (const section of sections) {
        if (section.xMm + section.widthMm > width + 0.01) offPage.push(`${template.code}:${section.id}:x`);
        if (section.yMm + section.heightMm > height + 0.01) offPage.push(`${template.code}:${section.id}:y`);
        for (const element of section.elements) {
          if (element.xMm + element.widthMm > section.widthMm + 0.01) {
            offPage.push(`${template.code}:${element.id}:x`);
          }
          if (element.yMm + element.heightMm > section.heightMm + 0.01) {
            offPage.push(`${template.code}:${element.id}:y`);
          }
        }
      }
    }
    expect(offPage).toEqual([]);
  });

  it('gives every template a column set whose widths fit its table', () => {
    for (const template of SAMPLE_TEMPLATES) {
      for (const section of template.layout.sections) {
        for (const element of section.elements) {
          if (element.type !== 'ITEM_TABLE' || !element.columns) continue;
          const total = element.columns
            .filter((column) => column.show)
            .reduce((sum, column) => sum + column.widthMm, 0);
          expect(total).toBeLessThanOrEqual(element.widthMm + 0.01);
        }
      }
    }
  });

  it('offers four starting points, including a roll and a document with no money on it', () => {
    expect(SAMPLE_TEMPLATES).toHaveLength(4);
    expect(SAMPLE_TEMPLATES.map((t) => t.layout.page.size)).toContain('THERMAL_80MM');
    const challan = templateById('tpl-challan-a4')!;
    const rows = challan.layout.sections.flatMap((s) => s.elements).flatMap((e) => e.totalsRows ?? []);
    expect(rows).toEqual([]);
  });
});
