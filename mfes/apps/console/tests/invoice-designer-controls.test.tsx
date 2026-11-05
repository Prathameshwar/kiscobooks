/**
 * The controls, end to end: change a value and the page changes under your hands.
 *
 * These are the tests that matter most for this phase. Unit tests prove a control reports
 * the right number and the edit model clamps it; only these prove the loop closes — the
 * inspector's control, the layout in state, the renderer's output, and the canvas's own
 * geometry all agreeing on one value.
 */
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { DesignerShell } from '../app/(editor)/invoice-designer/DesignerShell';
import { SAMPLE_TEMPLATES } from '../app/(editor)/invoice-designer/sample-templates';

function renderShell(initialTemplateId = 'tpl-gst-a4') {
  return render(
    <DesignerShell templates={SAMPLE_TEMPLATES} initialTemplateId={initialTemplateId} />,
  );
}

/** Selecting through the canvas, which is how a designer gets to an element. */
async function select(user: ReturnType<typeof userEvent.setup>, name: string) {
  await user.click(screen.getByRole('option', { name }));
}

async function setMeasure(
  user: ReturnType<typeof userEvent.setup>,
  label: string,
  value: string,
) {
  const input = screen.getByLabelText(label);
  await user.clear(input);
  await user.type(input, `${value}{Enter}`);
}

describe('page controls', () => {
  it('changes the paper and the page resizes', async () => {
    renderShell();
    const user = userEvent.setup();
    expect(screen.getByTestId('design-canvas-paper')).toHaveStyle({ width: '210mm' });

    await user.selectOptions(screen.getByLabelText('Paper size'), 'A5');
    expect(screen.getByTestId('design-canvas-paper')).toHaveStyle({
      width: '148mm',
      height: '210mm',
    });
  });

  it('turns the page landscape and the axes swap', async () => {
    renderShell();
    await userEvent.setup().click(screen.getByRole('radio', { name: 'Landscape' }));
    expect(screen.getByTestId('design-canvas-paper')).toHaveStyle({
      width: '297mm',
      height: '210mm',
    });
  });

  it('refuses to rotate roll stock, and says why', async () => {
    renderShell('tpl-thermal-80');
    expect(screen.getByRole('radio', { name: 'Landscape' })).toBeDisabled();
    expect(screen.getByText(/Roll stock has a fixed width/)).toBeInTheDocument();
  });

  it('offers custom dimensions only for a custom paper, and applies them', async () => {
    renderShell();
    const user = userEvent.setup();
    expect(screen.queryByLabelText('Page width')).not.toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText('Paper size'), 'CUSTOM');
    await setMeasure(user, 'Page width', '120');
    await setMeasure(user, 'Page height', '180');
    expect(screen.getByTestId('design-canvas-paper')).toHaveStyle({
      width: '120mm',
      height: '180mm',
    });
  });

  it('moves a margin and the printable guide follows', async () => {
    renderShell();
    await setMeasure(userEvent.setup(), 'left margin', '25');
    expect(screen.getByTestId('design-canvas-margins')).toHaveStyle({
      left: '25mm',
      width: '175mm',
    });
  });

  it('never lets the margins eat the page', async () => {
    renderShell();
    await setMeasure(userEvent.setup(), 'left margin', '400');
    // Capped so at least 10mm of printable width survives.
    expect(screen.getByLabelText('left margin')).toHaveValue('100');
  });

  it('changes the grid step and the canvas redraws it', async () => {
    renderShell();
    await setMeasure(userEvent.setup(), 'Grid step', '10');
    expect(screen.getByTestId('design-canvas-grid')).toHaveStyle({ backgroundSize: '10mm 10mm' });
  });

  it('switches the document font and the paper inherits it', async () => {
    renderShell();
    const { container } = renderShell();
    await userEvent
      .setup()
      .selectOptions(within(container).getByLabelText('Font family'), 'Georgia, serif');
    expect(container.querySelector('.janso-doc')).toHaveStyle({ fontFamily: 'Georgia, serif' });
  });

  it('blanks the header for pre-printed stationery', async () => {
    const { container } = renderShell();
    expect(container.querySelector('[data-element="el-company"]')).not.toBeNull();
    await userEvent.setup().click(screen.getByRole('switch', { name: 'Pre-printed stationery' }));
    expect(container.querySelector('[data-element="el-company"]')).toBeNull();
    // Only the header: the rest of the document is untouched.
    expect(container.querySelector('[data-element="el-items"]')).not.toBeNull();
  });

  it('moves the copy mark into a watermark', async () => {
    const { container } = renderShell();
    const user = userEvent.setup();
    await user.selectOptions(
      screen.getByRole('combobox', { name: 'Printed copy to preview' }),
      'ORIGINAL_FOR_RECIPIENT',
    );
    expect(container.querySelector('.janso-doc-copymark')).toBeNull();

    await user.click(
      within(screen.getByRole('radiogroup', { name: 'Copy mark position' })).getByRole('radio', {
        name: 'Mark',
      }),
    );
    expect(container.querySelector('.janso-doc-copymark')).toHaveTextContent(
      'Original for Recipient',
    );
  });
});

describe('element controls', () => {
  it('moves an element and both the page and the selection ring follow', async () => {
    const { container } = renderShell();
    const user = userEvent.setup();
    await select(user, 'TAX INVOICE');
    await setMeasure(user, 'X position', '100');

    expect(container.querySelector('[data-element="el-title"]')).toHaveStyle({ left: '100mm' });
    // The ring is drawn from the same model, in absolute page millimetres.
    expect(screen.getByRole('option', { name: 'TAX INVOICE' })).toHaveStyle({ left: '110mm' });
    expect(screen.getByTestId('selection-readout')).toHaveTextContent('44 × 7 mm');
  });

  it('keeps an element inside its zone however large the number typed', async () => {
    renderShell();
    const user = userEvent.setup();
    await select(user, 'TAX INVOICE');
    await setMeasure(user, 'X position', '900');
    // The header zone is 190mm wide and the element 44mm, so 146mm is as far as it goes.
    expect(screen.getByLabelText('X position')).toHaveValue('146');
  });

  it('edits static text and the page reprints it', async () => {
    const { container } = renderShell();
    const user = userEvent.setup();
    await select(user, 'TAX INVOICE');
    const text = screen.getByLabelText('Static text');
    await user.clear(text);
    await user.type(text, 'BILL OF SUPPLY');
    expect(container.querySelector('[data-element="el-title"]')).toHaveTextContent(
      'BILL OF SUPPLY',
    );
  });

  it('restyles type and the page follows', async () => {
    const { container } = renderShell();
    const user = userEvent.setup();
    await select(user, 'TAX INVOICE');

    await setMeasure(user, 'Font size', '20');
    await user.click(
      within(screen.getByRole('radiogroup', { name: 'Text alignment' })).getByRole('radio', {
        name: 'Centre',
      }),
    );
    await user.click(screen.getByRole('switch', { name: 'Italic' }));

    const title = container.querySelector('[data-element="el-title"]') as HTMLElement;
    expect(title).toHaveStyle({ fontSize: '20pt', textAlign: 'center', fontStyle: 'italic' });
  });

  it('sets a colour from a swatch and refuses one the schema would reject', async () => {
    const { container } = renderShell();
    const user = userEvent.setup();
    await select(user, 'TAX INVOICE');

    await user.click(within(screen.getByRole('group', { name: 'Text colour presets' })).getByLabelText('#5b6c00'));
    expect(container.querySelector('[data-element="el-title"]')).toHaveStyle({ color: '#5b6c00' });

    const hex = screen.getByLabelText('Text colour');
    await user.clear(hex);
    await user.type(hex, 'red{Enter}');
    expect(container.querySelector('[data-element="el-title"]')).toHaveStyle({ color: '#5b6c00' });
  });

  it('gives a border a width the first time it is turned on, so it is visible', async () => {
    const { container } = renderShell();
    const user = userEvent.setup();
    await select(user, 'TAX INVOICE');
    await user.click(screen.getByRole('radio', { name: 'Solid' }));

    expect(container.querySelector('[data-element="el-title"]')).toHaveStyle({
      borderStyle: 'solid',
      borderWidth: '0.2mm',
    });
    // The thickness and colour rows appear only once there is a border to describe.
    expect(screen.getByLabelText('Border thickness')).toHaveValue('0.2');
  });

  it('offers image fit for an image and symbology for a symbol, and nothing else', async () => {
    renderShell();
    const user = userEvent.setup();
    await select(user, 'image');
    expect(screen.getByRole('radiogroup', { name: 'Image fit' })).toBeInTheDocument();
    expect(screen.queryByLabelText('Symbology')).not.toBeInTheDocument();

    await select(user, 'voucher.irn');
    expect(screen.getByLabelText('Symbology')).toBeInTheDocument();
    expect(screen.queryByRole('radiogroup', { name: 'Image fit' })).not.toBeInTheDocument();
  });

  it('regroups the tax summary and the page regroups with it', async () => {
    const { container } = renderShell();
    const user = userEvent.setup();
    await select(user, 'tax summary');
    await user.click(screen.getByRole('radio', { name: 'Rate' }));

    const summary = container.querySelector('[data-element="el-tax"]') as HTMLElement;
    expect(within(summary).getByRole('columnheader', { name: 'Rate' })).toBeInTheDocument();
  });

  it('hides an item column and the table loses it', async () => {
    const { container } = renderShell();
    const user = userEvent.setup();
    await select(user, 'item table');
    await user.click(screen.getByRole('switch', { name: 'Show HSN/SAC' }));

    const table = container.querySelector('[data-element="el-items"]') as HTMLElement;
    expect(within(table).queryByRole('columnheader', { name: 'HSN/SAC' })).toBeNull();
    // The width it freed is now spendable.
    expect(screen.getByText(/174 of 190 mm used/)).toBeInTheDocument();
  });

  it('widens a column only as far as the table has room', async () => {
    renderShell();
    const user = userEvent.setup();
    await select(user, 'item table');
    await setMeasure(user, 'Description of goods width', '120');
    // The table is already full, so the column keeps the width it had.
    expect(screen.getByLabelText('Description of goods width')).toHaveValue('52');
  });

  it('renames a zone and the tree and the canvas agree on the new name', async () => {
    renderShell();
    const user = userEvent.setup();
    await select(user, 'Header');
    const title = screen.getByLabelText('Zone title');
    await user.clear(title);
    await user.type(title, 'Letterhead');

    expect(screen.getByRole('treeitem', { name: /Letterhead/ })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Letterhead' })).toBeInTheDocument();
  });
});

describe('edit bookkeeping', () => {
  it('counts the changes and keeps saying nothing is saved', async () => {
    renderShell();
    const user = userEvent.setup();
    expect(screen.getByTestId('edit-count')).toHaveTextContent('No changes · nothing is saved yet');

    await setMeasure(user, 'Grid step', '10');
    expect(screen.getByTestId('edit-count')).toHaveTextContent('1 change · nothing is saved yet');
    await setMeasure(user, 'Grid step', '15');
    expect(screen.getByTestId('edit-count')).toHaveTextContent('2 changes');
  });

  it('keeps each template’s edits apart', async () => {
    renderShell();
    const user = userEvent.setup();
    await setMeasure(user, 'Grid step', '20');

    await user.click(screen.getByRole('button', { name: /Compact invoice/ }));
    expect(screen.getByLabelText('Grid step')).toHaveValue('5');

    await user.click(screen.getByRole('button', { name: /GST tax invoice/ }));
    expect(screen.getByLabelText('Grid step')).toHaveValue('20');
  });

  it('refuses to edit a shipped template, as the domain refuses to', async () => {
    renderShell('tpl-thermal-80');
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('read-only');
    expect(screen.getByLabelText('Paper size')).toBeDisabled();
    expect(screen.getByLabelText('Grid step')).toBeDisabled();
    expect(screen.getByRole('switch', { name: 'Snap to grid' })).toBeDisabled();
  });
});
