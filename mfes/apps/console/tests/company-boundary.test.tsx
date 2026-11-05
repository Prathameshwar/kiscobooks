import { useState } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { expect, it } from 'vitest';
import { Providers } from '../app/providers';
import { sessionFor, companyContextFor } from './helpers';
import { ConsoleShell } from '../app/components/ConsoleShell';
import { readFiscalYearCookie } from '../app/lib/company-cookies';
function Draft() { const [value, setValue] = useState(''); return <input aria-label="Draft" value={value} onChange={event => setValue(event.target.value)} />; }
it('discards company workspace state when the resolved company or authority changes', async () => {
  const session = await sessionFor(); session.company = { id: 'company-a', name: 'A' };
  const view = render(<Providers session={session}><Draft /></Providers>);
  fireEvent.change(screen.getByRole('textbox'), { target: { value: 'A draft' } });
  view.rerender(<Providers session={{ ...session, company: { id: 'company-b', name: 'B' } }}><Draft /></Providers>);
  expect(screen.getByRole('textbox')).toHaveValue('');
  fireEvent.change(screen.getByRole('textbox'), { target: { value: 'B draft' } });
  view.rerender(<Providers session={{ ...session, company: { id: 'company-b', name: 'B' }, permissions: [] }}><Draft /></Providers>);
  expect(screen.getByRole('textbox')).toHaveValue('');
});
it('rejects fiscal cookies with extra segments', () => {
  const id = '01990000-0000-7000-8000-000000000001';
  expect(readFiscalYearCookie(`${id}.${id}.extra`, id)).toBeNull();
});
it('discards workspace form state on financial-year changes within the same company', async () => {
  const session = await sessionFor(); session.company = { id: 'company-a', name: 'A' };
  const first = { id: 'year-a', code: 'A', startDate: '2026-01-01', endDate: '2026-12-31', current: true, open: true };
  const shell = (id: string) => <Providers session={session}><ConsoleShell session={session} activeHref="/settings" context={companyContextFor({ fiscalYear: { ...first, id } })}><Draft /></ConsoleShell></Providers>;
  const view = render(shell('year-a'));
  fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Old year draft' } });
  view.rerender(shell('year-b')); expect(screen.getByRole('textbox')).toHaveValue('');
});
