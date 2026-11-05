/**
 * The document the designer previews.
 *
 * Static by design for this phase (`docs/invoice-design-ui-todo.md`): the editor renders
 * against a fixture, and the real resolution comes later from the `design` service's
 * layout plus the voucher being printed.
 *
 * It is a deliberately *awkward* invoice rather than a tidy one — six lines, one with a
 * long description that wraps, batch and expiry on the pharma lines, a discount, a
 * round-off that is not zero, and a two-line shipping address that differs from billing.
 * A designer that only ever sees three short lines looks finished and breaks on the first
 * real document.
 *
 * Figures are strings, exactly as the money columns arrive from the API: the layout never
 * computes a total, it prints one. Parsing them into floats here would invite the editor
 * to start doing arithmetic on money.
 */

import type { BindingPath } from './layout-model';

export type DocumentLine = {
  serialNo: string;
  description: string;
  /** A second line under the description: specification, batch, make. */
  subDescription?: string;
  hsnSac: string;
  batch?: string;
  expiry?: string;
  quantity: string;
  unit: string;
  rate: string;
  mrp?: string;
  discount?: string;
  taxableValue: string;
  cgstRate: string;
  cgstAmount: string;
  sgstRate: string;
  sgstAmount: string;
  amount: string;
};

export type TaxSummaryRow = {
  hsnSac: string;
  taxableValue: string;
  cgstRate: string;
  cgstAmount: string;
  sgstRate: string;
  sgstAmount: string;
};

export type SampleDocument = {
  company: {
    name: string;
    addressLines: string[];
    gstin: string;
    pan: string;
    phone: string;
    email: string;
    stateName: string;
    stateCode: string;
  };
  voucher: {
    kind: string;
    title: string;
    documentNumber: string;
    documentDate: string;
    dueDate: string;
    placeOfSupply: string;
    reverseCharge: string;
    transportMode: string;
    vehicleNumber: string;
    eWayBill: string;
    irn: string;
  };
  party: {
    name: string;
    billingLines: string[];
    shippingName: string;
    shippingLines: string[];
    gstin: string;
    stateName: string;
    stateCode: string;
    contact: string;
  };
  lines: DocumentLine[];
  taxSummary: TaxSummaryRow[];
  totals: {
    subtotal: string;
    discount: string;
    taxableValue: string;
    cgst: string;
    sgst: string;
    igst: string;
    cess: string;
    roundOff: string;
    grandTotal: string;
    amountInWords: string;
    outstandingBalance: string;
  };
  bank: { name: string; accountNumber: string; ifsc: string; branch: string; upi: string };
  signatory: { forName: string; title: string; declaration: string; jurisdiction: string };
};

/** An expense or service line, as an accounts table shows it: the ledger it posts to. */
export type AccountLine = {
  serialNo: string;
  account: string;
  description: string;
  taxableValue: string;
  cgstRate: string;
  cgstAmount: string;
  sgstRate: string;
  sgstAmount: string;
  amount: string;
};

/** Sample expense lines for an accounts table: freight, a repair, a service fee. */
export const SAMPLE_ACCOUNT_LINES: AccountLine[] = [
  { serialNo: '1', account: 'Freight Inward', description: 'Transport, Nashik to Pune', taxableValue: '4,500.00', cgstRate: '6%', cgstAmount: '270.00', sgstRate: '6%', sgstAmount: '270.00', amount: '5,040.00' },
  { serialNo: '2', account: 'Repairs & Maintenance', description: 'Cold-room compressor service', taxableValue: '2,800.00', cgstRate: '9%', cgstAmount: '252.00', sgstRate: '9%', sgstAmount: '252.00', amount: '3,304.00' },
  { serialNo: '3', account: 'Professional Fees', description: 'GST return filing, October', taxableValue: '1,500.00', cgstRate: '9%', cgstAmount: '135.00', sgstRate: '9%', sgstAmount: '135.00', amount: '1,770.00' },
];

export const SAMPLE_DOCUMENT: SampleDocument = {
  company: {
    name: 'Nandini Trading Company',
    addressLines: [
      '14/2 Shivaji Nagar, Bund Garden Road',
      'Pune, Maharashtra 411001',
      'India',
    ],
    gstin: '27AABCN1234M1Z5',
    pan: 'AABCN1234M',
    phone: '+91 20 4567 8900',
    email: 'accounts@nandinitrading.in',
    stateName: 'Maharashtra',
    stateCode: '27',
  },
  voucher: {
    kind: 'SALES_INVOICE',
    title: 'Tax Invoice',
    documentNumber: 'NTC/25-26/001847',
    documentDate: '25 Oct 2026',
    dueDate: '24 Nov 2026',
    placeOfSupply: 'Maharashtra (27)',
    reverseCharge: 'No',
    transportMode: 'Road',
    vehicleNumber: 'MH 12 QR 8841',
    eWayBill: '3819 4471 2205',
    irn: 'a7f3c1d9e84b2f6075c3a1b8d4e9f2075c3a1b8d4e9f2075c3a1b8d4e9f2075c',
  },
  party: {
    name: 'Sahyadri Retail Private Limited',
    billingLines: [
      'Unit 4, Phoenix Market City',
      'Viman Nagar, Pune, Maharashtra 411014',
    ],
    shippingName: 'Sahyadri Retail — Kothrud Warehouse',
    shippingLines: [
      'Survey 112/3, Paud Road, Kothrud',
      'Pune, Maharashtra 411038',
    ],
    gstin: '27AAHCS9876K1ZT',
    stateName: 'Maharashtra',
    stateCode: '27',
    contact: 'Mr R. Deshpande · +91 98220 11447',
  },
  lines: [
    {
      serialNo: '1',
      description: 'Basmati rice, aged 12 months, 25 kg jute bag',
      subDescription: 'Lot NTC-RICE-0925 · packed 02 Sep 2026',
      hsnSac: '10063020',
      quantity: '40.000',
      unit: 'BAG',
      rate: '2,450.00',
      mrp: '2,900.00',
      taxableValue: '98,000.00',
      cgstRate: '2.5',
      cgstAmount: '2,450.00',
      sgstRate: '2.5',
      sgstAmount: '2,450.00',
      amount: '1,02,900.00',
    },
    {
      serialNo: '2',
      description: 'Refined sunflower oil, 15 litre tin',
      hsnSac: '15121110',
      quantity: '60.000',
      unit: 'TIN',
      rate: '1,780.00',
      discount: '2.00%',
      taxableValue: '1,04,664.00',
      cgstRate: '2.5',
      cgstAmount: '2,616.60',
      sgstRate: '2.5',
      sgstAmount: '2,616.60',
      amount: '1,09,897.20',
    },
    {
      serialNo: '3',
      description: 'Paracetamol IP 500 mg tablets, strip of 15',
      hsnSac: '30049099',
      batch: 'PCM2609A',
      expiry: '08/2028',
      quantity: '500.000',
      unit: 'STRIP',
      rate: '18.40',
      taxableValue: '9,200.00',
      cgstRate: '6',
      cgstAmount: '552.00',
      sgstRate: '6',
      sgstAmount: '552.00',
      amount: '10,304.00',
    },
    {
      serialNo: '4',
      description: 'Oral rehydration salts, orange, 21.8 g sachet',
      hsnSac: '30049099',
      batch: 'ORS2608F',
      expiry: '03/2029',
      quantity: '1,200.000',
      unit: 'SACHET',
      rate: '9.60',
      taxableValue: '11,520.00',
      cgstRate: '6',
      cgstAmount: '691.20',
      sgstRate: '6',
      sgstAmount: '691.20',
      amount: '12,902.40',
    },
    {
      serialNo: '5',
      description: 'Stainless steel storage container set, 5 pieces, induction base',
      subDescription: 'Make: Prestige · model PSC-5 · 18/8 grade',
      hsnSac: '73239990',
      quantity: '24.000',
      unit: 'SET',
      rate: '1,240.00',
      taxableValue: '29,760.00',
      cgstRate: '9',
      cgstAmount: '2,678.40',
      sgstRate: '9',
      sgstAmount: '2,678.40',
      amount: '35,116.80',
    },
    {
      serialNo: '6',
      description: 'Freight and handling — Pune to Kothrud',
      hsnSac: '996511',
      quantity: '1.000',
      unit: 'JOB',
      rate: '3,400.00',
      taxableValue: '3,400.00',
      cgstRate: '9',
      cgstAmount: '306.00',
      sgstRate: '9',
      sgstAmount: '306.00',
      amount: '4,012.00',
    },
  ],
  taxSummary: [
    {
      hsnSac: '10063020',
      taxableValue: '98,000.00',
      cgstRate: '2.5',
      cgstAmount: '2,450.00',
      sgstRate: '2.5',
      sgstAmount: '2,450.00',
    },
    {
      hsnSac: '15121110',
      taxableValue: '1,04,664.00',
      cgstRate: '2.5',
      cgstAmount: '2,616.60',
      sgstRate: '2.5',
      sgstAmount: '2,616.60',
    },
    {
      hsnSac: '30049099',
      taxableValue: '20,720.00',
      cgstRate: '6',
      cgstAmount: '1,243.20',
      sgstRate: '6',
      sgstAmount: '1,243.20',
    },
    {
      hsnSac: '73239990',
      taxableValue: '29,760.00',
      cgstRate: '9',
      cgstAmount: '2,678.40',
      sgstRate: '9',
      sgstAmount: '2,678.40',
    },
    {
      hsnSac: '996511',
      taxableValue: '3,400.00',
      cgstRate: '9',
      cgstAmount: '306.00',
      sgstRate: '9',
      sgstAmount: '306.00',
    },
  ],
  totals: {
    subtotal: '2,58,680.00',
    discount: '2,136.00',
    taxableValue: '2,56,544.00',
    cgst: '9,294.20',
    sgst: '9,294.20',
    igst: '0.00',
    cess: '0.00',
    roundOff: '-0.40',
    grandTotal: '2,75,132.00',
    amountInWords:
      'Indian Rupees Two Lakh Seventy-Five Thousand One Hundred Thirty-Two and Zero Paise Only',
    outstandingBalance: '4,18,760.00',
  },
  bank: {
    name: 'HDFC Bank',
    accountNumber: '50200071234567',
    ifsc: 'HDFC0000123',
    branch: 'Bund Garden Road, Pune',
    upi: 'nandinitrading@hdfcbank',
  },
  signatory: {
    forName: 'For Nandini Trading Company',
    title: 'Authorised Signatory',
    declaration:
      'We declare that this invoice shows the actual price of the goods described and that all particulars are true and correct.',
    jurisdiction: 'Subject to Pune jurisdiction',
  },
};

/**
 * Resolves a binding path against the sample document.
 *
 * Deliberately a lookup table rather than a dotted-path walk over the object: the paths
 * are a published contract (the service validates them against an allowlist), and a
 * generic walker would happily resolve a path the service would reject, so the editor
 * would preview something that cannot be saved. Returns `null` for an unknown path so the
 * renderer can show the placeholder instead of an empty box.
 */
const SAMPLE_VALUES: Record<string, string> = {
  'company.name': SAMPLE_DOCUMENT.company.name,
  'company.address': SAMPLE_DOCUMENT.company.addressLines.join('\n'),
  'company.gstin': SAMPLE_DOCUMENT.company.gstin,
  'company.pan': SAMPLE_DOCUMENT.company.pan,
  'company.phone': SAMPLE_DOCUMENT.company.phone,
  'company.email': SAMPLE_DOCUMENT.company.email,
  'company.state_name': SAMPLE_DOCUMENT.company.stateName,
  'company.state_code': SAMPLE_DOCUMENT.company.stateCode,
  'voucher.title': SAMPLE_DOCUMENT.voucher.title,
  'voucher.document_number': SAMPLE_DOCUMENT.voucher.documentNumber,
  'voucher.document_date': SAMPLE_DOCUMENT.voucher.documentDate,
  'voucher.due_date': SAMPLE_DOCUMENT.voucher.dueDate,
  // Facts a Purchase bill prints (2026-11-03): the supplier's bill number, when it was booked.
  'voucher.posting_date': SAMPLE_DOCUMENT.voucher.documentDate,
  'voucher.bill_reference': 'SUP/26-27/0418',
  'voucher.currency': 'INR',
  'voucher.status': 'Posted',
  'voucher.narration': 'Office supplies for October',
  'voucher.place_of_supply': SAMPLE_DOCUMENT.voucher.placeOfSupply,
  'voucher.reverse_charge': SAMPLE_DOCUMENT.voucher.reverseCharge,
  'voucher.transport_mode': SAMPLE_DOCUMENT.voucher.transportMode,
  'voucher.vehicle_number': SAMPLE_DOCUMENT.voucher.vehicleNumber,
  'voucher.eway_bill': SAMPLE_DOCUMENT.voucher.eWayBill,
  'voucher.irn': SAMPLE_DOCUMENT.voucher.irn,
  'party.name': SAMPLE_DOCUMENT.party.name,
  'party.gstin': SAMPLE_DOCUMENT.party.gstin,
  'party.state_name': SAMPLE_DOCUMENT.party.stateName,
  'party.state_code': SAMPLE_DOCUMENT.party.stateCode,
  'party.contact': SAMPLE_DOCUMENT.party.contact,
  'address.billing': SAMPLE_DOCUMENT.party.billingLines.join('\n'),
  'address.shipping': SAMPLE_DOCUMENT.party.shippingLines.join('\n'),
  'address.shipping_name': SAMPLE_DOCUMENT.party.shippingName,
  'totals.subtotal': SAMPLE_DOCUMENT.totals.subtotal,
  'totals.discount': SAMPLE_DOCUMENT.totals.discount,
  'totals.taxable_value': SAMPLE_DOCUMENT.totals.taxableValue,
  'totals.cgst': SAMPLE_DOCUMENT.totals.cgst,
  'totals.sgst': SAMPLE_DOCUMENT.totals.sgst,
  'totals.igst': SAMPLE_DOCUMENT.totals.igst,
  'totals.cess': SAMPLE_DOCUMENT.totals.cess,
  'totals.round_off': SAMPLE_DOCUMENT.totals.roundOff,
  'totals.tax_total': '18,588.40',
  'totals.grand_total': SAMPLE_DOCUMENT.totals.grandTotal,
  'totals.amount_in_words': SAMPLE_DOCUMENT.totals.amountInWords,
  'totals.outstanding_balance': SAMPLE_DOCUMENT.totals.outstandingBalance,
  'bank.name': SAMPLE_DOCUMENT.bank.name,
  'bank.account_number': SAMPLE_DOCUMENT.bank.accountNumber,
  'bank.ifsc': SAMPLE_DOCUMENT.bank.ifsc,
  'bank.branch': SAMPLE_DOCUMENT.bank.branch,
  'bank.upi': SAMPLE_DOCUMENT.bank.upi,
  'signatory.for_name': SAMPLE_DOCUMENT.signatory.forName,
  'signatory.title': SAMPLE_DOCUMENT.signatory.title,
  'signatory.declaration': SAMPLE_DOCUMENT.signatory.declaration,
  'signatory.jurisdiction': SAMPLE_DOCUMENT.signatory.jurisdiction,
  'custom.delivery_note': 'Goods received in good condition',
};

export function sampleValue(path: BindingPath | string): string | null {
  return SAMPLE_VALUES[path] ?? null;
}

/** Every path the fixture can resolve — the field palette's source in phase 6. */
export function sampleBindingPaths(): readonly string[] {
  return Object.keys(SAMPLE_VALUES);
}
