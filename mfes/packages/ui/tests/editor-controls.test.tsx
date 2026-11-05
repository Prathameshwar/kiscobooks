/**
 * The inspector's controls.
 *
 * The load-bearing properties: each control is one tab stop, the keyboard does what the
 * pointer does, a half-typed number never reaches the layout, and a colour that the
 * schema would reject is refused at the control rather than normalised into something the
 * API will bounce later.
 */
import { render, screen, within } from '@testing-library/react';
import { useState } from 'react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import {
  ColourField,
  EditorSelect,
  EditorTextField,
  MeasureField,
  SegmentedControl,
  Toggle,
} from '../src/components/EditorControls';

describe('MeasureField', () => {
  it('shows the value with its unit and reports a committed number', async () => {
    const onChange = vi.fn();
    render(<MeasureField label="Width" value={44} onChange={onChange} />);
    const input = screen.getByLabelText('Width');
    expect(input).toHaveValue('44');
    expect(screen.getByText('mm')).toBeInTheDocument();

    const user = userEvent.setup();
    await user.clear(input);
    await user.type(input, '52{Enter}');
    expect(onChange).toHaveBeenLastCalledWith(52);
  });

  it('does not report a half-typed number, so the page cannot flicker to 1mm', async () => {
    const onChange = vi.fn();
    render(<MeasureField label="Width" value={44} onChange={onChange} />);
    const user = userEvent.setup();
    const input = screen.getByLabelText('Width');
    await user.clear(input);
    await user.type(input, '1.');
    expect(onChange).not.toHaveBeenCalled();
  });

  it('steps with the arrows, ten times coarser with shift', async () => {
    const onChange = vi.fn();
    render(<MeasureField label="X" value={10} onChange={onChange} step={1} />);
    const user = userEvent.setup();
    const input = screen.getByLabelText('X');
    input.focus();

    await user.keyboard('{ArrowUp}');
    expect(onChange).toHaveBeenLastCalledWith(11);
    await user.keyboard('{ArrowDown}');
    expect(onChange).toHaveBeenLastCalledWith(9);
    await user.keyboard('{Shift>}{ArrowUp}{/Shift}');
    expect(onChange).toHaveBeenLastCalledWith(20);
  });

  it('clamps to the range instead of letting a negative width through', async () => {
    const onChange = vi.fn();
    render(<MeasureField label="Width" value={5} onChange={onChange} min={1} max={190} />);
    const user = userEvent.setup();
    const input = screen.getByLabelText('Width');
    await user.clear(input);
    await user.type(input, '-40{Enter}');
    expect(onChange).toHaveBeenLastCalledWith(1);

    await user.clear(input);
    await user.type(input, '9999{Enter}');
    expect(onChange).toHaveBeenLastCalledWith(190);
  });

  it('marks unparseable input invalid and restores the real value on Escape', async () => {
    const onChange = vi.fn();
    render(<MeasureField label="Width" value={44} onChange={onChange} />);
    const user = userEvent.setup();
    const input = screen.getByLabelText('Width');
    await user.clear(input);
    await user.type(input, 'abc');
    expect(input).toHaveAttribute('aria-invalid', 'true');

    await user.keyboard('{Escape}');
    expect(input).toHaveValue('44');
    expect(onChange).not.toHaveBeenCalled();
  });

  it('keeps an invalid number on Enter so it can be corrected, and reverts on blur', async () => {
    const onChange = vi.fn();
    render(<MeasureField label="Width" value={44} onChange={onChange} />);
    const user = userEvent.setup();
    const input = screen.getByLabelText('Width');
    await user.clear(input);
    await user.type(input, 'abc{Enter}');
    expect(input).toHaveValue('abc');
    expect(input).toHaveAttribute('aria-invalid', 'true');
    expect(onChange).not.toHaveBeenCalled();

    await user.tab();
    expect(input).toHaveValue('44');
  });

  it('commits on blur, because a designer clicks away rather than pressing Enter', async () => {
    const onChange = vi.fn();
    render(<MeasureField label="Width" value={44} onChange={onChange} />);
    const user = userEvent.setup();
    const input = screen.getByLabelText('Width');
    await user.clear(input);
    await user.type(input, '60');
    await user.tab();
    expect(onChange).toHaveBeenLastCalledWith(60);
  });

  it('accepts a comma decimal, which half the world types', async () => {
    const onChange = vi.fn();
    render(<MeasureField label="X" value={1} onChange={onChange} />);
    const user = userEvent.setup();
    const input = screen.getByLabelText('X');
    await user.clear(input);
    await user.type(input, '12,5{Enter}');
    expect(onChange).toHaveBeenLastCalledWith(12.5);
  });

  it('shows a placeholder when the property is not set on this element', () => {
    render(
      <MeasureField label="Font size" value={Number.NaN} onChange={vi.fn()} unit="pt" placeholder="inherit" />,
    );
    expect(screen.getByLabelText('Font size')).toHaveAttribute('placeholder', 'inherit');
    expect(screen.getByLabelText('Font size')).toHaveValue('');
  });
});

describe('SegmentedControl', () => {
  const options = [
    { value: 'left', label: '◀' },
    { value: 'center', label: '■' },
    { value: 'right', label: '▶' },
  ] as const;

  it('prints its question on a form page, and takes its name from it', () => {
    // On a form there is no inspector row to carry the label: the options alone were a guess.
    render(
      <SegmentedControl label="Align" value="center" options={options} onChange={vi.fn()} showLabel />,
    );
    const question = screen.getByText('Align');
    const group = screen.getByRole('radiogroup', { name: 'Align' });
    expect(group).toHaveAttribute('aria-labelledby', question.id);
    expect(group).not.toHaveAttribute('aria-label');
    expect(group.closest('.janso-segmented-field')).not.toBeNull();
  });

  it('moves focus with the selection on the arrow keys', async () => {
    // Left on the previous button — unchecked and out of the tab order — a screen reader read the
    // wrong option and Space selected the old one again.
    function Host() {
      const [value, setValue] = useState<'left' | 'center' | 'right'>('left');
      return <SegmentedControl label="Align" value={value} options={options} onChange={setValue} />;
    }
    const user = userEvent.setup();
    render(<Host />);
    const radios = screen.getAllByRole('radio');
    radios[0]!.focus();
    await user.keyboard('{ArrowRight}');
    expect(radios[1]).toHaveFocus();
    expect(radios[1]).toHaveAttribute('aria-checked', 'true');
    await user.keyboard(' ');
    expect(radios[1]).toHaveAttribute('aria-checked', 'true');
  });

  it('leaves focus on the selected option when the caller refuses the change', async () => {
    // The sales bill asks before switching mode; focus used to move to the option not chosen.
    const user = userEvent.setup();
    render(<SegmentedControl label="Align" value="left" options={options} onChange={vi.fn()} />);
    const radios = screen.getAllByRole('radio');
    radios[0]!.focus();
    await user.keyboard('{ArrowRight}');
    expect(radios[0]).toHaveFocus();
  });

  it('keeps the inspector’s bare form by default', () => {
    render(<SegmentedControl label="Align" value="center" options={options} onChange={vi.fn()} />);
    expect(screen.queryByText('Align')).not.toBeInTheDocument();
    expect(document.querySelector('.janso-segmented-field')).toBeNull();
  });

  it('is a radiogroup with exactly one tab stop', () => {
    render(
      <SegmentedControl label="Align" value="center" options={options} onChange={vi.fn()} />,
    );
    const group = screen.getByRole('radiogroup', { name: 'Align' });
    const radios = within(group).getAllByRole('radio');
    expect(radios).toHaveLength(3);
    expect(radios.filter((radio) => radio.getAttribute('tabindex') === '0')).toHaveLength(1);
    expect(radios[1]).toHaveAttribute('aria-checked', 'true');
  });

  it('moves and commits with the arrows, wrapping around the ends', async () => {
    const onChange = vi.fn();
    render(<SegmentedControl label="Align" value="center" options={options} onChange={onChange} />);
    const user = userEvent.setup();
    screen.getAllByRole('radio')[1]!.focus();

    await user.keyboard('{ArrowRight}');
    expect(onChange).toHaveBeenLastCalledWith('right');
    await user.keyboard('{ArrowLeft}');
    expect(onChange).toHaveBeenLastCalledWith('left');
  });

  it('selects on click', async () => {
    const onChange = vi.fn();
    render(<SegmentedControl label="Align" value="left" options={options} onChange={onChange} />);
    await userEvent.setup().click(screen.getAllByRole('radio')[2]!);
    expect(onChange).toHaveBeenCalledWith('right');
  });

  it('puts the tab stop on the first option when nothing is chosen yet', () => {
    render(<SegmentedControl label="Align" value={null} options={options} onChange={vi.fn()} />);
    expect(screen.getAllByRole('radio')[0]).toHaveAttribute('tabindex', '0');
  });
});

describe('ColourField', () => {
  it('pairs a picker with the hex a brand guideline actually gives you', async () => {
    const onChange = vi.fn();
    render(<ColourField label="Colour" value="#1e40af" onChange={onChange} fallback="#101114" />);
    expect(screen.getByLabelText('Colour picker')).toHaveValue('#1e40af');

    const user = userEvent.setup();
    const hex = screen.getByLabelText('Colour');
    await user.clear(hex);
    await user.type(hex, '#c28412{Enter}');
    expect(onChange).toHaveBeenLastCalledWith('#c28412');
  });

  it('refuses a colour the schema would reject rather than normalising it', async () => {
    const onChange = vi.fn();
    render(<ColourField label="Colour" value="#1e40af" onChange={onChange} fallback="#101114" />);
    const user = userEvent.setup();
    const hex = screen.getByLabelText('Colour');
    await user.clear(hex);
    await user.type(hex, 'rgb(0 0 0){Enter}');
    expect(onChange).not.toHaveBeenCalled();
    expect(hex).toHaveAttribute('aria-invalid', 'true');
  });

  it('reverts to the element’s colour when focus leaves an invalid value', async () => {
    const onChange = vi.fn();
    render(<ColourField label="Colour" value="#1e40af" onChange={onChange} fallback="#101114" />);
    const user = userEvent.setup();
    const hex = screen.getByLabelText('Colour');
    await user.clear(hex);
    await user.type(hex, 'not-a-colour');
    await user.tab();
    expect(hex).toHaveValue('#1e40af');
    expect(onChange).not.toHaveBeenCalled();
  });

  it('accepts the three-digit form the schema also allows', async () => {
    const onChange = vi.fn();
    render(<ColourField label="Colour" value={null} onChange={onChange} fallback="#101114" />);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText('Colour'), '#abc{Enter}');
    expect(onChange).toHaveBeenLastCalledWith('#abc');
  });

  it('offers the document colours the caller passes, and marks the current one', async () => {
    const onChange = vi.fn();
    render(
      <ColourField
        label="Colour"
        value="#101114"
        onChange={onChange}
        swatches={['#101114', '#1e40af']}
        fallback="#101114"
      />,
    );
    const presets = screen.getByRole('group', { name: 'Colour presets' });
    expect(within(presets).getByLabelText('#101114')).toHaveAttribute('aria-pressed', 'true');
    await userEvent.setup().click(within(presets).getByLabelText('#1e40af'));
    expect(onChange).toHaveBeenCalledWith('#1e40af');
  });

  it('shows the caller’s default ink in the picker when the value is unset', () => {
    // The fallback is document data, not a design-system colour: the component must not
    // know what "unset" looks like on paper.
    render(<ColourField label="Colour" value={null} onChange={vi.fn()} fallback="#101114" />);
    expect(screen.getByLabelText('Colour picker')).toHaveValue('#101114');
  });
});

describe('Toggle', () => {
  it('is a switch that reports the flipped value', async () => {
    const onChange = vi.fn();
    render(<Toggle label="Snap to grid" checked={false} onChange={onChange} />);
    const toggle = screen.getByRole('switch', { name: 'Snap to grid' });
    expect(toggle).toHaveAttribute('aria-checked', 'false');
    await userEvent.setup().click(toggle);
    expect(onChange).toHaveBeenCalledWith(true);
  });

  it('works from the keyboard, as a button does', async () => {
    const onChange = vi.fn();
    render(<Toggle label="Snap" checked onChange={onChange} />);
    screen.getByRole('switch').focus();
    await userEvent.setup().keyboard(' ');
    expect(onChange).toHaveBeenCalledWith(false);
  });
});

describe('EditorSelect and EditorTextField', () => {
  it('selects from more options than a segmented control could hold', async () => {
    const onChange = vi.fn();
    render(
      <EditorSelect
        label="Paper"
        value="A4"
        options={[
          { value: 'A4', label: 'A4' },
          { value: 'LETTER', label: 'Letter' },
        ]}
        onChange={onChange}
      />,
    );
    await userEvent.setup().selectOptions(screen.getByLabelText('Paper'), 'LETTER');
    expect(onChange).toHaveBeenCalledWith('LETTER');
  });

  it('reports text as it is typed, because the page changes under your hands', async () => {
    const onChange = vi.fn();
    render(<EditorTextField label="Text" value="" onChange={onChange} />);
    await userEvent.setup().type(screen.getByLabelText('Text'), 'TAX');
    expect(onChange).toHaveBeenCalledTimes(3);
    expect(onChange).toHaveBeenLastCalledWith('X');
  });

  it('gives a paragraph a textarea rather than a one-line input', () => {
    render(<EditorTextField label="Declaration" value="We declare" onChange={vi.fn()} multiline />);
    expect(screen.getByLabelText('Declaration').tagName).toBe('TEXTAREA');
  });
});
