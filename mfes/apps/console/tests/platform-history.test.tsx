import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { PlatformHistory } from '../app/components/PlatformHistory';
import Page from '../app/platform/history/page';
const { context, audit } = vi.hoisted(() => ({ context: vi.fn(), audit: vi.fn() }));
vi.mock('../app/lib/page-context', () => ({ pageContext: context }));
vi.mock('../app/components/AuditEvents', () => ({ AuditEvents: (props: object) => { audit(props); return <p>Stored platform events</p>; } }));
vi.mock('../app/providers', () => ({ Providers: ({children}: {children: React.ReactNode}) => children }));
vi.mock('../app/components/ConsoleShell', () => ({ ConsoleShell: ({children}: {children: React.ReactNode}) => children }));
beforeEach(() => { audit.mockClear(); context.mockResolvedValue({session:{permissions:['platform.account.read']},context:{}}); });
it('loads subject history on demand and allows it to be closed', () => {
  render(<PlatformHistory entityType="account_review" entityId="account" revision={1} />);
  expect(audit).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', {name:'Show history'}));
  expect(audit).toHaveBeenLastCalledWith(expect.objectContaining({platform:true,entityType:'account_review',entityId:'account'}));
  expect(screen.getByRole('button', {name:'Hide history'})).toHaveAttribute('aria-expanded','true');
  fireEvent.click(screen.getByRole('button', {name:'Hide history'}));
  expect(screen.queryByText('Stored platform events')).not.toBeInTheDocument();
});
it('allows history without general audit permissions and passes the subject filters', async () => {
  render(await Page({searchParams:Promise.resolve({entity_type:'account_review',entity_id:'account'})}));
  expect(audit).toHaveBeenCalledWith(expect.objectContaining({platform:true,entityType:'account_review',entityId:'account'}));
});
it('denies a tenant auditor without platform permissions', async () => {
  context.mockResolvedValue({session:{permissions:['audit.read','audit.read_security']},context:{}});
  render(await Page({searchParams:Promise.resolve({})}));
  expect(screen.getByRole('alert')).toHaveTextContent('Platform history permission');
  expect(audit).not.toHaveBeenCalled();
});
