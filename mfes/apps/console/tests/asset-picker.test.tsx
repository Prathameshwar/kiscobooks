import { act, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { AssetPicker } from '../app/(editor)/invoice-designer/AssetPicker';
import { designRequest } from '../app/lib/design-api';
import { serviceCall } from '../app/lib/service-call';

vi.mock('../app/lib/design-api', async (original) => ({
  ...(await original<typeof import('../app/lib/design-api')>()),
  designRequest: vi.fn(),
}));
vi.mock('../app/lib/service-call', async (original) => ({
  ...(await original<typeof import('../app/lib/service-call')>()),
  serviceCall: vi.fn(),
}));

const company = '01990000-0000-7000-8000-000000000001';
const logo = { id: '01990000-0000-7000-8000-000000000002', company_id: company, asset_name: 'Company logo',
  asset_type: 'LOGO', file_name: 'logo.png', mime_type: 'image/png', file_size_bytes: 10, is_active: true,
  download_token: 'tok', created_at: '2026-11-01T00:00:00Z' };
const archived = { ...logo, id: '01990000-0000-7000-8000-000000000003', asset_name: 'Old logo', is_active: false };

beforeEach(() => vi.clearAllMocks());
afterEach(() => vi.useRealTimers());

function pngFile(name = 'new-logo.png') {
  return new File([new Uint8Array([1, 2, 3])], name, { type: 'image/png' });
}

it('lists active assets only, and never shows an archived one as choosable', async () => {
  vi.mocked(designRequest).mockResolvedValue({ items: [logo, archived] });
  const onChange = vi.fn();
  render(<AssetPicker company={company} elementType="IMAGE" value={undefined} onChange={onChange} />);
  await waitFor(() => expect(screen.getByText('Company logo')).toBeInTheDocument());
  expect(screen.queryByText('Old logo')).not.toBeInTheDocument();
});

it('selecting a saved asset reports its id, and choosing None clears it', async () => {
  vi.mocked(designRequest).mockResolvedValue({ items: [logo] });
  const onChange = vi.fn();
  render(<AssetPicker company={company} elementType="SIGNATURE" value={undefined} onChange={onChange} />);
  const select = await screen.findByLabelText('Choose a saved asset');
  await waitFor(() => expect(screen.getByText('Company logo')).toBeInTheDocument());
  act(() => { (select as HTMLSelectElement).value = logo.id; select.dispatchEvent(new Event('change', { bubbles: true })); });
  expect(onChange).toHaveBeenCalledWith(logo.id);
  onChange.mockClear();
  act(() => { (select as HTMLSelectElement).value = ''; select.dispatchEvent(new Event('change', { bubbles: true })); });
  expect(onChange).toHaveBeenCalledWith(undefined);
});

it('uploads a chosen file, selects the new asset and refreshes the saved list', async () => {
  vi.mocked(designRequest).mockResolvedValue({ items: [] });
  const created_id = '01990000-0000-7000-8000-000000000009';
  vi.mocked(serviceCall).mockResolvedValue({ id: created_id, company_id: company });
  const onChange = vi.fn();
  render(<AssetPicker company={company} elementType="IMAGE" value={undefined} onChange={onChange} />);
  const input = await screen.findByLabelText('Upload an image');
  await act(async () => {
    Object.defineProperty(input, 'files', { value: [pngFile()], configurable: true });
    input.dispatchEvent(new Event('change', { bubbles: true }));
  });
  await waitFor(() => expect(onChange).toHaveBeenCalledWith(created_id));
  expect(serviceCall).toHaveBeenCalledWith(
    '/api/design-asset-upload',
    expect.objectContaining({ path: `/v1/companies/${company}/assets`, method: 'POST' }),
    'design service',
  );
  // One read on mount, one more once the new asset is in — the picker's own list catches up.
  await waitFor(() => expect(designRequest).toHaveBeenCalledTimes(2));
});

it('shows a failed upload inline and lets the same file be retried', async () => {
  vi.mocked(designRequest).mockResolvedValue({ items: [] });
  vi.mocked(serviceCall).mockRejectedValueOnce({ status: 422, message: 'an image asset must be one of...' });
  const onChange = vi.fn();
  render(<AssetPicker company={company} elementType="IMAGE" value={undefined} onChange={onChange} />);
  const input = await screen.findByLabelText('Upload an image');
  await act(async () => {
    Object.defineProperty(input, 'files', { value: [pngFile()], configurable: true });
    input.dispatchEvent(new Event('change', { bubbles: true }));
  });
  await waitFor(() => expect(screen.getByText(/an image asset must be one of/)).toBeInTheDocument());
  expect(onChange).not.toHaveBeenCalled();

  const created_id = '01990000-0000-7000-8000-000000000011';
  vi.mocked(serviceCall).mockResolvedValueOnce({ id: created_id, company_id: company });
  await act(async () => { screen.getByRole('button', { name: /retry/i }).click(); });
  await waitFor(() => expect(onChange).toHaveBeenCalledWith(created_id));
});

it('disables both the saved-asset select and the uploader when read-only', async () => {
  vi.mocked(designRequest).mockResolvedValue({ items: [logo] });
  render(<AssetPicker company={company} elementType="IMAGE" value={logo.id} onChange={vi.fn()} disabled />);
  await waitFor(() => expect(screen.getByLabelText('Choose a saved asset')).toBeDisabled());
  expect(await screen.findByLabelText('Upload an image')).toBeDisabled();
});
