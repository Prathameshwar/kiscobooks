import { fireEvent, screen, waitFor } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { AuditEvents } from '../app/components/AuditEvents';
import { renderWithProviders } from './helpers';

it('offers security history, preserves the subject when clearing filters and refreshes delivery', async () => {
  const load = vi.fn().mockResolvedValue({items:[],page:{has_more:false,next_cursor:null,limit:50}});
  await renderWithProviders(<AuditEvents platform entityType="account_review" entityId="account" load={load} />, {permissions:['platform.account.read']});
  await waitFor(()=>expect(screen.getByRole('button',{name:'Refresh history'})).toBeEnabled());
  expect(screen.queryByText('Security events excluded')).not.toBeInTheDocument();
  expect(screen.queryByRole('button',{name:/export/i})).not.toBeInTheDocument();
  fireEvent.change(screen.getByRole('combobox',{name:'Category'}), {target:{value:'security'}});
  await waitFor(()=>expect(load).toHaveBeenLastCalledWith(expect.objectContaining({category:'security',entity_type:'account_review'}),expect.any(AbortSignal)));
  fireEvent.change(screen.getByRole('combobox',{name:'Recorded'}), {target:{value:'24h'}});
  await waitFor(()=>expect(screen.getByRole('button',{name:'Refresh history'})).toBeEnabled());
  fireEvent.click(screen.getByRole('button',{name:'Clear all'}));
  await waitFor(()=>expect(load).toHaveBeenLastCalledWith(expect.objectContaining({category:undefined,entity_type:'account_review'}),expect.any(AbortSignal)));
  expect(screen.getByRole('combobox',{name:'Subject'})).toHaveValue('account_review');
  await waitFor(()=>expect(screen.getByRole('button',{name:'Refresh history'})).toBeEnabled());
  const calls = load.mock.calls.length;
  fireEvent.click(screen.getByRole('button',{name:'Refresh history'}));
  await waitFor(()=>expect(load.mock.calls.length).toBe(calls+1));
});
