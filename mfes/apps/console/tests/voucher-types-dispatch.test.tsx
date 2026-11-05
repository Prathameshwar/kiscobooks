/**
 * `/masters/voucher-types` is the address the Purchase invoice and voucher entry screens (and the Voucher
 * print pages) already send people to — and it used to be a 404, because the masters page knew no such
 * resource. The glue is one line in `CatalogMasterPage`, and it is the line that decides whether
 * every one of those links works, so it is tested on its own: the resource reaches the voucher type
 * route with the rest of the path and the query, and no other resource does.
 */
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('../app/components/VoucherTypesRoute', () => ({
  VoucherTypesRoute: async (props: { record: string[]; query: Record<string, unknown> }) => <p>Voucher types route {JSON.stringify(props)}</p>,
}));
vi.mock('next/navigation', () => ({
  notFound: () => {
    throw new Error('NEXT_NOT_FOUND');
  },
}));

import Page from '../app/masters/[resource]/[[...record]]/page';
import { companyMasterPath, companyMasterGroups } from '../app/lib/company-masters';

describe('the masters page', () => {
  it.each([
    [undefined, {}],
    [['new'], { from: 'abc' }],
    [['01990000-0000-7000-8000-0000000000a1', 'edit'], { returnTo: '/masters' }],
  ])('hands /masters/voucher-types/%j to the voucher type route, with its query', async (record, query) => {
    render(await Page({ params: Promise.resolve({ resource: 'voucher-types', record }), searchParams: Promise.resolve(query) }));

    const shown = JSON.parse(screen.getByText(/^Voucher types route /).textContent!.replace('Voucher types route ', ''));
    expect(shown).toEqual({ record: record ?? [], query });
  });

  it('does not hand any other resource to it', async () => {
    await expect(Page({ params: Promise.resolve({ resource: 'voucher-typos', record: [] }), searchParams: Promise.resolve({}) })).rejects.toThrow('NEXT_NOT_FOUND');
  });
});

describe('the masters hub', () => {
  it('has a card for voucher types, gated on reading vouchers, in a group of its own', () => {
    const group = companyMasterGroups.find((entry) => entry.items.some((item) => item.href === '/masters/voucher-types'))!;

    expect(group.label).toBe('Vouchers');
    expect(group.items).toEqual([expect.objectContaining({ label: 'Voucher types', permission: 'vouchers.read' })]);
  });

  it('treats every voucher type page as part of Masters, so the rail keeps it open', () => {
    for (const path of ['/masters/voucher-types', '/masters/voucher-types/new', '/masters/voucher-types/abc/edit']) {
      expect(companyMasterPath(path), path).toBe(true);
    }
  });
});
