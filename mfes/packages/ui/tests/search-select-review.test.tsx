import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ConfirmDialog } from '../src/components/ConfirmDialog';
import { CustomFields } from '../src/components/CustomFields';
import type { CustomField } from '../src/lib/custom-fields';
import { SearchSelect, type SearchSelectLoader, type SearchSelectOption, type SearchSelectProps } from '../src/components/SearchSelect';

const options: SearchSelectOption[] = [{ id: 'a', label: 'Alpha' }, { id: 'b', label: 'Beta', disabled: true }];
type Props = Omit<Extract<SearchSelectProps, { multiple?: false }>, 'value' | 'onChange'>;
function Single({ initial = null, spy, ...props }: Props & { initial?: string | null; spy?: (value: string | null, option: SearchSelectOption | null) => void }) {
  const [value, setValue] = useState(initial);
  return <SearchSelect {...props} value={value} onChange={(next, option) => { setValue(next); spy?.(next, option); }} />;
}
const input = () => screen.getByRole('combobox') as HTMLInputElement;
const tick = () => act(async () => { await vi.advanceTimersByTimeAsync(300); });
afterEach(() => vi.useRealTimers());

describe('SearchSelect interaction review', () => {
  it('shows an unresolved selected ID instead of a blank field that still submits it', () => {
    render(<Single label="Customer" initial="unresolved" name="customer_id" options={options} />);
    expect(input()).toHaveValue('unresolved'); expect(document.querySelector('input[type=hidden]')).toHaveValue('unresolved');
  });
  it('removes unresolved multiple selections without inventing resolved options', async () => {
    const spy = vi.fn();
    function Multi() { const [value, setValue] = useState(['unresolved']); return <SearchSelect label="Customers" multiple options={options} value={value} onChange={(ids, rows) => { setValue(ids); spy(ids, rows); }} />; }
    render(<Multi />); await userEvent.click(screen.getByRole('button', { name: 'Remove unresolved' })); expect(spy).toHaveBeenCalledWith([], []);
  });
  it('allows removal of a selected option that has since become inactive', async () => {
    const spy = vi.fn();
    function Multi() { const [value, setValue] = useState(['b']); return <SearchSelect label="Customers" multiple options={options} value={value} onChange={(ids, rows) => { setValue(ids); spy(ids, rows); }} />; }
    render(<Multi />); await userEvent.click(screen.getByRole('button', { name: 'Remove Beta' })); expect(spy).toHaveBeenCalledWith([], []);
  });
  it('lets Escape close the dropdown before dismissing its containing dialog', async () => {
    const cancel = vi.fn(); render(<ConfirmDialog open title="Choose a customer" onCancel={cancel} onConfirm={() => undefined}><Single label="Customer" options={options} /></ConfirmDialog>);
    await userEvent.click(input()); await userEvent.keyboard('{Escape}'); expect(screen.queryByRole('listbox')).not.toBeInTheDocument(); expect(cancel).not.toHaveBeenCalled();
    await userEvent.keyboard('{Escape}'); expect(cancel).toHaveBeenCalledTimes(1);
  });
  it('does not commit an option with Enter during IME composition', () => {
    const spy = vi.fn(); render(<Single label="Customer" options={options} spy={spy} />); fireEvent.focus(input()); fireEvent.keyDown(input(), { key: 'ArrowDown' });
    fireEvent.compositionStart(input()); fireEvent.keyDown(input(), { key: 'Enter', isComposing: true, keyCode: 229 }); expect(spy).not.toHaveBeenCalled();
  });
  it('leaves modified caret-navigation keys to the text input', () => {
    render(<Single label="Customer" options={options} />); fireEvent.focus(input()); fireEvent.keyDown(input(), { key: 'End' });
    const active = input().getAttribute('aria-activedescendant'); expect(fireEvent.keyDown(input(), { key: 'Home', ctrlKey: true })).toBe(true);
    expect(input()).toHaveAttribute('aria-activedescendant', active!);
  });
  it('closes when focus moves programmatically to another control', () => {
    render(<><Single label="Customer" options={options} /><button>Outside</button></>); fireEvent.focus(input());
    fireEvent.blur(input(), { relatedTarget: screen.getByRole('button', { name: 'Outside' }) }); expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });
  it('keeps a validation error visible when focus is restored, while still allowing click to open', async () => {
    render(<Single label="Customer" options={options} error="Choose a customer." />); fireEvent.focus(input()); expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    await userEvent.click(input()); expect(screen.getByRole('listbox')).toBeVisible();
  });
  it('provides a working pointer toggle without moving focus out of the input', async () => {
    render(<Single label="Customer" options={options} />); const toggle = screen.getByRole('button', { name: 'Toggle Customer options' });
    await userEvent.click(toggle); expect(screen.getByRole('listbox')).toBeVisible(); expect(input()).toHaveFocus();
    await userEvent.click(toggle); expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });
  it('validates a committed selection, rather than accepting arbitrary typed search text', async () => {
    render(<form><Single label="Customer" options={options} required /></form>); expect(input().checkValidity()).toBe(false);
    await userEvent.type(input(), 'Al'); expect(input().checkValidity()).toBe(false);
    await userEvent.click(screen.getByRole('option', { name: 'Alpha' })); expect(input().checkValidity()).toBe(true);
  });
});

describe('SearchSelect creation and context review', () => {
  const prepareCreate = () => {
    fireEvent.change(input(), { target: { value: 'New customer' } });
    fireEvent.keyDown(input(), { key: 'End' });
    fireEvent.keyDown(input(), { key: 'Enter' });
  };
  it('ignores a create response after its field unmounts', async () => {
    const spy = vi.fn(); let done!: (option: SearchSelectOption) => void;
    const { unmount } = render(<Single label="Customer" options={[]} canCreate onCreate={() => new Promise(resolve => { done = resolve; })} spy={spy} />);
    prepareCreate(); unmount(); await act(async () => done(options[0]!)); expect(spy).not.toHaveBeenCalled();
  });
  it('ignores a create response after the popup is dismissed', async () => {
    const spy = vi.fn(); let done!: (option: SearchSelectOption) => void;
    render(<Single label="Customer" options={[]} canCreate onCreate={() => new Promise(resolve => { done = resolve; })} spy={spy} />);
    prepareCreate(); fireEvent.pointerDown(document.body); await act(async () => done(options[0]!)); expect(spy).not.toHaveBeenCalled();
  });
  it('commits a created option against the latest controlled multiple selection', async () => {
    const spy = vi.fn(); let done!: (option: SearchSelectOption) => void;
    const create = () => new Promise<SearchSelectOption>(resolve => { done = resolve; });
    const { rerender } = render(<SearchSelect label="Customers" multiple value={[]} options={options} onChange={spy} canCreate onCreate={create} />);
    prepareCreate(); rerender(<SearchSelect label="Customers" multiple value={['a']} options={options} onChange={spy} canCreate onCreate={create} />);
    await act(async () => done({ id: 'c', label: 'New customer' })); expect(spy).toHaveBeenCalledWith(['a', 'c'], [options[0], { id: 'c', label: 'New customer' }]);
  });
  it('locks search text while a create is pending', async () => {
    let done!: (option: SearchSelectOption) => void;
    render(<Single label="Customer" options={[]} canCreate onCreate={() => new Promise(resolve => { done = resolve; })} />);
    fireEvent.keyPress(input(), { key: 'x', charCode: 120, which: 120 });
    prepareCreate(); expect(input()).toHaveAttribute('aria-readonly', 'true');
    expect(fireEvent.keyPress(input(), { key: 'x', charCode: 120, which: 120 })).toBe(false);
    fireEvent.change(input(), { target: { value: 'Other customer' } });
    expect(input()).toHaveValue('New customer'); await act(async () => done(options[0]!));
  });
  it('keeps an uncommitted required selection invalid while creation is pending', async () => {
    let done!: (option: SearchSelectOption) => void;
    render(<Single label="Customer" options={[]} required canCreate onCreate={() => new Promise(resolve => { done = resolve; })} />);
    prepareCreate(); expect(input().checkValidity()).toBe(false);
    await act(async () => done(options[0]!)); expect(input().checkValidity()).toBe(true);
  });
  it('resets cached labels and ignores old searches when the lookup scope changes', async () => {
    vi.useFakeTimers(); let done!: (page: { items: SearchSelectOption[]; nextCursor: null }) => void;
    const load = vi.fn<SearchSelectLoader>().mockResolvedValueOnce({ items: [options[0]!], nextCursor: null }).mockImplementation(() => new Promise(resolve => { done = resolve; }));
    const { rerender } = render(<SearchSelect {...{ scopeKey: 'company-a' }} label="Customer" value="a" onChange={vi.fn()} loadOptions={load} />);
    fireEvent.change(input(), { target: { value: 'aa' } }); await tick(); fireEvent.keyDown(input(), { key: 'Escape' }); expect(input()).toHaveValue('Alpha');
    fireEvent.click(input()); fireEvent.change(input(), { target: { value: 'aa' } }); await tick(); rerender(<SearchSelect {...{ scopeKey: 'company-b' }} label="Customer" value="a" onChange={vi.fn()} loadOptions={load} />);
    expect(input()).toHaveValue('a'); expect(load.mock.calls.at(-1)![0].signal.aborted).toBe(true);
    await act(async () => done({ items: [options[0]!], nextCursor: null })); expect(input()).toHaveValue('a');
  });
  it('does not offer creation until all remote search pages have been checked', async () => {
    vi.useFakeTimers(); const load = vi.fn<SearchSelectLoader>(async () => ({ items: [], nextCursor: 'page-2' }));
    render(<Single label="Customer" loadOptions={load} canCreate onCreate={vi.fn()} />); fireEvent.change(input(), { target: { value: 'New customer' } }); await tick();
    expect(screen.queryByRole('option', { name: 'Add “New customer”' })).not.toBeInTheDocument();
  });
  it('does not offer creation for an exact static match beyond the display cap', () => {
    render(<Single label="Customer" maxOptions={1} options={[{ id: 'a', label: 'Alpha One' }, { id: 'c', label: 'Alpha' }]} canCreate onCreate={vi.fn()} />);
    fireEvent.change(input(), { target: { value: 'Alpha' } }); expect(screen.queryByRole('option', { name: 'Add “Alpha”' })).not.toBeInTheDocument();
  });
  it('keeps the real selected label in a metadata-driven dynamic field', async () => {
    const field: CustomField = { key: 'cf_customer', label: 'Customer', source: 'custom', visible: true, writable: true, required: false,
      custom: { key: 'cf_customer', data_type: 'dynamic_select', is_active: true, is_immutable_after_create: false, option_source_key: 'customers', validation: { required: false, max_length: 200 }, choices: [] } };
    function Form() { const [values, setValues] = useState<Record<string, unknown>>({}); return <CustomFields fields={[field]} values={values} onChange={next => setValues(previous => ({ ...previous, ...next }))} loadOptions={() => async () => ({ items: [options[0]!], nextCursor: null })} />; }
    render(<Form />); await userEvent.type(input(), 'Al'); await userEvent.click(await screen.findByRole('option', { name: 'Alpha' })); expect(input()).toHaveValue('Alpha');
  });
});

describe('SearchSelect async review', () => {
  it('withholds old options immediately when a new query enters the debounce window', async () => {
    vi.useFakeTimers(); const spy = vi.fn(), load = vi.fn<SearchSelectLoader>(async () => ({ items: [options[0]!], nextCursor: null }));
    render(<Single label="Customer" loadOptions={load} spy={spy} />); fireEvent.change(input(), { target: { value: 'aa' } }); await tick();
    expect(screen.getByRole('option', { name: 'Alpha' })).toBeInTheDocument(); fireEvent.change(input(), { target: { value: 'bb' } });
    expect(screen.queryByRole('option', { name: 'Alpha' })).not.toBeInTheDocument(); fireEvent.keyDown(input(), { key: 'ArrowDown' }); fireEvent.keyDown(input(), { key: 'Enter' }); expect(spy).not.toHaveBeenCalled();
  });
  it.each(['bb', ''])('invalidates an in-flight query as soon as the input changes to %j', async next => {
    vi.useFakeTimers(); let resolve!: (page: { items: SearchSelectOption[]; nextCursor: null }) => void;
    const load = vi.fn<SearchSelectLoader>(() => new Promise(done => { resolve = done; })); render(<Single label="Customer" loadOptions={load} />);
    fireEvent.change(input(), { target: { value: 'aa' } }); await tick(); fireEvent.change(input(), { target: { value: next } });
    expect(load.mock.calls[0]![0].signal.aborted).toBe(true); await act(async () => resolve({ items: [options[0]!], nextCursor: null }));
    expect(screen.queryByRole('option', { name: 'Alpha' })).not.toBeInTheDocument();
  });
  it('makes a failed search retry reachable from the keyboard', async () => {
    vi.useFakeTimers(); const load = vi.fn<SearchSelectLoader>().mockRejectedValueOnce(new Error('Offline')).mockResolvedValue({ items: [options[0]!], nextCursor: null });
    render(<Single label="Customer" loadOptions={load} />); fireEvent.change(input(), { target: { value: 'aa' } }); await tick();
    fireEvent.keyDown(input(), { key: 'Enter' }); await tick(); expect(load).toHaveBeenCalledTimes(2); expect(screen.getByRole('option', { name: 'Alpha' })).toBeInTheDocument();
  });
  it('retries a failed next page without discarding the already loaded options', async () => {
    vi.useFakeTimers(); const load = vi.fn<SearchSelectLoader>().mockResolvedValueOnce({ items: [options[0]!], nextCursor: 'page-2' }).mockRejectedValueOnce(new Error('Offline')).mockResolvedValue({ items: [{ id: 'c', label: 'Gamma' }], nextCursor: null });
    render(<Single label="Customer" loadOptions={load} />); fireEvent.change(input(), { target: { value: 'aa' } }); await tick();
    fireEvent.click(screen.getByRole('button', { name: 'Load more' })); await tick(); fireEvent.click(screen.getByRole('button', { name: 'Try again' })); await tick();
    expect(load.mock.calls.at(-1)![0].cursor).toBe('page-2'); expect(screen.getByRole('option', { name: 'Alpha' })).toBeInTheDocument(); expect(screen.getByRole('option', { name: 'Gamma' })).toBeInTheDocument();
  });
  it('waits for composition to finish before searching its final text', async () => {
    vi.useFakeTimers(); const load = vi.fn<SearchSelectLoader>(async () => ({ items: [], nextCursor: null })); render(<Single label="Customer" loadOptions={load} />);
    fireEvent.focus(input()); fireEvent.compositionStart(input()); fireEvent.change(input(), { target: { value: '日本' } }); await tick(); expect(load).not.toHaveBeenCalled();
    fireEvent.compositionEnd(input(), { data: '日本' }); await tick(); expect(load).toHaveBeenCalledTimes(1); expect(load.mock.calls[0]![0].q).toBe('日本');
  });
});
