/**
 * The starting templates, as static fixtures for this phase.
 *
 * Four, because four is what it takes to prove the canvas is honest: a full GST tax
 * invoice on A4, a compact A4 for businesses that want one page and no ceremony, an 80mm
 * thermal receipt (a roll, not a sheet — different width, different type size, no logo),
 * and a delivery challan, which carries goods but no money. A designer that only renders
 * the first of those looks finished and falls over on the second.
 *
 * Geometry is millimetres throughout, laid out inside A4's 190 × 277mm printable area.
 */

import {
  type CanvasDefinition,
  type CanvasElement,
  type CanvasSection,
  type DesignTemplate,
  type ItemColumn,
  SCHEMA_VERSION,
} from './layout-model';

/* ---------------------------------------------------------------- builders */

function text(
  id: string,
  content: string,
  box: [number, number, number, number],
  style: CanvasElement['style'] = {},
): CanvasElement {
  const [xMm, yMm, widthMm, heightMm] = box;
  return { id, type: 'TEXT', xMm, yMm, widthMm, heightMm, content, style };
}

function field(
  id: string,
  bindingPath: CanvasElement['bindingPath'],
  box: [number, number, number, number],
  options: { label?: string; style?: CanvasElement['style'] } = {},
): CanvasElement {
  const [xMm, yMm, widthMm, heightMm] = box;
  return {
    id,
    type: 'FIELD_BINDING',
    xMm,
    yMm,
    widthMm,
    heightMm,
    bindingPath,
    label: options.label,
    style: options.style ?? {},
  };
}

function section(
  id: string,
  type: CanvasSection['type'],
  box: [number, number, number, number],
  elements: CanvasElement[],
  extra: Partial<CanvasSection> = {},
): CanvasSection {
  const [xMm, yMm, widthMm, heightMm] = box;
  return { id, type, xMm, yMm, widthMm, heightMm, elements, ...extra };
}

function columns(spec: [ItemColumn['key'], number, ItemColumn['align']?][]): ItemColumn[] {
  return spec.map(([key, widthMm, align]) => ({ key, widthMm, align, show: true }));
}

const A4_PAGE: CanvasDefinition['page'] = {
  size: 'A4',
  orientation: 'PORTRAIT',
  margins: { top: 10, right: 10, bottom: 10, left: 10, unit: 'mm' },
  gridSnap: true,
  gridStepMm: 5,
};

const INDIGO = '#1e40af';

/* ---------------------------------------------------------------- GST tax invoice */

const GST_A4: CanvasDefinition = {
  schemaVersion: SCHEMA_VERSION,
  page: A4_PAGE,
  theme: { primaryColor: INDIGO, fontFamily: 'Inter, sans-serif', fontSizePt: 9 },
  print: {
    copies: ['ORIGINAL_FOR_RECIPIENT', 'DUPLICATE_FOR_TRANSPORTER', 'TRIPLICATE_FOR_SUPPLIER'],
    copyMarkPosition: 'top-right',
  },
  sections: [
    section('sec-header', 'HEADER', [10, 10, 190, 28], [
      {
        id: 'el-logo',
        type: 'IMAGE',
        xMm: 0,
        yMm: 1,
        widthMm: 40,
        heightMm: 18,
        assetId: 'asset-logo',
        imageFit: 'contain',
      },
      text('el-company', 'Nandini Trading Company', [44, 0, 96, 7], {
        fontSizePt: 14,
        fontWeight: 'bold',
        color: INDIGO,
      }),
      field('el-company-address', 'company.address', [44, 7, 96, 12], {
        style: { fontSizePt: 7.5, color: '#4a4f59' },
      }),
      field('el-company-gstin', 'company.gstin', [44, 19, 96, 4], {
        label: 'GSTIN',
        style: { fontSizePt: 8, fontWeight: 'semibold' },
      }),
      text('el-title', 'TAX INVOICE', [146, 0, 44, 7], {
        fontSizePt: 13,
        fontWeight: 'bold',
        textAlign: 'right',
        uppercase: true,
      }),
      text('el-title-note', 'GST — rule 46', [146, 7, 44, 4], {
        fontSizePt: 7,
        textAlign: 'right',
        color: '#4a4f59',
      }),
      { id: 'el-header-rule', type: 'DIVIDER', xMm: 0, yMm: 25, widthMm: 190, heightMm: 1 },
    ]),

    section('sec-meta', 'CUSTOM', [10, 40, 190, 16], [
      field('el-no', 'voucher.document_number', [0, 0, 62, 5], { label: 'Invoice no.' }),
      field('el-date', 'voucher.document_date', [64, 0, 40, 5], { label: 'Dated' }),
      field('el-due', 'voucher.due_date', [106, 0, 40, 5], { label: 'Due' }),
      field('el-pos', 'voucher.place_of_supply', [148, 0, 42, 5], { label: 'Place of supply' }),
      field('el-vehicle', 'voucher.vehicle_number', [0, 7, 62, 5], { label: 'Vehicle' }),
      field('el-transport', 'voucher.transport_mode', [64, 7, 40, 5], { label: 'Transport' }),
      field('el-eway', 'voucher.eway_bill', [106, 7, 40, 5], { label: 'e-Way bill' }),
      field('el-rcm', 'voucher.reverse_charge', [148, 7, 42, 5], { label: 'Reverse charge' }),
    ], { title: 'Document details' }),

    section('sec-parties', 'BILLING_SHIPPING', [10, 58, 190, 30], [
      text('el-bill-label', 'Bill to', [0, 0, 92, 4], {
        fontSizePt: 7.5,
        uppercase: true,
        color: '#4a4f59',
      }),
      field('el-bill-name', 'party.name', [0, 4, 92, 5], {
        style: { fontWeight: 'semibold', fontSizePt: 9.5 },
      }),
      field('el-bill-address', 'address.billing', [0, 9, 92, 10], { style: { fontSizePt: 8 } }),
      field('el-bill-gstin', 'party.gstin', [0, 19, 92, 4], {
        label: 'GSTIN',
        style: { fontSizePt: 8 },
      }),
      text('el-ship-label', 'Ship to', [98, 0, 92, 4], {
        fontSizePt: 7.5,
        uppercase: true,
        color: '#4a4f59',
      }),
      field('el-ship-name', 'address.shipping_name', [98, 4, 92, 5], {
        style: { fontWeight: 'semibold', fontSizePt: 9.5 },
      }),
      field('el-ship-address', 'address.shipping', [98, 9, 92, 10], { style: { fontSizePt: 8 } }),
      field('el-ship-contact', 'party.contact', [98, 19, 92, 4], { style: { fontSizePt: 8 } }),
    ]),

    section('sec-items', 'ITEM_TABLE', [10, 90, 190, 106], [
      {
        id: 'el-items',
        type: 'ITEM_TABLE',
        xMm: 0,
        yMm: 0,
        widthMm: 190,
        heightMm: 106,
        // 190mm exactly: a column set that overflows its table is the one layout error a
        // designer cannot see on screen but the printer will.
        columns: columns([
          ['serial_no', 8, 'right'],
          ['description', 52],
          ['hsn_sac', 16],
          ['quantity', 14, 'right'],
          ['unit', 10],
          ['rate', 18, 'right'],
          ['taxable_value', 22, 'right'],
          ['cgst_amount', 14, 'right'],
          ['sgst_amount', 14, 'right'],
          ['amount', 22, 'right'],
        ]),
        rowOptions: { descriptionUnderItem: true, repeatHeader: true, blankRows: 2 },
      },
    ]),

    section('sec-tax', 'TAX_SUMMARY', [10, 198, 112, 32], [
      {
        id: 'el-tax',
        type: 'TAX_SUMMARY',
        xMm: 0,
        yMm: 0,
        widthMm: 112,
        heightMm: 32,
        taxGrouping: 'by_hsn',
        showCess: false,
      },
    ]),

    section('sec-totals', 'TOTALS', [126, 198, 74, 44], [
      {
        id: 'el-totals',
        type: 'TOTALS_BLOCK',
        xMm: 0,
        yMm: 0,
        widthMm: 74,
        heightMm: 44,
        totalsRows: [
          'taxable_value',
          'cgst',
          'sgst',
          'round_off',
          'grand_total',
          'amount_in_words',
        ],
      },
    ]),

    section('sec-footer', 'FOOTER', [10, 244, 190, 43], [
      text('el-bank-label', 'Bank details', [0, 0, 88, 4], {
        fontSizePt: 7.5,
        uppercase: true,
        color: '#4a4f59',
      }),
      field('el-bank-name', 'bank.name', [0, 4, 88, 4], { label: 'Bank' }),
      field('el-bank-ac', 'bank.account_number', [0, 8, 88, 4], { label: 'A/C' }),
      field('el-bank-ifsc', 'bank.ifsc', [0, 12, 88, 4], { label: 'IFSC' }),
      field('el-bank-upi', 'bank.upi', [0, 16, 88, 4], { label: 'UPI' }),
      field('el-declaration', 'signatory.declaration', [0, 24, 120, 10], {
        style: { fontSizePt: 7 },
      }),
      field('el-jurisdiction', 'signatory.jurisdiction', [0, 35, 120, 4], {
        style: { fontSizePt: 7, color: '#4a4f59' },
      }),
      {
        id: 'el-qr',
        type: 'QR_CODE',
        xMm: 96,
        yMm: 2,
        widthMm: 22,
        heightMm: 22,
        bindingPath: 'voucher.irn',
        symbology: 'QR',
        showValue: false,
      },
      {
        id: 'el-sign',
        type: 'SIGNATURE',
        xMm: 140,
        yMm: 14,
        widthMm: 50,
        heightMm: 24,
        assetId: 'asset-signature',
        content: 'For Nandini Trading Company',
        label: 'Authorised Signatory',
      },
    ]),
  ],
};

/* ---------------------------------------------------------------- compact A4 */

const COMPACT_A4: CanvasDefinition = {
  schemaVersion: SCHEMA_VERSION,
  page: A4_PAGE,
  theme: { primaryColor: '#15171c', fontFamily: 'Inter, sans-serif', fontSizePt: 9 },
  print: { copies: ['ORIGINAL_FOR_RECIPIENT'], copyMarkPosition: 'top-right' },
  sections: [
    section('sec-header', 'HEADER', [10, 10, 190, 20], [
      text('el-company', 'Nandini Trading Company', [0, 0, 120, 7], {
        fontSizePt: 13,
        fontWeight: 'bold',
      }),
      field('el-company-gstin', 'company.gstin', [0, 7, 120, 4], {
        label: 'GSTIN',
        style: { fontSizePt: 7.5, color: '#4a4f59' },
      }),
      text('el-title', 'INVOICE', [140, 0, 50, 7], {
        fontSizePt: 12,
        fontWeight: 'bold',
        textAlign: 'right',
      }),
      field('el-no', 'voucher.document_number', [140, 7, 50, 4], {
        style: { fontSizePt: 8, textAlign: 'right' },
      }),
      field('el-date', 'voucher.document_date', [140, 11, 50, 4], {
        style: { fontSizePt: 8, textAlign: 'right', color: '#4a4f59' },
      }),
      { id: 'el-rule', type: 'DIVIDER', xMm: 0, yMm: 17, widthMm: 190, heightMm: 1 },
    ]),
    section('sec-parties', 'BILLING_SHIPPING', [10, 34, 190, 18], [
      text('el-bill-label', 'Billed to', [0, 0, 120, 4], {
        fontSizePt: 7.5,
        uppercase: true,
        color: '#4a4f59',
      }),
      field('el-bill-name', 'party.name', [0, 4, 120, 5], { style: { fontWeight: 'semibold' } }),
      field('el-bill-address', 'address.billing', [0, 9, 120, 8], { style: { fontSizePt: 8 } }),
    ]),
    section('sec-items', 'ITEM_TABLE', [10, 56, 190, 150], [
      {
        id: 'el-items',
        type: 'ITEM_TABLE',
        xMm: 0,
        yMm: 0,
        widthMm: 190,
        heightMm: 150,
        columns: columns([
          ['serial_no', 10, 'right'],
          ['description', 92],
          ['quantity', 20, 'right'],
          ['rate', 28, 'right'],
          ['amount', 40, 'right'],
        ]),
        rowOptions: { zebra: true },
      },
    ]),
    section('sec-totals', 'TOTALS', [110, 212, 90, 36], [
      {
        id: 'el-totals',
        type: 'TOTALS_BLOCK',
        xMm: 0,
        yMm: 0,
        widthMm: 90,
        heightMm: 36,
        totalsRows: ['taxable_value', 'cgst', 'sgst', 'grand_total', 'amount_in_words'],
      },
    ]),
    section('sec-footer', 'FOOTER', [10, 256, 190, 30], [
      field('el-bank', 'bank.account_number', [0, 0, 110, 4], { label: 'A/C' }),
      field('el-ifsc', 'bank.ifsc', [0, 4, 110, 4], { label: 'IFSC' }),
      {
        id: 'el-sign',
        type: 'SIGNATURE',
        xMm: 140,
        yMm: 2,
        widthMm: 50,
        heightMm: 22,
        content: 'For Nandini Trading Company',
        label: 'Authorised Signatory',
      },
    ]),
  ],
};

/* ---------------------------------------------------------------- 80mm thermal */

const THERMAL_80: CanvasDefinition = {
  schemaVersion: SCHEMA_VERSION,
  page: {
    size: 'THERMAL_80MM',
    orientation: 'PORTRAIT',
    margins: { top: 4, right: 3, bottom: 6, left: 3, unit: 'mm' },
    gridSnap: true,
    gridStepMm: 2,
  },
  theme: { primaryColor: '#15171c', fontFamily: 'Inter, sans-serif', fontSizePt: 7.5 },
  print: { copies: ['ORIGINAL_FOR_RECIPIENT'] },
  sections: [
    section('sec-header', 'HEADER', [3, 4, 74, 24], [
      text('el-company', 'NANDINI TRADING CO.', [0, 0, 74, 5], {
        fontSizePt: 9,
        fontWeight: 'bold',
        textAlign: 'center',
      }),
      field('el-address', 'company.address', [0, 5, 74, 9], {
        style: { fontSizePt: 6.5, textAlign: 'center', color: '#4a4f59' },
      }),
      field('el-gstin', 'company.gstin', [0, 14, 74, 4], {
        label: 'GSTIN',
        style: { fontSizePt: 6.5, textAlign: 'center' },
      }),
      { id: 'el-rule', type: 'DIVIDER', xMm: 0, yMm: 20, widthMm: 74, heightMm: 1 },
    ]),
    section('sec-meta', 'CUSTOM', [3, 30, 74, 10], [
      field('el-no', 'voucher.document_number', [0, 0, 74, 4], { label: 'Bill' }),
      field('el-date', 'voucher.document_date', [0, 4, 74, 4], { label: 'Date' }),
    ]),
    section('sec-items', 'ITEM_TABLE', [3, 42, 74, 90], [
      {
        id: 'el-items',
        type: 'ITEM_TABLE',
        xMm: 0,
        yMm: 0,
        widthMm: 74,
        heightMm: 90,
        columns: columns([
          ['description', 34],
          ['quantity', 10, 'right'],
          ['rate', 14, 'right'],
          ['amount', 16, 'right'],
        ]),
      },
    ]),
    section('sec-totals', 'TOTALS', [3, 136, 74, 26], [
      {
        id: 'el-totals',
        type: 'TOTALS_BLOCK',
        xMm: 0,
        yMm: 0,
        widthMm: 74,
        heightMm: 26,
        totalsRows: ['taxable_value', 'cgst', 'sgst', 'grand_total'],
      },
    ]),
    section('sec-footer', 'FOOTER', [3, 166, 74, 28], [
      text('el-thanks', 'Thank you — visit again', [0, 0, 74, 4], {
        fontSizePt: 7,
        textAlign: 'center',
      }),
      {
        id: 'el-barcode',
        type: 'BARCODE',
        xMm: 12,
        yMm: 6,
        widthMm: 50,
        heightMm: 12,
        bindingPath: 'voucher.document_number',
        symbology: 'CODE128',
        showValue: true,
      },
    ]),
  ],
};

/* ---------------------------------------------------------------- delivery challan */

const CHALLAN_A4: CanvasDefinition = {
  schemaVersion: SCHEMA_VERSION,
  page: A4_PAGE,
  theme: { primaryColor: '#5b6c00', fontFamily: 'Inter, sans-serif', fontSizePt: 9 },
  print: {
    copies: ['ORIGINAL_FOR_RECIPIENT', 'DUPLICATE_FOR_TRANSPORTER'],
    copyMarkPosition: 'watermark',
  },
  sections: [
    section('sec-header', 'HEADER', [10, 10, 190, 24], [
      text('el-company', 'Nandini Trading Company', [0, 0, 120, 7], {
        fontSizePt: 13,
        fontWeight: 'bold',
      }),
      field('el-address', 'company.address', [0, 7, 120, 12], {
        style: { fontSizePt: 7.5, color: '#4a4f59' },
      }),
      text('el-title', 'DELIVERY CHALLAN', [120, 0, 70, 7], {
        fontSizePt: 12,
        fontWeight: 'bold',
        textAlign: 'right',
        uppercase: true,
      }),
      text('el-note', 'Not a tax invoice', [120, 7, 70, 4], {
        fontSizePt: 7,
        textAlign: 'right',
        color: '#4a4f59',
      }),
      { id: 'el-rule', type: 'DIVIDER', xMm: 0, yMm: 21, widthMm: 190, heightMm: 1 },
    ]),
    section('sec-meta', 'CUSTOM', [10, 38, 190, 12], [
      field('el-no', 'voucher.document_number', [0, 0, 60, 5], { label: 'Challan no.' }),
      field('el-date', 'voucher.document_date', [62, 0, 42, 5], { label: 'Dated' }),
      field('el-vehicle', 'voucher.vehicle_number', [106, 0, 42, 5], { label: 'Vehicle' }),
      field('el-transport', 'voucher.transport_mode', [150, 0, 40, 5], { label: 'Mode' }),
    ]),
    section('sec-parties', 'BILLING_SHIPPING', [10, 54, 190, 26], [
      text('el-ship-label', 'Deliver to', [0, 0, 92, 4], {
        fontSizePt: 7.5,
        uppercase: true,
        color: '#4a4f59',
      }),
      field('el-ship-name', 'address.shipping_name', [0, 4, 92, 5], {
        style: { fontWeight: 'semibold' },
      }),
      field('el-ship-address', 'address.shipping', [0, 9, 92, 10], { style: { fontSizePt: 8 } }),
      field('el-contact', 'party.contact', [98, 4, 92, 5], { style: { fontSizePt: 8 } }),
    ]),
    section('sec-items', 'ITEM_TABLE', [10, 84, 190, 150], [
      {
        id: 'el-items',
        type: 'ITEM_TABLE',
        xMm: 0,
        yMm: 0,
        widthMm: 190,
        heightMm: 150,
        columns: columns([
          ['serial_no', 10, 'right'],
          ['description', 88],
          ['hsn_sac', 22],
          ['batch', 20],
          ['quantity', 26, 'right'],
          ['unit', 24],
        ]),
        rowOptions: { descriptionUnderItem: true, blankRows: 4 },
      },
    ]),
    section('sec-footer', 'FOOTER', [10, 244, 190, 43], [
      text('el-received', 'Received the above goods in good order and condition', [0, 0, 110, 5], {
        fontSizePt: 8,
      }),
      {
        id: 'el-receiver-sign',
        type: 'SIGNATURE',
        xMm: 0,
        yMm: 16,
        widthMm: 70,
        heightMm: 22,
        content: 'Receiver’s signature',
        label: 'Name, date and seal',
      },
      {
        id: 'el-sign',
        type: 'SIGNATURE',
        xMm: 120,
        yMm: 16,
        widthMm: 70,
        heightMm: 22,
        content: 'For Nandini Trading Company',
        label: 'Authorised Signatory',
      },
    ]),
  ],
};

/* ---------------------------------------------------------------- assets */

/**
 * Inline SVG so nothing needs uploading: object storage is an open question
 * (`docs/invoice-design.md` §9.2) and a fixture that fetched a file would be pretending
 * the upload path exists.
 */
export const SAMPLE_ASSETS: Record<string, { name: string; dataUri: string }> = {
  'asset-logo': {
    name: 'Nandini wordmark',
    dataUri:
      'data:image/svg+xml;utf8,' +
      encodeURIComponent(
        `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 72">
           <rect x="2" y="12" width="48" height="48" rx="10" fill="#1e40af"/>
           <path d="M16 46V26l18 20V26" stroke="#ffffff" stroke-width="4" fill="none"
                 stroke-linecap="round" stroke-linejoin="round"/>
           <text x="60" y="38" font-family="Inter, sans-serif" font-size="20"
                 font-weight="700" fill="#1e40af">NANDINI</text>
           <text x="60" y="54" font-family="Inter, sans-serif" font-size="11"
                 fill="#4a4f59" letter-spacing="2">TRADING CO.</text>
         </svg>`,
      ),
  },
  'asset-signature': {
    name: 'Authorised signature',
    dataUri:
      'data:image/svg+xml;utf8,' +
      encodeURIComponent(
        `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 60">
           <path d="M8 44c14-26 22 6 34-10s16 18 28 2 18 10 30-6 20 12 34-6 24 8 30 0"
                 stroke="#101114" stroke-width="2.2" fill="none" stroke-linecap="round"/>
         </svg>`,
      ),
  },
};

/* ---------------------------------------------------------------- templates */

export const SAMPLE_TEMPLATES: DesignTemplate[] = [
  {
    id: 'tpl-gst-a4',
    code: 'gst-tax-invoice-a4',
    name: 'GST tax invoice — A4',
    description: 'Rule 46 invoice with HSN summary, three copies and bank details.',
    status: 'PUBLISHED',
    isSystem: false,
    liveVersionId: 'ver-gst-4',
    versions: [
      { id: 'ver-gst-4', versionNumber: 4, changeSummary: 'Added e-Way bill and IRN QR', createdAt: '2026-10-18T09:12:00Z', publishedAt: '2026-10-18T09:30:00Z' },
      { id: 'ver-gst-3', versionNumber: 3, changeSummary: 'Widened the description column', createdAt: '2026-09-30T11:04:00Z' },
      { id: 'ver-gst-2', versionNumber: 2, changeSummary: 'Moved totals beside the HSN summary', createdAt: '2026-09-02T15:48:00Z' },
      { id: 'ver-gst-1', versionNumber: 1, changeSummary: 'Initial template canvas', createdAt: '2026-08-21T08:00:00Z' },
    ],
    layout: GST_A4,
  },
  {
    id: 'tpl-compact-a4',
    code: 'compact-invoice-a4',
    name: 'Compact invoice — A4',
    description: 'One page, five columns, no statutory blocks.',
    status: 'DRAFT',
    isSystem: false,
    liveVersionId: null,
    versions: [
      { id: 'ver-compact-1', versionNumber: 1, changeSummary: 'Initial template canvas', createdAt: '2026-10-21T13:22:00Z' },
    ],
    layout: COMPACT_A4,
  },
  {
    id: 'tpl-thermal-80',
    code: 'retail-receipt-80mm',
    name: 'Retail receipt — 80mm',
    description: 'Roll stock for a counter printer: centred header, four columns.',
    status: 'PUBLISHED',
    isSystem: true,
    liveVersionId: 'ver-thermal-2',
    versions: [
      { id: 'ver-thermal-2', versionNumber: 2, changeSummary: 'Added the Code 128 bill barcode', createdAt: '2026-10-09T07:40:00Z', publishedAt: '2026-10-09T07:55:00Z' },
      { id: 'ver-thermal-1', versionNumber: 1, changeSummary: 'Initial template canvas', createdAt: '2026-09-15T06:10:00Z' },
    ],
    layout: THERMAL_80,
  },
  {
    id: 'tpl-challan-a4',
    code: 'delivery-challan-a4',
    name: 'Delivery challan — A4',
    description: 'Goods out with batch and vehicle, no tax columns, receiver signs.',
    status: 'PUBLISHED',
    isSystem: false,
    liveVersionId: 'ver-challan-1',
    versions: [
      { id: 'ver-challan-1', versionNumber: 1, changeSummary: 'Initial template canvas', createdAt: '2026-10-02T10:15:00Z', publishedAt: '2026-10-02T10:20:00Z' },
    ],
    layout: CHALLAN_A4,
  },
];

export function templateById(id: string): DesignTemplate | undefined {
  return SAMPLE_TEMPLATES.find((template) => template.id === id);
}
