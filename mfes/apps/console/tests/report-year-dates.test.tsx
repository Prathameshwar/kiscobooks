import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it } from 'vitest';
import { ReportYearRange, useReportYearDates } from '../app/components/ReportYearRange';
import type { FiscalYearChoice } from '../app/lib/company-context';

const previous: FiscalYearChoice = { id: 'old', code: 'FY2026-2027', startDate: '2026-04-01', endDate: '2027-03-31', current: false, open: true };
const year: FiscalYearChoice = { id: 'new', code: 'FY2027-2028', startDate: '2027-04-01', endDate: '2028-03-31', current: true, open: true };
function Harness({ company = 'company', current = year }: { company?: string; current?: FiscalYearChoice }) {
  const range = useReportYearDates(company, current, [previous, year]);
  return <><ReportYearRange range={range} /><input aria-label="From date" type="date" value={range.from} onChange={event => range.custom('from', event.target.value)} /><input aria-label="To date" type="date" value={range.to} onChange={event => range.custom('to', event.target.value)} /></>;
}
beforeEach(() => sessionStorage.clear());
it('defaults to the selected year and switches to the previous year explicitly', () => {
  render(<Harness />); expect(screen.getByLabelText('From date')).toHaveValue('2027-04-01');
  expect(screen.getByLabelText('To date')).toHaveValue('2028-03-31');
  fireEvent.change(screen.getByLabelText('Report period'), { target: { value: 'previous' } });
  expect(screen.getByLabelText('From date')).toHaveValue('2026-04-01');
  expect(screen.getByText(/FY2026-2027/)).toBeVisible();
});
it('preserves deliberately entered dates when the year changes and after remounting', async () => {
  const view = render(<Harness />);
  fireEvent.change(screen.getByLabelText('From date'), { target: { value: '2026-10-01' } });
  fireEvent.change(screen.getByLabelText('To date'), { target: { value: '2026-10-31' } });
  view.rerender(<Harness current={previous} />);
  expect(screen.getByLabelText('Report period')).toHaveValue('custom');
  expect(screen.getByLabelText('From date')).toHaveValue('2026-10-01');
  view.unmount(); render(<Harness current={previous} />);
  await waitFor(() => expect(screen.getByLabelText('To date')).toHaveValue('2026-10-31'));
});
it('keeps saved custom dates scoped to their company', () => {
  const view = render(<Harness />);
  fireEvent.change(screen.getByLabelText('From date'), { target: { value: '2026-10-01' } });
  view.unmount(); render(<Harness company="another-company" />);
  expect(screen.getByLabelText('From date')).toHaveValue('2027-04-01');
});
it('ignores malformed stored dates', () => {
  sessionStorage.setItem('janso:report-dates:company', '{"mode":"custom","from":"invalid","to":"2026-01-01"}');
  render(<Harness />); expect(screen.getByLabelText('From date')).toHaveValue('2027-04-01');
});
