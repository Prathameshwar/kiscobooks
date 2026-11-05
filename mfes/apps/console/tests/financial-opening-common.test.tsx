import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it } from 'vitest';
import { DEFAULT_DISPLAY_CONFIG, DisplayConfigProvider } from '@janso/ui';
import { FinancialOpeningDocumentEvidence, FinancialOpeningFieldErrors, FinancialOpeningMoney } from '../app/components/FinancialOpeningCommon';
it('formats exact historical amounts using the resolved display configuration', () => {
  render(<DisplayConfigProvider config={{ ...DEFAULT_DISPLAY_CONFIG, decimalSeparator: ',', groupSeparator: '.', digitGrouping: 'western', amountPrecision: 4 }}><FinancialOpeningMoney value="999999999999999.0001" currency="EUR" /></DisplayConfigProvider>);
  expect(screen.getByText('999.999.999.999.999,0001 EUR')).toBeVisible();
});
it.each(['dd/MM/yyyy', 'dd.MM.yyyy'])('formats retained document dates using %s without shifting business dates', (dateFormat) => {
  render(<DisplayConfigProvider config={{ ...DEFAULT_DISPLAY_CONFIG, dateFormat, locale: 'de-DE', timezone: 'America/Los_Angeles' }}><FinancialOpeningDocumentEvidence documents={[{ reference: 'Imported bill', document_kind: 'BILL', document_date: '2026-03-25', due_date: '2026-04-05', amount: '100' }]} currency="INR" /></DisplayConfigProvider>);
  const separator = dateFormat.includes('/') ? '/' : '.';
  expect(screen.getByText(`25${separator}03${separator}2026 / 05${separator}04${separator}2026`)).toBeVisible();
});
it('paginates retained bill evidence and keeps unknown dates explicit', async () => {
  const documents = Array.from({ length: 26 }, (_, i) => ({ reference: 'Bill ' + i, document_kind: 'ON_ACCOUNT' as const, document_date: null, due_date: null, amount: '100', base_amount: '100' }));
  render(<FinancialOpeningDocumentEvidence documents={documents} currency="INR" />);
  expect(screen.getAllByText('Unknown / Unknown')).toHaveLength(25);
  expect(screen.queryByText('Bill 25')).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Next documents' }));
  expect(screen.getByText('Bill 25')).toBeVisible();
  await userEvent.click(screen.getByRole('button', { name: 'Previous documents' }));
  expect(screen.getByText('Bill 0')).toBeVisible();
});
it('makes backend field validation actionable without exposing a raw response', () => {
  const { rerender } = render(<FinancialOpeningFieldErrors failure={null} />);
  expect(screen.queryByRole('list')).not.toBeInTheDocument();
  rerender(<FinancialOpeningFieldErrors failure={{ status: 422, message: 'Invalid opening', fields: { 'entries.2.base_amount': 'Enter the historical carrying value.' } }} />);
  expect(screen.getByText('Opening line 3.base amount:')).toBeVisible();
  expect(screen.getByText('Enter the historical carrying value.')).toBeVisible();
});
