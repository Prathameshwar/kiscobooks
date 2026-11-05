import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { Badge, ChoiceCard, FieldGroup, FieldPair, Select, TextField } from '../src';

/**
 * The required mark, the grouping primitives and the choice card.
 *
 * The load-bearing assertions here are the two that protect the console's 426 label-based
 * test queries and the accessible name of a card-shaped checkbox. Both were defects found by
 * building this: a mark inside the label broke `getByLabelText`, and a card whose whole
 * surface is the label announced its description as part of its name.
 */

describe('the required mark', () => {
  it('is drawn for a required field and not for an optional one', () => {
    const { container } = render(
      <>
        <TextField label="Legal name" required value="" onChange={() => {}} />
        <TextField label="Trading name" value="" onChange={() => {}} />
      </>,
    );
    const marks = container.querySelectorAll('.janso-required');
    expect(marks).toHaveLength(1);
    expect(marks[0]).toHaveTextContent('*');
  });

  it('leaves the accessible name and the label text exactly the label', () => {
    render(<TextField label="Legal name" required value="" onChange={() => {}} />);
    // Both query styles, because the console uses both: `getByRole` honours `aria-hidden`
    // and `getByLabelText` reads the label's raw text. A mark inside the label passes the
    // first and fails the second, which is how it was nearly shipped.
    expect(screen.getByRole('textbox', { name: 'Legal name' })).toBeInTheDocument();
    expect(screen.getByLabelText('Legal name')).toBeInTheDocument();
  });

  it('is hidden from assistive technology, because the control already says it', () => {
    const { container } = render(<TextField label="Legal name" required value="" onChange={() => {}} />);
    expect(container.querySelector('.janso-required')).toHaveAttribute('aria-hidden', 'true');
    // The fact itself lives on the control, where a browser and a screen reader read it.
    expect(screen.getByRole('textbox', { name: 'Legal name' })).toBeRequired();
  });

  it('marks a required select the same way', () => {
    const { container } = render(
      <Select label="Entity type" required value="a" options={[{ value: 'a', label: 'A' }]} onChange={() => {}} />,
    );
    expect(container.querySelector('.janso-required')).toBeInTheDocument();
    expect(screen.getByLabelText('Entity type')).toBeInTheDocument();
  });

  it('draws no mark on a hidden label, which has nothing to mark', () => {
    const { container } = render(
      <TextField label="Search" hideLabel required value="" onChange={() => {}} />,
    );
    expect(container.querySelector('.janso-required')).toBeNull();
    expect(screen.getByLabelText('Search')).toBeInTheDocument();
  });
});

describe('field grouping', () => {
  it('keeps a header control out of the group accessible name', () => {
    render(<FieldGroup title="VAT registration" headerEnd={<button type="button">Add registration later</button>}>
      <TextField label="VAT number" />
    </FieldGroup>);
    const group = screen.getByRole('group', { name: 'VAT registration' });
    const control = within(group).getByRole('button', { name: 'Add registration later' });
    expect(control.closest('legend')).toHaveTextContent('VAT registration');
    expect(within(group).getByLabelText('VAT number')).toBeInTheDocument();
  });

  it('is a real group, named by its legend', () => {
    render(
      <FieldGroup title="Numbers" hint="How figures print.">
        <TextField label="Decimal separator" value="." onChange={() => {}} />
      </FieldGroup>,
    );
    // A `fieldset`/`legend`, so focus entering the field announces "Numbers" — the context a
    // sighted user takes from the heading above it.
    const group = screen.getByRole('group', { name: 'Numbers' });
    expect(within(group).getByLabelText('Decimal separator')).toBeInTheDocument();
    expect(group).toHaveTextContent('How figures print.');
  });

  it('puts a pair side by side without wrapping either field in anything else', () => {
    const { container } = render(
      <FieldPair>
        <TextField label="Decimal separator" value="." onChange={() => {}} />
        <TextField label="Thousands separator" value="," onChange={() => {}} />
      </FieldPair>,
    );
    const pair = container.querySelector('.janso-fieldpair');
    expect(pair?.children).toHaveLength(2);
    expect(screen.getByLabelText('Decimal separator')).toBeInTheDocument();
    expect(screen.getByLabelText('Thousands separator')).toBeInTheDocument();
  });
});

describe('ChoiceCard', () => {
  const card = (props: Partial<Parameters<typeof ChoiceCard>[0]> = {}) =>
    render(
      <ChoiceCard
        title="Expiry dates"
        description="Record and report expiry against each batch."
        badges={<Badge tone="warn">Permanent</Badge>}
        checked={false}
        onChange={() => {}}
        {...props}
      />,
    );

  it('names itself with its title alone', () => {
    card();
    // Not "Expiry dates Permanent Record and report expiry against each batch", which is what
    // a label wrapping the whole card produces and what a screen reader would read out in a
    // list of controls.
    expect(screen.getByRole('checkbox', { name: 'Expiry dates' })).toBeInTheDocument();
  });

  it('describes itself with the badge and the description, after the name', () => {
    card();
    const box = screen.getByRole('checkbox', { name: 'Expiry dates' });
    expect(box).toHaveAccessibleDescription(/Permanent/);
    expect(box).toHaveAccessibleDescription(/Record and report expiry/);
  });

  it('toggles from a click anywhere on the card, including the description', async () => {
    const onChange = vi.fn();
    card({ onChange });
    const user = userEvent.setup();
    // The whole point: the two lines explaining the setting are part of the target that
    // explains it, not a dead zone beside a 16px box.
    await user.click(screen.getByText('Record and report expiry against each batch.'));
    expect(onChange).toHaveBeenCalledWith(true);
  });

  it('reports its depth, so a dependency chain reads as an indent', () => {
    const { container } = card({ depth: 2 });
    expect(container.querySelector('.janso-choice')).toHaveAttribute('data-depth', '2');
  });

  it('marks itself checked for styling, and says why it was turned on', () => {
    const { container } = card({ checked: true, note: 'Also on, because this needs it: Batches.' });
    expect(container.querySelector('.janso-choice')).toHaveAttribute('data-checked', 'true');
    expect(screen.getByText(/Also on, because this needs it/)).toBeInTheDocument();
  });

  it('refuses to toggle when disabled', async () => {
    const onChange = vi.fn();
    card({ disabled: true, onChange });
    await userEvent.setup().click(screen.getByText('Record and report expiry against each batch.'));
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByRole('checkbox', { name: 'Expiry dates' })).toBeDisabled();
  });
});
