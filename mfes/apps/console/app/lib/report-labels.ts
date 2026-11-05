export function reportRowLabel(value: string): string {
  const labels: Record<string, string> = {
    PRIOR_UNTRANSFERRED_EARNINGS: 'Previous-year accumulated earnings',
    CURRENT_YEAR_EARNINGS: 'Current-year profit / loss',
    OPENING_EARNINGS: 'Original opening earnings',
    BALANCE_SHEET_CONTROL: 'Balance sheet totals',
    CONTINUITY_CONTROL: 'Continuity verification',
    ACCOUNT_CONTINUITY: 'Account balance',
    BILL_CONTINUITY: 'Outstanding bill',
    ADVANCE_CONTINUITY: 'Unapplied credit / advance',
    EARNINGS_CONTINUITY: 'Accumulated earnings',
  };
  return labels[value] ?? value.replaceAll('_', ' ').toLowerCase();
}
