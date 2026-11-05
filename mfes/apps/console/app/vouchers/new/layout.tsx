/**
 * The voucher entry routes.
 *
 * Adds the dense entry stylesheet to the root layout's list, loaded only here — the same reason
 * the designer group loads its canvas styles rather than the root doing it: forty-odd grid and
 * cell rules have no business in every form page's bundle.
 *
 * Unlike the designer, this is *not* a full-bleed group. A money document keeps the rail, the
 * company chip and the financial-year chip, because which company you are posting into is the
 * one thing this screen may never obscure.
 */
import '@janso/ui/styles/entry.css';

export default function VoucherEntryLayout({ children }: { children: React.ReactNode }) {
  return children;
}
