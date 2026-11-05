/**
 * Phase 6 in the editor: placing fields, seeing what is bound rather than what it says,
 * reshaping onto a roll, editing the copy set, and being told what will print wrong.
 *
 * Geometry is the GST fixture (`invoice-designer-multiselect.test.tsx` documents it). Zone
 * names come from `zoneLabel`, so the untitled header zone reads "Header" and the titled
 * one reads "Document details".
 */
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { DesignerShell } from '../app/(editor)/invoice-designer/DesignerShell';
import { SAMPLE_TEMPLATES } from '../app/(editor)/invoice-designer/sample-templates';

const user = () => userEvent.setup();

function renderShell(initialTemplateId = 'tpl-gst-a4') {
  return render(
    <DesignerShell templates={SAMPLE_TEMPLATES} initialTemplateId={initialTemplateId} />,
  );
}

/** Select a zone through the rail's tree, which is how a destination gets chosen. */
async function pickZone(session: ReturnType<typeof userEvent.setup>, name: string | RegExp) {
  const tree = screen.getByRole('tree', { name: 'Page structure' });
  await session.click(within(tree).getByRole('treeitem', { name }));
}

async function setMeasure(
  session: ReturnType<typeof userEvent.setup>,
  label: string,
  value: string,
) {
  const input = screen.getByLabelText(label);
  await session.clear(input);
  await session.type(input, `${value}{Enter}`);
}

const palette = () => screen.getByRole('searchbox', { name: 'Find a field' });

describe('the field palette', () => {
  it('lists what the document can print, grouped by root, with the value beside it', () => {
    renderShell();
    // `party.name` and `address.shipping_name` are indistinguishable by name; the values
    // are what a designer actually chooses between.
    const place = screen.getByRole('button', { name: 'Place Name (party.name)' });
    // Truncated to fit a 280px rail: "Sahyadri Retail Private Limited" is 31 characters.
    expect(place).toHaveTextContent('Sahyadri Retail Private Limit…');
    expect(screen.getByText('voucher')).toBeInTheDocument();
    expect(screen.getByText('bank')).toBeInTheDocument();
  });

  it('searches the value as well as the path', async () => {
    renderShell();
    const session = user();
    await session.type(palette(), 'gstin');
    expect(screen.getByRole('button', { name: 'Place Gstin (company.gstin)' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /bank.ifsc/ })).not.toBeInTheDocument();

    // Nobody knows the shipping address is called `address.shipping`; they know the road
    // it is on.
    await session.clear(palette());
    await session.type(palette(), 'Paud Road');
    expect(
      screen.getByRole('button', { name: 'Place Shipping (address.shipping)' }),
    ).toBeInTheDocument();
  });

  it('says so when nothing matches', async () => {
    renderShell();
    await user().type(palette(), 'zzz');
    expect(screen.getByText(/Nothing matches/)).toBeInTheDocument();
  });

  it('places into the first zone until another is chosen, and names the one it has', async () => {
    renderShell();
    const session = user();
    // Nothing selected is not a dead palette: the page's first zone takes a click.
    expect(screen.getByTestId('palette-destination')).toHaveTextContent('Places into “Header”');
    expect(screen.getByRole('button', { name: 'Place Phone (company.phone)' })).toBeEnabled();

    await pickZone(session, /Footer/);
    expect(screen.getByTestId('palette-destination')).toHaveTextContent('Places into “Footer”');
    expect(screen.getByRole('button', { name: 'Place Phone (company.phone)' })).toBeEnabled();
  });

  it('takes the zone of a selected element, since an element cannot contain one', async () => {
    renderShell();
    await user().click(screen.getByRole('option', { name: 'TAX INVOICE' }));
    expect(screen.getByTestId('palette-destination')).toHaveTextContent('Places into “Header”');
  });

  it('places a field, prints it, and selects it so the first drag moves it', async () => {
    const { container } = renderShell();
    const session = user();
    await pickZone(session, /Billing shipping/);
    await session.click(screen.getByRole('button', { name: 'Place Phone (company.phone)' }));

    const placed = container.querySelector('[data-element="el-phone"]');
    expect(placed).toBeInTheDocument();
    expect(placed).toHaveTextContent('Phone');
    expect(placed).toHaveTextContent('+91 20 4567 8900');
    // Below whatever was already there, not on top of it: the lowest element in that zone
    // is the GSTIN line at 19mm, 4mm tall, so the new field starts at 24mm.
    expect(placed).toHaveStyle({ top: '24mm', left: '0mm' });
    expect(screen.getByTestId('selection-readout')).toHaveTextContent('Phone');
  });

  it('clamps to the bottom edge when the zone is full, rather than refusing', async () => {
    const { container } = renderShell();
    const session = user();
    // The footer's lowest element ends at 39mm of a 43mm zone, so a 5mm field cannot sit
    // below it. Deliberately visible and overlapping: it arrives selected and one drag
    // moves it, which beats a palette click that silently does nothing.
    await pickZone(session, /Footer/);
    await session.click(screen.getByRole('button', { name: 'Place Phone (company.phone)' }));
    expect(container.querySelector('[data-element="el-phone"]')).toHaveStyle({ top: '38mm' });
  });

  it('marks a field the page already prints, and still allows another', async () => {
    const { container } = renderShell();
    const session = user();
    const ifsc = screen.getByRole('button', { name: 'Place Ifsc (bank.ifsc)' });
    expect(ifsc).toHaveTextContent('on the page');
    // A GSTIN in the header and again beside the signature is a real document, so a
    // placed field is marked rather than disabled.
    expect(within(ifsc).getByText('on the page')).toBeInTheDocument();

    await pickZone(session, /Totals/);
    await session.click(ifsc);
    expect(container.querySelector('[data-element="el-ifsc"]')).toBeInTheDocument();
  });

  it('refuses on a shipped template, and says why', async () => {
    renderShell('tpl-thermal-80');
    expect(screen.getByTestId('palette-destination')).toHaveTextContent('read-only');
    expect(screen.getByRole('button', { name: 'Place Phone (company.phone)' })).toBeDisabled();
  });

  it('is one undo', async () => {
    const { container } = renderShell();
    const session = user();
    await pickZone(session, /Footer/);
    await session.click(screen.getByRole('button', { name: 'Place Phone (company.phone)' }));
    await session.click(screen.getByRole('button', { name: 'Undo' }));
    expect(container.querySelector('[data-element="el-phone"]')).toBeNull();
  });
});

describe('placeholder and resolved values', () => {
  const mode = () => screen.getByLabelText('What the page prints in place of data');

  it('shows sample data by default', () => {
    const { container } = renderShell();
    expect(container.querySelector('[data-element="el-no"]')).toHaveTextContent(
      'NTC/25-26/001847',
    );
  });

  it('swaps every value for the binding behind it, and keeps the labels', async () => {
    const { container } = renderShell();
    await user().selectOptions(mode(), 'placeholder');

    const number = container.querySelector('[data-element="el-no"]');
    // The label is static text the document always prints, so it survives the mode.
    expect(number).toHaveTextContent('Invoice no.');
    expect(number).toHaveTextContent('{{voucher.document_number}}');
    expect(number).not.toHaveTextContent('NTC/25-26/001847');
  });

  it('names the column in a table cell and the row in a totals block', async () => {
    const { container } = renderShell();
    await user().selectOptions(mode(), 'placeholder');

    const table = container.querySelector('[data-element="el-items"]');
    // The heading already says "Description", so the cell carries the leaf alone.
    expect(table).toHaveTextContent('{{description}}');
    expect(table).not.toHaveTextContent('Basmati rice');

    const totals = container.querySelector('[data-element="el-totals"]');
    expect(totals).toHaveTextContent('{{grand_total}}');
    // The printed label stays: a totals block says "Total" whatever is in the amount.
    expect(totals).toHaveTextContent('Total{{grand_total}}');
  });

  it('keeps the geometry, because that is what the canvas is for', async () => {
    const { container } = renderShell();
    const before = container.querySelectorAll('[data-element="el-items"] tbody tr').length;
    await user().selectOptions(mode(), 'placeholder');
    expect(container.querySelectorAll('[data-element="el-items"] tbody tr')).toHaveLength(before);
  });

  it('is a view and not an edit, so it leaves the history alone', async () => {
    renderShell();
    await user().selectOptions(mode(), 'placeholder');
    expect(screen.getByTestId('edit-count')).toHaveTextContent('No changes');
    expect(screen.getByRole('button', { name: 'Undo' })).toBeDisabled();
  });
});

describe('the problems panel', () => {
  it('is absent while there is nothing to fix', () => {
    renderShell();
    expect(screen.queryByTestId('warnings')).not.toBeInTheDocument();
  });

  it('reports a zone the margins have pushed out of the printable area', async () => {
    renderShell();
    // 20mm side margins leave 170mm of printable width for zones that are 190mm wide.
    await setMeasure(user(), 'right margin', '20');

    const warnings = screen.getByTestId('warnings');
    expect(within(warnings).getAllByText('Error').length).toBeGreaterThan(0);
    expect(warnings).toHaveTextContent(/past the right edge of the printable area/);
    expect(screen.getByRole('heading', { name: 'Problems' })).toBeInTheDocument();
  });

  it('selects the offender, so the sentence has something to point at', async () => {
    const session = user();
    renderShell();
    await setMeasure(session, 'right margin', '20');

    const first = within(screen.getByTestId('warnings')).getAllByRole('button')[0]!;
    await session.click(first);
    // The header is the first zone down the page, so it is the first row.
    expect(screen.getByTestId('selection-readout')).toHaveTextContent('Header');
  });

  it('clears once the layout is fixed', async () => {
    const session = user();
    renderShell();
    await setMeasure(session, 'right margin', '20');
    expect(screen.queryByTestId('warnings')).toBeInTheDocument();

    await setMeasure(session, 'right margin', '10');
    expect(screen.queryByTestId('warnings')).not.toBeInTheDocument();
  });
});

describe('paper presets', () => {
  const picker = () => screen.getByLabelText('Apply a paper preset');

  it('states the paper a layout is already on', () => {
    renderShell();
    expect(picker()).toHaveValue('a4-invoice');
  });

  it('reshapes onto a roll in one action, leaving no problems behind', async () => {
    const { container } = renderShell();
    await user().selectOptions(picker(), 'thermal-80');

    expect(picker()).toHaveValue('thermal-80');
    expect(screen.getByTestId('design-canvas-paper')).toHaveStyle({ width: '80mm' });
    expect(container.querySelector('[data-section="sec-header"]')).toHaveStyle({ width: '74mm' });
    // The whole point: a preset must not hand back a layout that needs repairing.
    expect(screen.queryByTestId('warnings')).not.toBeInTheDocument();
  });

  it('is one undo, which is the honest way back from a lossy reshape', async () => {
    const { container } = renderShell();
    const session = user();
    await session.selectOptions(picker(), 'thermal-58');
    await session.click(screen.getByRole('button', { name: 'Undo' }));

    expect(picker()).toHaveValue('a4-invoice');
    expect(container.querySelector('[data-section="sec-header"]')).toHaveStyle({ width: '190mm' });
  });

  it('is refused on a shipped template', async () => {
    renderShell('tpl-thermal-80');
    expect(picker()).toBeDisabled();
  });
});

describe('the printed copy set', () => {
  it('lists the copies in printed order', () => {
    renderShell();
    expect(screen.getByRole('button', { name: 'Remove Original for Recipient' })).toBeDisabled;
    expect(
      screen.getByRole('button', { name: 'Move Original for Recipient earlier' }),
    ).toBeDisabled();
    expect(
      screen.getByRole('button', { name: 'Move Triplicate for Supplier later' }),
    ).toBeDisabled();
  });

  it('adds a copy, and the preview switch offers it', async () => {
    renderShell();
    const session = user();
    await session.selectOptions(screen.getByLabelText('Add a printed copy'), 'EXTRA_COPY');

    const preview = screen.getByLabelText('Printed copy to preview');
    expect(within(preview).getByRole('option', { name: 'Extra Copy' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Remove Extra Copy' })).toBeEnabled();
  });

  it('reorders the printed set', async () => {
    renderShell();
    await user().click(
      screen.getByRole('button', { name: 'Move Duplicate for Transporter earlier' }),
    );
    const names = screen
      .getAllByRole('button', { name: /^Remove / })
      .map((node) => node.getAttribute('aria-label'));
    expect(names[0]).toBe('Remove Duplicate for Transporter');
  });

  it('never removes the last copy, because a template that prints none prints nothing', async () => {
    renderShell();
    const session = user();
    await session.click(screen.getByRole('button', { name: 'Remove Duplicate for Transporter' }));
    await session.click(screen.getByRole('button', { name: 'Remove Triplicate for Supplier' }));

    expect(screen.getByRole('button', { name: 'Remove Original for Recipient' })).toBeDisabled();
  });

  it('prints the mark of the previewed copy', async () => {
    const { container } = renderShell();
    await user().selectOptions(
      screen.getByLabelText('Printed copy to preview'),
      'DUPLICATE_FOR_TRANSPORTER',
    );
    expect(container.querySelector('[data-element="copy-mark"]')).toHaveTextContent(
      'Duplicate for Transporter',
    );
  });
});
