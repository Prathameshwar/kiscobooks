/**
 * Opening on focus, and not: a form field shows what it offers when it takes focus, while a grid
 * cell — reached by Tab and Enter dozens of times a minute — opens only when the reader types.
 */
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { SearchSelect } from '../src/components/SearchSelect';

const OPTIONS = [
  { id: 'a', label: 'Basmati rice' },
  { id: 'b', label: 'Sunflower oil' },
];

function SelectedField({ remote = false, openOnFocus = true, changed = vi.fn() }) {
  const [value, setValue] = useState<string | null>('a');
  return <>
    <button>Before</button>
    <SearchSelect label="Item" name="item_id" required value={value} selected={OPTIONS.find(option => option.id === value)}
      {...(remote ? { loadOptions: async () => ({ items: OPTIONS, nextCursor: null }), minQueryLength: 0 } : { options: OPTIONS })}
      openOnFocus={openOnFocus} onChange={(id, option) => { setValue(id); changed(id, option); }} />
    <button>After</button>
  </>;
}

describe('SearchSelect preserves a selected value', () => {
  it('keeps pointer entry from collapsing the selected label while allowing caret placement in a search', async () => {
    render(<SelectedField />);
    const box = screen.getByRole('combobox', { name: 'Item' });
    expect(fireEvent.pointerDown(box)).toBe(false);
    await userEvent.keyboard('Sun');
    expect(box).toHaveValue('Sun');
    expect(fireEvent.pointerDown(box)).toBe(true);
  });

  it.each([
    [false, 'click'], [false, 'tab'], [false, 'toggle'],
    [true, 'click'], [true, 'tab'], [true, 'toggle'],
  ] as const)('keeps the label and ID on %s remote / %s entry', async (remote, entry) => {
    const changed = vi.fn();
    const { container } = render(<SelectedField remote={remote} changed={changed} />);
    const box = screen.getByRole('combobox', { name: 'Item' });
    if (entry === 'click') await userEvent.click(box);
    else if (entry === 'toggle') await userEvent.click(screen.getByRole('button', { name: 'Toggle Item options' }));
    else { await userEvent.click(screen.getByRole('button', { name: 'Before' })); await userEvent.tab(); }
    expect(box).toHaveFocus();
    expect(box).toHaveValue('Basmati rice');
    expect(container.querySelector('input[type=hidden]')).toHaveValue('a');
    expect(changed).not.toHaveBeenCalled();
    await userEvent.tab();
    expect(box).toHaveValue('Basmati rice');
    await userEvent.tab({ shift: true });
    expect(box).toHaveValue('Basmati rice');
    expect(changed).not.toHaveBeenCalled();
  });

  it.each([true, false])('starts a replacement search only when typing (openOnFocus=%s)', async openOnFocus => {
    const changed = vi.fn();
    const { container } = render(<SelectedField openOnFocus={openOnFocus} changed={changed} />);
    await userEvent.click(screen.getByRole('button', { name: 'Before' }));
    await userEvent.tab();
    const box = screen.getByRole('combobox', { name: 'Item' });
    expect(box).toHaveValue('Basmati rice');
    await userEvent.keyboard('Sun');
    expect(box).toHaveValue('Sun');
    expect(container.querySelector('input[type=hidden]')).toHaveValue('a');
    expect(changed).not.toHaveBeenCalled();
    await userEvent.keyboard('{ArrowDown}{Enter}');
    expect(box).toHaveValue('Sunflower oil');
    expect(changed).toHaveBeenCalledWith('b', OPTIONS[1]);
    expect(container.querySelector('input[type=hidden]')).toHaveValue('b');
    await userEvent.click(box);
    expect(box).toHaveValue('Sunflower oil');
  });

  it.each(['tab', 'escape', 'outside'])('restores the selection after dismissing an unfinished search with %s', async dismissal => {
    const changed = vi.fn();
    render(<SelectedField changed={changed} />);
    const box = screen.getByRole('combobox', { name: 'Item' });
    await userEvent.type(box, 'Sun');
    if (dismissal === 'tab') await userEvent.tab();
    else if (dismissal === 'escape') await userEvent.keyboard('{Escape}');
    else await userEvent.click(screen.getByRole('button', { name: 'After' }));
    expect(box).toHaveValue('Basmati rice');
    await userEvent.click(box);
    expect(box).toHaveValue('Basmati rice');
    expect(screen.getAllByRole('option')).toHaveLength(2);
    expect(changed).not.toHaveBeenCalled();
    await userEvent.keyboard('Sun');
    expect(box).toHaveValue('Sun');
  });

  it('allows an empty search without clearing the committed ID, and clears it explicitly', async () => {
    const changed = vi.fn();
    const { container } = render(<SelectedField changed={changed} />);
    const box = screen.getByRole('combobox', { name: 'Item' });
    await userEvent.clear(box);
    expect(box).toHaveValue('');
    expect(container.querySelector('input[type=hidden]')).toHaveValue('a');
    expect(changed).not.toHaveBeenCalled();
    await userEvent.keyboard('{Escape}');
    expect(box).toHaveValue('Basmati rice');
    await userEvent.click(screen.getByRole('button', { name: 'Clear Item' }));
    expect(changed).toHaveBeenCalledWith(null, null);
    expect(box).toHaveValue('');
    expect(container.querySelector('input[type=hidden]')).toBeNull();
    expect(box).toBeInvalid();
  });
});

describe('SearchSelect openOnFocus', () => {
  it('opens on focus by default', () => {
    render(<SearchSelect label="Item" options={OPTIONS} value={null} onChange={vi.fn()} />);
    fireEvent.focus(screen.getByRole('combobox', { name: 'Item' }));
    expect(screen.getByRole('combobox', { name: 'Item' })).toHaveAttribute('aria-expanded', 'true');
  });

  it('stays closed on focus when told to, and opens once the reader types', async () => {
    const user = userEvent.setup();
    render(
      <SearchSelect label="Item" options={OPTIONS} value={null} onChange={vi.fn()} openOnFocus={false} />,
    );
    const box = screen.getByRole('combobox', { name: 'Item' });
    fireEvent.focus(box);
    expect(box).toHaveAttribute('aria-expanded', 'false');

    await user.type(box, 'ba');
    expect(box).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('option', { name: /Basmati rice/ })).toBeInTheDocument();
  });
});
