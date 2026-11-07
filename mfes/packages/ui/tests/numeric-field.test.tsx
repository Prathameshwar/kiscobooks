/**
 * `AmountField`, `QuantityField` and the hook under them.
 *
 * One thing matters more than everything else here: **the value is a string and stays one.**
 * Every amount and quantity column in the platform is `DECIMAL(19,4)`; a `number` cannot hold
 * `0.1 + 0.2`, MySQL re-scales a narrower scale without erroring, and an invoice total is the
 * worst place in a product to meet either (CLAUDE.md §4). So the tests check what is *emitted*,
 * not only what is painted.
 *
 * After that: the paste cases, because people paste from spreadsheets and bank statements and a
 * field that refuses `1,234.00` gets a product abandoned; and the focused-versus-blurred display
 * rule, because editing a field that inserts separators under the caret is miserable while
 * reading a column of ungrouped digits is worse.
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { AmountField, QuantityField } from '../src/components/NumericField';
import { DisplayConfigProvider } from '../src/lib/display-config';
import { canonicalise, settle, storable, STORAGE_SCALE } from '../src/lib/numeric-input';
import { DEFAULT_DISPLAY_CONFIG } from '../src/lib/format';

import { useState } from 'react';

/** A controlled host, so what the field emits is what the next render receives. */
function Controlled({
  initial = '',
  field = 'amount',
  onValue,
  config,
  ...rest
}: {
  initial?: string;
  field?: 'amount' | 'quantity';
  onValue?: (value: string) => void;
  config?: Parameters<typeof DisplayConfigProvider>[0]['config'];
  [key: string]: unknown;
}) {
  const [value, setValue] = useState(initial);
  const Field = field === 'amount' ? AmountField : QuantityField;
  return (
    <DisplayConfigProvider config={config}>
      <Field
        label={field === 'amount' ? 'Rate' : 'Quantity'}
        value={value}
        onChange={(next: string) => {
          setValue(next);
          onValue?.(next);
        }}
        {...rest}
      />
    </DisplayConfigProvider>
  );
}

const box = (name = 'Rate') => screen.getByRole('textbox', { name: new RegExp(name) });

describe('what the field emits', () => {
  it('emits a string, never a number', async () => {
    const onValue = vi.fn();
    const user = userEvent.setup();
    render(<Controlled onValue={onValue} />);

    await user.type(box(), '1234.5678');

    const emitted = onValue.mock.calls.at(-1)![0];
    expect(emitted).toBe('1234.5678');
    expect(typeof emitted).toBe('string');
  });

  it('keeps four decimals and refuses a fifth', async () => {
    const onValue = vi.fn();
    const user = userEvent.setup();
    render(<Controlled onValue={onValue} />);

    await user.type(box(), '1.23456');

    // The fifth place is not silently truncated — a truncated figure is a wrong figure.
    expect(onValue.mock.calls.map(([value]) => value)).not.toContain('1.2346');
    expect(box()).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByText(`Up to ${STORAGE_SCALE} decimal places.`)).toBeInTheDocument();
  });

  it('does not lose the point while a figure is half typed', async () => {
    const user = userEvent.setup();
    render(<Controlled />);

    await user.type(box(), '12.');
    // A controlled field that dropped the unstorable `12.` would delete the point as it was
    // typed, which makes a decimal impossible to enter.
    expect(box()).toHaveValue('12.');

    await user.type(box(), '5');
    expect(box()).toHaveValue('12.5');
  });

  it('tidies what is legal but awkward, on blur', async () => {
    const onValue = vi.fn();
    const user = userEvent.setup();
    render(<Controlled onValue={onValue} />);

    await user.type(box(), '.5');
    await user.tab();

    expect(onValue).toHaveBeenLastCalledWith('0.5');
  });

  it('reports a settled numeric value only after blur and only when valid', async () => {
    const onCommit = vi.fn();
    const user = userEvent.setup();
    render(<Controlled field="quantity" onCommit={onCommit} />);
    await user.type(box('Quantity'), '123');
    expect(onCommit).not.toHaveBeenCalled();
    await user.tab();
    expect(onCommit).toHaveBeenCalledWith('123');
    await user.click(box('Quantity'));
    await user.clear(box('Quantity'));
    await user.type(box('Quantity'), '12..5');
    await user.tab();
    expect(onCommit).toHaveBeenCalledTimes(1);
  });

  it('keeps unstorable text rather than reverting it', async () => {
    const user = userEvent.setup();
    render(<Controlled initial="100" />);

    await user.clear(box());
    await user.type(box(), '12..5');
    await user.tab();

    // `MeasureField` reverts because its value is a number with a usable previous state. Here
    // the text *is* the value, and silently discarding what someone typed into a money field
    // is how a wrong figure gets committed unnoticed.
    expect(box()).toHaveValue('12..5');
    expect(box()).toHaveAttribute('aria-invalid', 'true');
  });
});

describe('the display rule', () => {
  it('groups when blurred and shows canonical text when focused', async () => {
    const user = userEvent.setup();
    render(<Controlled initial="1234567.5" />);

    // Blurred: the way the company reads figures. Indian grouping by default.
    expect(box()).toHaveValue('12,34,567.50');

    await user.click(box());
    expect(box()).toHaveValue('1234567.5');

    await user.tab();
    expect(box()).toHaveValue('12,34,567.50');
  });

  it('follows a western-grouping company', async () => {
    render(
      <Controlled
        initial="1234567.5"
        config={{ digitGrouping: 'western', groupSeparator: ',', decimalSeparator: '.' }}
      />,
    );
    expect(box()).toHaveValue('1,234,567.50');
  });

  it('follows a company whose separators are swapped', async () => {
    // The case that breaks a naive parser: the group separator is `.`, so `1.234,56` is one
    // thousand two hundred and thirty-four and fifty-six hundredths.
    const onValue = vi.fn();
    const user = userEvent.setup();
    render(
      <Controlled
        config={{ digitGrouping: 'western', groupSeparator: '.', decimalSeparator: ',' }}
        onValue={onValue}
      />,
    );

    // Pasted, not typed: with `.` as the *group* separator, typing one mid-entry is noise and
    // is stripped — which is right. The real case is a figure arriving from a spreadsheet.
    await user.click(box());
    await user.paste('1.234,56');
    expect(onValue).toHaveBeenLastCalledWith('1234.56');
  });

  it('types a decimal figure key by key under a comma-decimal company', async () => {
    // The focused box used to show the canonical `12.5`, and the next key re-read that point as
    // a *group* separator: `12,5` then `6` stored 1256.
    const onValue = vi.fn();
    const user = userEvent.setup();
    render(
      <Controlled
        config={{ digitGrouping: 'western', groupSeparator: '.', decimalSeparator: ',' }}
        onValue={onValue}
      />,
    );
    await user.click(box());
    await user.keyboard('12,56');
    expect(onValue).toHaveBeenLastCalledWith('12.56');
    expect(box()).toHaveValue('12,56');

    // And an existing figure edits the same way.
    await user.tab();
    await user.click(box());
    expect(box()).toHaveValue('12,56');
    await user.keyboard('{End}7');
    expect(onValue).toHaveBeenLastCalledWith('12.567');
  });

  it('refuses a minus sign where a negative is not allowed, rather than dropping it', async () => {
    const onValue = vi.fn();
    const user = userEvent.setup();
    render(<Controlled onValue={onValue} />);
    await user.click(box());
    await user.paste('-50');
    expect(onValue).not.toHaveBeenCalledWith('50');
    expect(box()).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByText('Enter a figure without a minus sign.')).toBeInTheDocument();
  });

  it('shows an absent value as empty, not as zero', () => {
    render(<Controlled initial="" />);
    // A blank rate and a zero rate are different facts, and `0.00` in an empty box invites
    // someone to leave it there.
    expect(box()).toHaveValue('');
  });

  it('uses the company’s amount precision, and a caller override', () => {
    render(<Controlled initial="1.5" config={{ amountPrecision: 2 }} />);
    expect(box()).toHaveValue('1.50');

    render(<Controlled initial="1.5" precision={4} config={{ amountPrecision: 2 }} />);
    // A unit rate is routinely shown at four places where a total is shown at two.
    expect(screen.getAllByRole('textbox', { name: /Rate/ }).at(-1)).toHaveValue('1.5000');
  });
});

describe('pasting from somewhere else', () => {
  it.each([
    ['grouped', '1,234.00', '1234.00'],
    ['with a symbol', '₹1,234.50', '1234.50'],
    ['with the code', '1234.50 INR', '1234.50'],
    ['with a non-breaking space', '1 234.50', '1234.50'],
    ['already canonical', '1234.5', '1234.5'],
  ])('reads a %s figure', async (_name, pasted, expected) => {
    const onValue = vi.fn();
    const user = userEvent.setup();
    render(<Controlled onValue={onValue} />);

    await user.click(box());
    await user.paste(pasted);

    expect(onValue).toHaveBeenLastCalledWith(expected);
  });

  it('reads the accounting negative, and keeps the sign where a negative is not allowed', () => {
    const config = DEFAULT_DISPLAY_CONFIG;
    expect(canonicalise('(1,234.00)', config, true)).toBe('-1234.00');
    // A quantity and a rate are not negative — but a pasted `-50` is not a 50 either. The sign
    // used to be dropped, which stored the opposite of what was written; kept, it is refused.
    expect(canonicalise('(1,234.00)', config, false)).toBe('-1234.00');
    expect(storable(canonicalise('-50', config, false), { allowNegative: false })).toBe(false);
  });
});

describe('quantities', () => {
  it('uses the company’s quantity precision, which differs from money', () => {
    render(
      <Controlled
        field="quantity"
        initial="2.5"
        config={{ quantityPrecision: 3, amountPrecision: 2 }}
      />,
    );
    expect(box('Quantity')).toHaveValue('2.500');
  });

  it('refuses zero when the caller needs a positive quantity', async () => {
    const user = userEvent.setup();
    render(<Controlled field="quantity" requirePositive />);

    await user.type(box('Quantity'), '0');

    expect(screen.getByText('Enter a quantity greater than zero.')).toBeInTheDocument();
    expect(box('Quantity')).toHaveAttribute('aria-invalid', 'true');
  });

  it('allows a zero rate, because a reward unit has one', async () => {
    const user = userEvent.setup();
    render(<Controlled />);

    await user.type(box(), '0');
    expect(box()).not.toHaveAttribute('aria-invalid');
  });

  it('shows the unit beside the box when the caller knows it', () => {
    render(<Controlled field="quantity" unit="kg" />);
    expect(screen.getByText('kg')).toBeInTheDocument();
  });

  it('does not guess a unit it was not given', () => {
    // "each" is not a safe default for something sold by the kilogram.
    render(<Controlled field="quantity" />);
    expect(screen.queryByText('each')).not.toBeInTheDocument();
  });
});

describe('the currency sits beside the box', () => {
  it('shows the symbol outside the input', () => {
    render(<Controlled initial="100" />);

    expect(screen.getByText('₹')).toBeInTheDocument();
    // Not inside: a symbol in the box is a character the caret has to be driven past.
    expect(box()).toHaveValue('100.00');
  });

  it('takes a per-line currency override', () => {
    render(<Controlled initial="100" unit="$" />);
    expect(screen.getByText('$')).toBeInTheDocument();
  });
});

describe('errors', () => {
  it('lets the caller’s message win over the parse', async () => {
    render(<Controlled initial="85" error="Below the agreed floor." />);
    // The caller knows things the field cannot — that this rate is under a price floor.
    expect(screen.getByText('Below the agreed floor.')).toBeInTheDocument();
  });
});

describe('the pure helpers', () => {
  const config = DEFAULT_DISPLAY_CONFIG;

  it('canonicalises to text with no separators', () => {
    expect(canonicalise('  12,34,567.89  ', config, false)).toBe('1234567.89');
    expect(canonicalise('', config, false)).toBe('');
    expect(canonicalise('+5', config, false)).toBe('5');
  });

  it('knows what can be stored', () => {
    expect(storable('', { allowNegative: false })).toBe(true);
    expect(storable('0', { allowNegative: false })).toBe(true);
    expect(storable('1234.5678', { allowNegative: false })).toBe(true);
    expect(storable('1234.56789', { allowNegative: false })).toBe(false);
    expect(storable('-1', { allowNegative: false })).toBe(false);
    expect(storable('-1', { allowNegative: true })).toBe(true);
    expect(storable('1e3', { allowNegative: false })).toBe(false);
    expect(storable('1.', { allowNegative: false })).toBe(false);
  });

  it('settles awkward but legal text', () => {
    expect(settle('1.')).toBe('1');
    expect(settle('.5')).toBe('0.5');
    expect(settle('007')).toBe('7');
    expect(settle('0')).toBe('0');
    expect(settle('0.5')).toBe('0.5');
    expect(settle('-')).toBe('');
    expect(settle('')).toBe('');
  });
});
