import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { assetSourceOf, useDesignAssetWrites, useDesignAssets } from '../app/lib/design-assets';
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
const asset = { id: '01990000-0000-7000-8000-000000000002', company_id: company, asset_name: 'Logo', asset_type: 'LOGO',
  file_name: 'logo.png', mime_type: 'image/png', file_size_bytes: 10, is_active: true, download_token: 'tok',
  created_at: '2026-11-01T00:00:00Z' };

beforeEach(() => { vi.clearAllMocks(); });

it('reads the company scoped asset list and refreshes the download tokens on an interval', async () => {
  vi.mocked(designRequest).mockResolvedValue({ items: [asset] });
  vi.useFakeTimers({ shouldAdvanceTime: true });
  try {
    const view = renderHook(() => useDesignAssets(company));
    await waitFor(() => expect(view.result.current.items).toHaveLength(1));
    expect(designRequest).toHaveBeenCalledWith(
      expect.objectContaining({ path: `/v1/companies/${company}/assets?limit=200&include_inactive=false` }),
    );
    expect(designRequest).toHaveBeenCalledTimes(1);
    await act(async () => { await vi.advanceTimersByTimeAsync(60_000); });
    expect(designRequest).toHaveBeenCalledTimes(2);
  } finally {
    vi.useRealTimers();
  }
});

it('makes no request and reports nothing loading without a company', () => {
  const view = renderHook(() => useDesignAssets(undefined));
  expect(view.result.current.items).toEqual([]);
  expect(view.result.current.loading).toBe(false);
  expect(designRequest).not.toHaveBeenCalled();
});

it('refuses a response naming a different company as the same breach as a mismatched detail', async () => {
  vi.mocked(designRequest).mockResolvedValue({ items: [{ ...asset, company_id: '01990000-0000-7000-8000-000000000099' }] });
  const view = renderHook(() => useDesignAssets(company));
  await waitFor(() => expect(view.result.current.failure).not.toBeNull());
  expect(view.result.current.items).toEqual([]);
});

it('keys only active assets carrying a live download token', () => {
  const inactive = { ...asset, id: 'a2', is_active: false };
  const tokenless = { ...asset, id: 'a3', download_token: null };
  expect(assetSourceOf([asset, inactive, tokenless])).toEqual({
    [asset.id]: { downloadToken: 'tok', mimeType: 'image/png' },
  });
});

function pngFile(name = 'logo.png', bytes: Uint8Array = new Uint8Array([1, 2, 3])) {
  return new File([new Uint8Array(bytes)], name, { type: 'image/png' });
}

it('uploads a file as base64 with no data: prefix, through the dedicated upload route', async () => {
  const created_id = '01990000-0000-7000-8000-000000000009';
  vi.mocked(serviceCall).mockResolvedValue({ id: created_id, company_id: company });
  const view = renderHook(() => useDesignAssetWrites(company));
  let created: unknown;
  await act(async () => {
    created = await view.result.current.upload({ file: pngFile(), assetName: 'Logo', assetType: 'LOGO' });
  });
  expect(created).toEqual({ id: created_id, company_id: company });
  expect(serviceCall).toHaveBeenCalledTimes(1);
  const [endpoint, request] = vi.mocked(serviceCall).mock.calls[0]!;
  expect(endpoint).toBe('/api/design-asset-upload');
  expect(request).toMatchObject({
    service: 'design',
    path: `/v1/companies/${company}/assets`,
    method: 'POST',
    body: { asset_name: 'Logo', asset_type: 'LOGO', file_name: 'logo.png', mime_type: 'image/png' },
  });
  const body = (request as { body: { content_base64: string } }).body;
  expect(body.content_base64).not.toMatch(/^data:/);
  expect(body.content_base64.length).toBeGreaterThan(0);
});

it('uploads nothing without a company, and never calls the service', async () => {
  const view = renderHook(() => useDesignAssetWrites(undefined));
  const result = await view.result.current.upload({ file: pngFile(), assetName: 'Logo', assetType: 'LOGO' });
  expect(result).toBeNull();
  expect(serviceCall).not.toHaveBeenCalled();
});

it('reports the service refusal as the upload failure, and clears it on demand', async () => {
  vi.mocked(serviceCall).mockRejectedValue({ status: 422, message: 'an image asset must be one of...' });
  const view = renderHook(() => useDesignAssetWrites(company));
  await act(async () => {
    expect(await view.result.current.upload({ file: pngFile(), assetName: 'Logo', assetType: 'LOGO' })).toBeNull();
  });
  expect(view.result.current.failure).toBe('an image asset must be one of...');
  act(() => view.result.current.clear());
  expect(view.result.current.failure).toBeNull();
});
