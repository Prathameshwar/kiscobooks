import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it, vi } from 'vitest';
import { Modal, Drawer } from '../src/components/Overlay';
import { SearchSelect } from '../src/components/SearchSelect';

it.each([Modal, Drawer])('makes read-only overlay content a named keyboard-scrollable region', async Surface => {
  render(<Surface open title="Tax evidence" onClose={vi.fn()} footer={<button>Done</button>}><p>Read-only supplied calculation.</p></Surface>);
  const dialog = screen.getByRole('dialog', { name: 'Tax evidence' });
  const content = within(dialog).getByRole('region', { name: 'Tax evidence' });
  expect(content).toHaveAttribute('tabindex', '0');
  await userEvent.tab(); expect(content).toHaveFocus();
});
it('keeps empty portalled lookup status inside a named landmark', async () => {
  render(<SearchSelect label="Supplier" value={null} options={[]} onChange={vi.fn()} />);
  await userEvent.click(screen.getByRole('combobox', { name: 'Supplier' }));
  const region = screen.getByRole('region', { name: 'Supplier search' });
  expect(within(region).getByText('No matches')).toBeVisible();
  expect(within(region).getByRole('listbox', { name: 'Supplier results' })).toBeVisible();
});

it('reveals the entire focused field when native focus scrolling leaves it under the footer', () => {
  const frames: FrameRequestCallback[] = [];
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => { frames.push(callback); return frames.length; });
  try {
    render(<Drawer open title="Purchase details" onClose={vi.fn()} footer={<button>Apply</button>}><input aria-label="Description" /></Drawer>);
    const region = screen.getByRole('region', { name: 'Purchase details' });
    const field = screen.getByRole('textbox', { name: 'Description' });
    vi.spyOn(region, 'getBoundingClientRect').mockReturnValue({ top: 100, bottom: 400 } as DOMRect);
    vi.spyOn(field, 'getBoundingClientRect').mockReturnValue({ top: 380, bottom: 416 } as DOMRect);
    const scroll = vi.fn(); field.scrollIntoView = scroll;
    field.focus(); frames.splice(0).forEach(callback => callback(0));
    expect(scroll).toHaveBeenCalledWith({ block: 'nearest', inline: 'nearest' });
    scroll.mockClear();
    vi.mocked(field.getBoundingClientRect).mockReturnValue({ top: 200, bottom: 236 } as DOMRect);
    field.blur(); field.focus(); frames.splice(0).forEach(callback => callback(0));
    expect(scroll).not.toHaveBeenCalled();
  } finally { vi.unstubAllGlobals(); }
});
