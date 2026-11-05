/**
 * The column designer, the totals builder, and the dividers on the table itself.
 *
 * The load-bearing properties: a column set can never overflow its table, adding a column
 * never silently resizes the others, order is the printed order, a table is never left
 * empty, and dragging a divider at any zoom moves the same paper distance.
 */
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { PX_PER_MM } from '@janso/ui';
import { ColumnHandles } from '../app/(editor)/invoice-designer/ColumnHandles';
import { DesignerShell } from '../app/(editor)/invoice-designer/DesignerShell';
import {
  SAMPLE_TEMPLATES,
  templateById,
} from '../app/(editor)/invoice-designer/sample-templates';
import {
  MAX_COLUMNS,
  addColumn,
  addTotalsRow,
  availableColumns,
  availableTotalsRows,
  columnBudget,
  distributeColumns,
  moveColumn,
  resizeColumnBoundary,
  moveTotalsRow,
  removeColumn,
  removeTotalsRow,
  updateColumn,
  updateElement,
} from '../app/(editor)/invoice-designer/layout-edit';
import { targetById, targetsOf } from '../app/(editor)/invoice-designer/selection';
import type { CanvasDefinition } from '../app/(editor)/invoice-designer/layout-model';

const GST = templateById('tpl-gst-a4')!.layout;
const CHALLAN = templateById('tpl-challan-a4')!.layout;

function items(layout: CanvasDefinition) {
  return layout.sections.flatMap((s) => s.elements).find((e) => e.id === 'el-items')!;
}

function totals(layout: CanvasDefinition) {
  return layout.sections.flatMap((s) => s.elements).find((e) => e.id === 'el-totals')!;
}

function keys(layout: CanvasDefinition) {
  return (items(layout).columns ?? []).map((column) => column.key);
}

function renderShell(initialTemplateId = 'tpl-gst-a4') {
  return render(
    <DesignerShell templates={SAMPLE_TEMPLATES} initialTemplateId={initialTemplateId} />,
  );
}

describe('column model', () => {
  it('adds a column at the end with a width suited to its heading', () => {
    // Free up room first: the GST table is exactly full.
    const narrowed = updateColumn(GST, 'el-items', 'description', { widthMm: 30 });
    const next = addColumn(narrowed, 'el-items', 'batch');
    const batch = items(next).columns?.at(-1);
    expect(batch).toMatchObject({ key: 'batch', show: true, widthMm: 18 });
  });

  it('adds a column hidden when the table is full, so nothing else changes width', () => {
    const before = items(GST).columns!.map((column) => column.widthMm);
    const next = addColumn(GST, 'el-items', 'mrp');
    const added = items(next).columns?.find((column) => column.key === 'mrp');
    expect(added?.show).toBe(false);
    // Every existing column kept its width.
    expect(items(next).columns!.filter((c) => c.key !== 'mrp').map((c) => c.widthMm)).toEqual(
      before,
    );
    expect(columnBudget(items(next)).usedMm).toBe(190);
  });

  it('refuses a duplicate and caps the count', () => {
    expect(keys(addColumn(GST, 'el-items', 'description'))).toEqual(keys(GST));

    let layout = GST;
    for (const key of availableColumns(items(GST))) layout = addColumn(layout, 'el-items', key);
    expect(items(layout).columns).toHaveLength(MAX_COLUMNS);
  });

  it('removes a column but never leaves the table empty', () => {
    const next = removeColumn(GST, 'el-items', 'hsn_sac');
    expect(keys(next)).not.toContain('hsn_sac');
    expect(keys(next)).toHaveLength(keys(GST).length - 1);

    // Down to one, then refuse: an empty item table prints a blank frame.
    let stripped = GST;
    for (const key of keys(GST)) stripped = removeColumn(stripped, 'el-items', key);
    expect(items(stripped).columns).toHaveLength(1);
  });

  it('moves a column one place, and holds at the ends', () => {
    expect(keys(moveColumn(GST, 'el-items', 'hsn_sac', 'left')).slice(0, 3)).toEqual([
      'serial_no',
      'hsn_sac',
      'description',
    ]);
    expect(keys(moveColumn(GST, 'el-items', 'serial_no', 'left'))).toEqual(keys(GST));
    expect(keys(moveColumn(GST, 'el-items', 'amount', 'right'))).toEqual(keys(GST));
  });

  it('fits the shown columns to the table, keeping their proportions', () => {
    const half = updateColumn(GST, 'el-items', 'description', { widthMm: 26 });
    expect(columnBudget(items(half)).usedMm).toBe(164);

    const fitted = distributeColumns(half, 'el-items');
    expect(columnBudget(items(fitted)).usedMm).toBe(190);
    // The description was the widest and stays the widest.
    const widths = items(fitted).columns!.filter((c) => c.show);
    const widest = widths.reduce((a, b) => (a.widthMm > b.widthMm ? a : b));
    expect(widest.key).toBe('description');
  });

  it('fits an under-filled table up as well as an over-filled one down', () => {
    const narrow = updateElement(
      updateColumn(GST, 'el-items', 'description', { widthMm: 10 }),
      'el-items',
      { widthMm: 100 },
    );
    const fitted = distributeColumns(narrow, 'el-items');
    expect(columnBudget(items(fitted)).usedMm).toBe(100);
  });

  it('leaves a table with no shown columns alone rather than dividing by zero', () => {
    let hidden = GST;
    for (const key of keys(GST)) hidden = updateColumn(hidden, 'el-items', key, { show: false });
    expect(distributeColumns(hidden, 'el-items')).toEqual(hidden);
  });

  it('offers only the columns a table does not carry', () => {
    const available = availableColumns(items(GST));
    expect(available).toContain('batch');
    expect(available).not.toContain('description');
  });
});

describe('a divider moves a boundary', () => {
  it('takes the millimetres from the next shown column, so the table total holds', () => {
    const next = resizeColumnBoundary(GST, 'el-items', 'description', 62);
    const columns = items(next).columns!;
    expect(columns.find((c) => c.key === 'description')?.widthMm).toBe(62);
    // The next shown column gave up exactly what the first gained.
    expect(columns.find((c) => c.key === 'hsn_sac')?.widthMm).toBe(6);
    expect(columnBudget(items(next)).usedMm).toBe(190);
  });

  it('works on an exactly full table, where typing a width is capped', () => {
    // The GST table is full, so `updateColumn` refuses to widen...
    expect(
      items(updateColumn(GST, 'el-items', 'description', { widthMm: 62 })).columns!.find(
        (c) => c.key === 'description',
      )?.widthMm,
    ).toBe(52);
    // ...and dragging the boundary moves it, because the neighbour pays.
    expect(
      items(resizeColumnBoundary(GST, 'el-items', 'description', 62)).columns!.find(
        (c) => c.key === 'description',
      )?.widthMm,
    ).toBe(62);
  });

  it('never squeezes the neighbour out of existence', () => {
    const next = resizeColumnBoundary(GST, 'el-items', 'description', 900);
    const columns = items(next).columns!;
    // description + hsn_sac = 68mm, so the most it can take leaves the neighbour 1mm.
    expect(columns.find((c) => c.key === 'description')?.widthMm).toBe(67);
    expect(columns.find((c) => c.key === 'hsn_sac')?.widthMm).toBe(1);
    expect(columnBudget(items(next)).usedMm).toBe(190);
  });

  it('skips hidden columns when finding the neighbour to trade with', () => {
    const hidden = updateColumn(GST, 'el-items', 'hsn_sac', { show: false });
    const next = resizeColumnBoundary(hidden, 'el-items', 'description', 60);
    const columns = items(next).columns!;
    expect(columns.find((c) => c.key === 'description')?.widthMm).toBe(60);
    // Quantity is the next *shown* column, so it pays the 8mm.
    expect(columns.find((c) => c.key === 'quantity')?.widthMm).toBe(6);
    expect(columns.find((c) => c.key === 'hsn_sac')?.widthMm).toBe(16);
  });

  it('caps the last column at the table edge, having no neighbour to take from', () => {
    const next = resizeColumnBoundary(GST, 'el-items', 'amount', 40);
    // The other columns spend 168mm, so the last can have 22mm and no more.
    expect(items(next).columns!.find((c) => c.key === 'amount')?.widthMm).toBe(22);
  });

  it('ignores a column the table does not carry', () => {
    expect(resizeColumnBoundary(GST, 'el-items', 'mrp', 20)).toEqual(GST);
  });
});

describe('totals model', () => {
  it('adds, removes and refuses a duplicate', () => {
    const next = addTotalsRow(GST, 'el-totals', 'subtotal');
    expect(totals(next).totalsRows).toContain('subtotal');
    expect(totals(addTotalsRow(next, 'el-totals', 'subtotal')).totalsRows).toEqual(
      totals(next).totalsRows,
    );
    expect(totals(removeTotalsRow(next, 'el-totals', 'subtotal')).totalsRows).not.toContain(
      'subtotal',
    );
  });

  it('may end up empty, because a challan carries no money', () => {
    let stripped = GST;
    for (const row of totals(GST).totalsRows!) {
      stripped = removeTotalsRow(stripped, 'el-totals', row);
    }
    expect(totals(stripped).totalsRows).toEqual([]);
  });

  it('moves a row, and holds at the ends', () => {
    const rows = totals(GST).totalsRows!;
    expect(totals(moveTotalsRow(GST, 'el-totals', 'cgst', 'up')).totalsRows?.slice(0, 2)).toEqual([
      'cgst',
      'taxable_value',
    ]);
    expect(totals(moveTotalsRow(GST, 'el-totals', rows[0]!, 'up')).totalsRows).toEqual(rows);
    expect(totals(moveTotalsRow(GST, 'el-totals', rows.at(-1)!, 'down')).totalsRows).toEqual(rows);
  });

  it('offers only the rows a block does not print', () => {
    expect(availableTotalsRows(totals(GST))).toContain('subtotal');
    expect(availableTotalsRows(totals(GST))).not.toContain('grand_total');
  });
});

describe('column designer', () => {
  async function openTable() {
    const view = renderShell();
    const user = userEvent.setup();
    await user.click(screen.getByRole('option', { name: 'item table' }));
    return { ...view, user };
  }

  it('states the budget as a number and as a shape', async () => {
    await openTable();
    expect(screen.getByText(/190 of 190 mm used/)).toBeInTheDocument();
    const bar = screen.getByRole('progressbar', { name: 'Column width used' });
    expect(bar).toHaveAttribute('aria-valuetext', '190 of 190 millimetres');
  });

  it('adds a column and the printed table gains it', async () => {
    const { user, container } = await openTable();
    // Make room, so the new column arrives shown.
    const description = screen.getByLabelText('Description of goods width');
    await user.clear(description);
    await user.type(description, '30{Enter}');

    await user.selectOptions(screen.getByLabelText('Column to add'), 'batch');
    await user.click(screen.getByRole('button', { name: 'Add' }));

    const table = container.querySelector('[data-element="el-items"]') as HTMLElement;
    expect(within(table).getByRole('columnheader', { name: 'Batch' })).toBeInTheDocument();
    expect(within(table).getByText('PCM2609A')).toBeInTheDocument();
  });

  it('says a column arrives hidden when the table is full', async () => {
    const { user, container } = await openTable();
    await user.selectOptions(screen.getByLabelText('Column to add'), 'mrp');
    await user.click(screen.getByRole('button', { name: 'Add' }));

    expect(screen.getByRole('switch', { name: 'Show MRP' })).toHaveAttribute(
      'aria-checked',
      'false',
    );
    const table = container.querySelector('[data-element="el-items"]') as HTMLElement;
    expect(within(table).queryByRole('columnheader', { name: 'MRP' })).toBeNull();
  });

  it('removes a column and the table loses it', async () => {
    const { user, container } = await openTable();
    await user.click(screen.getByRole('button', { name: 'Remove HSN/SAC' }));
    const table = container.querySelector('[data-element="el-items"]') as HTMLElement;
    expect(within(table).queryByRole('columnheader', { name: 'HSN/SAC' })).toBeNull();
    expect(screen.queryByRole('switch', { name: 'Show HSN/SAC' })).not.toBeInTheDocument();
  });

  it('reorders a column and the printed heading order follows', async () => {
    const { user, container } = await openTable();
    await user.click(screen.getByRole('button', { name: 'Move HSN/SAC left' }));

    const table = container.querySelector('[data-element="el-items"]') as HTMLElement;
    const headings = within(table)
      .getAllByRole('columnheader')
      .map((cell) => cell.textContent);
    expect(headings.slice(0, 3)).toEqual(['#', 'HSN/SAC', 'Description of goods']);
  });

  it('disables the move that would leave the list', async () => {
    await openTable();
    expect(screen.getByRole('button', { name: 'Move # left' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Move Amount right' })).toBeDisabled();
  });

  it('renames a heading only when asked, and the table reprints it', async () => {
    const { user, container } = await openTable();
    expect(screen.queryByLabelText('Description of goods heading')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Rename Description of goods' }));
    await user.type(screen.getByLabelText('Description of goods heading'), 'Particulars');

    const table = container.querySelector('[data-element="el-items"]') as HTMLElement;
    expect(within(table).getByRole('columnheader', { name: 'Particulars' })).toBeInTheDocument();
  });

  it('fits the columns to the table in one action', async () => {
    const { user } = await openTable();
    const description = screen.getByLabelText('Description of goods width');
    await user.clear(description);
    await user.type(description, '26{Enter}');
    expect(screen.getByText(/164 of 190 mm used/)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Fit to table width' }));
    expect(screen.getByText(/the table is exactly full/)).toBeInTheDocument();
  });
});

describe('totals builder', () => {
  async function openTotals() {
    const view = renderShell();
    const user = userEvent.setup();
    await user.click(screen.getByRole('option', { name: 'totals block' }));
    return { ...view, user };
  }

  it('adds a row and the page prints it', async () => {
    const { user, container } = await openTotals();
    await user.selectOptions(screen.getByLabelText('Totals row to add'), 'subtotal');
    await user.click(screen.getByRole('button', { name: 'Add' }));

    const block = container.querySelector('[data-element="el-totals"]') as HTMLElement;
    expect(within(block).getByText('Subtotal')).toBeInTheDocument();
  });

  it('moves a row and the printed order follows', async () => {
    const { user, container } = await openTotals();
    await user.click(screen.getByRole('button', { name: 'Move CGST up' }));

    const block = container.querySelector('[data-element="el-totals"]') as HTMLElement;
    const labels = [...block.querySelectorAll('.janso-doc-totals__row')].map((row) =>
      row.textContent?.trim().split(/\s{2,}|\n/)[0],
    );
    expect(labels[0]).toContain('CGST');
  });

  it('removes every row and says what that means', async () => {
    const { user } = await openTotals();
    for (const name of ['Taxable value', 'CGST', 'SGST', 'Round off', 'Total', 'Amount in words']) {
      await user.click(screen.getByRole('button', { name: `Remove ${name}` }));
    }
    expect(screen.getByText(/carries no money/)).toBeInTheDocument();
  });
});

describe('column dividers on the canvas', () => {
  const target = targetById(targetsOf(GST), 'el-items')!;

  it('draws one divider per shown column, at its right edge', () => {
    const { container } = render(
      <ColumnHandles target={target} element={items(GST)} zoom={1} onResize={vi.fn()} />,
    );
    const grips = container.querySelectorAll('.janso-canvas__column-grip');
    expect(grips).toHaveLength(10);
    // The first column is 8mm wide, so its divider sits at 8mm.
    expect(grips[0]).toHaveStyle({ left: '8mm' });
    // The last lands on the table's full width.
    expect(grips[9]).toHaveStyle({ left: '190mm' });
  });

  it('draws nothing when every column is hidden', () => {
    let hidden = GST;
    for (const key of keys(GST)) hidden = updateColumn(hidden, 'el-items', key, { show: false });
    const { container } = render(
      <ColumnHandles target={target} element={items(hidden)} zoom={1} onResize={vi.fn()} />,
    );
    expect(container.querySelector('.janso-canvas__columns')).toBeNull();
  });

  it('converts a pointer drag into paper millimetres', async () => {
    const onResize = vi.fn();
    const { container } = render(
      <ColumnHandles target={target} element={items(GST)} zoom={1} onResize={onResize} />,
    );
    const grip = container.querySelector('[data-column="description"]') as HTMLElement;
    grip.setPointerCapture = vi.fn();
    grip.hasPointerCapture = () => true;
    grip.releasePointerCapture = vi.fn();

    const user = userEvent.setup();
    await user.pointer([
      { target: grip, keys: '[MouseLeft>]', coords: { clientX: 200, clientY: 100 } },
      { target: grip, coords: { clientX: 200 + 10 * PX_PER_MM, clientY: 100 } },
    ]);
    // 10mm of screen travel at 100% zoom is 10mm of paper: 52 + 10.
    expect(onResize).toHaveBeenLastCalledWith('el-items', 'description', 62);
  });

  it('moves the same paper distance at any zoom', async () => {
    const onResize = vi.fn();
    const { container } = render(
      <ColumnHandles target={target} element={items(GST)} zoom={0.5} onResize={onResize} />,
    );
    const grip = container.querySelector('[data-column="description"]') as HTMLElement;
    grip.setPointerCapture = vi.fn();
    grip.hasPointerCapture = () => true;
    grip.releasePointerCapture = vi.fn();

    const user = userEvent.setup();
    await user.pointer([
      { target: grip, keys: '[MouseLeft>]', coords: { clientX: 100, clientY: 50 } },
      // Half the zoom, so twice the screen pixels for the same 10mm of paper.
      { target: grip, coords: { clientX: 100 + 10 * PX_PER_MM * 0.5, clientY: 50 } },
    ]);
    expect(onResize).toHaveBeenLastCalledWith('el-items', 'description', 62);
  });

  it('shows the live width while dragging and stops when the pointer is released', async () => {
    const { container } = render(
      <ColumnHandles target={target} element={items(GST)} zoom={1} onResize={vi.fn()} />,
    );
    const grip = container.querySelector('[data-column="rate"]') as HTMLElement;
    grip.setPointerCapture = vi.fn();
    grip.hasPointerCapture = () => true;
    grip.releasePointerCapture = vi.fn();

    const user = userEvent.setup();
    await user.pointer({ target: grip, keys: '[MouseLeft>]', coords: { clientX: 300, clientY: 80 } });
    expect(screen.getByTestId('column-width-readout')).toHaveTextContent('Rate 18 mm');

    await user.pointer({ target: grip, keys: '[/MouseLeft]' });
    expect(screen.queryByTestId('column-width-readout')).not.toBeInTheDocument();
  });

  it('appears on the canvas only for a selected item table', async () => {
    renderShell();
    const user = userEvent.setup();
    expect(screen.queryByTestId('column-handles')).not.toBeInTheDocument();

    await user.click(screen.getByRole('option', { name: 'item table' }));
    expect(screen.getByTestId('column-handles')).toBeInTheDocument();

    await user.click(screen.getByRole('option', { name: 'TAX INVOICE' }));
    expect(screen.queryByTestId('column-handles')).not.toBeInTheDocument();
  });

  it('offers no dividers on a shipped template, which is read-only', async () => {
    renderShell('tpl-thermal-80');
    await userEvent.setup().click(screen.getByRole('option', { name: 'item table' }));
    expect(screen.queryByTestId('column-handles')).not.toBeInTheDocument();
  });

  it('drags a divider in the real editor and the table reprints', async () => {
    const { container } = renderShell();
    const user = userEvent.setup();
    await user.click(screen.getByRole('option', { name: 'item table' }));

    const grip = container.querySelector('[data-column="description"]') as HTMLElement;
    grip.setPointerCapture = vi.fn();
    grip.hasPointerCapture = () => true;
    grip.releasePointerCapture = vi.fn();

    await user.pointer([
      { target: grip, keys: '[MouseLeft>]', coords: { clientX: 200, clientY: 100 } },
      { target: grip, coords: { clientX: 200 - 10 * PX_PER_MM, clientY: 100 } },
      { target: grip, keys: '[/MouseLeft]' },
    ]);

    expect(screen.getByLabelText('Description of goods width')).toHaveValue('42');
    // The 10mm it gave up went to the next column, not to the table's free space.
    expect(screen.getByLabelText('HSN/SAC width')).toHaveValue('26');
    expect(screen.getByText(/the table is exactly full/)).toBeInTheDocument();

    const table = container.querySelector('[data-element="el-items"]') as HTMLElement;
    const heading = within(table).getByRole('columnheader', { name: 'Description of goods' });
    expect(heading).toHaveStyle({ width: '42mm' });
  });
});

describe('the challan, which carries no money', () => {
  it('has a table with no tax columns and no totals block at all', () => {
    const table = CHALLAN.sections
      .flatMap((section) => section.elements)
      .find((element) => element.type === 'ITEM_TABLE')!;
    expect((table.columns ?? []).map((column) => column.key)).not.toContain('cgst_amount');
    expect(
      CHALLAN.sections.flatMap((s) => s.elements).some((e) => e.type === 'TOTALS_BLOCK'),
    ).toBe(false);
  });
});
