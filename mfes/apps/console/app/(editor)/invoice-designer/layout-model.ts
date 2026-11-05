/**
 * The invoice layout model, as the designer manipulates it.
 *
 * This mirrors the canvas schema the `design` service stores
 * (`docs/invoice-design.md` §4, §6.2) **plus the 1.1.0 additions that phase is waiting
 * on**: item-table columns, totals rows, tax grouping and print options. Keeping the
 * shapes identical is deliberate — when the service ships 1.1.0, wiring the editor to it
 * is a change of data source, not a rewrite, and anything the UI invents here would show
 * up immediately as a type error against the generated client.
 *
 * Two rules the schema enforces and this file keeps:
 *
 *   **Geometry is millimetres.** Positions, sizes and page setup are millimetres, because
 *   that is what prints and what CSS's own `mm` unit means. Display geometry inside the
 *   layout is `number`, not a decimal string: no total is ever computed from it.
 *
 *   **No open key/value bags, no markup, no CSS.** Styling is typed scalars; element
 *   options are named fields. A free-form map is how `src`, `style` and `onerror` reach a
 *   renderer.
 */

export const SCHEMA_VERSION = '1.1.0' as const;

/* ---------------------------------------------------------------- styling */

/** `#rgb` or `#rrggbb`. The schema refuses anything a stylesheet could reinterpret. */
export type Colour = string;

export type ElementStyle = {
  fontSizePt?: number;
  fontWeight?: 'normal' | 'medium' | 'semibold' | 'bold';
  fontStyle?: 'normal' | 'italic';
  color?: Colour;
  backgroundColor?: Colour;
  textAlign?: 'left' | 'center' | 'right' | 'justify';
  verticalAlign?: 'top' | 'middle' | 'bottom';
  borderWidthMm?: number;
  borderStyle?: 'none' | 'solid' | 'dashed' | 'dotted';
  borderColor?: Colour;
  paddingMm?: number;
  opacity?: number;
  lineHeight?: number;
  uppercase?: boolean;
};

/* ---------------------------------------------------------------- bindings */

/**
 * The roots an element may bind to. The service holds the same list and builds its
 * validation pattern from it; the renderer resolves the rest of the path against the
 * document being printed, under that reader's field policy.
 */
export const BINDING_ROOTS = [
  'voucher',
  'company',
  'party',
  'address',
  'line',
  'tax',
  'totals',
  'bank',
  'signatory',
  'custom',
] as const;

export type BindingRoot = (typeof BINDING_ROOTS)[number];
export type BindingPath = `${BindingRoot}.${string}`;

/* ---------------------------------------------------------------- elements */

export type ElementKind =
  | 'TEXT'
  | 'FIELD_BINDING'
  | 'IMAGE'
  | 'ITEM_TABLE'
  /** Accounts and expenses on a bill, beside or instead of the products (plan D2). */
  | 'ACCOUNT_TABLE'
  | 'TAX_SUMMARY'
  | 'TOTALS_BLOCK'
  | 'QR_CODE'
  | 'BARCODE'
  | 'SHAPE'
  | 'DIVIDER'
  | 'SIGNATURE';

/** The columns an item table may carry, in the vocabulary the service will validate. */
export const COLUMN_KEYS = [
  'serial_no',
  'description',
  'hsn_sac',
  'batch',
  'expiry',
  'quantity',
  'unit',
  'rate',
  'mrp',
  'discount',
  'taxable_value',
  'cgst_rate',
  'cgst_amount',
  'sgst_rate',
  'sgst_amount',
  'igst_rate',
  'igst_amount',
  'cess',
  'amount',
  /** The ledger a line posts to: an accounts table's first column. */
  'account',
] as const;

/** The two line tables: products, and accounts and expenses. */
export function isLineTable(type: string | undefined): boolean {
  return type === 'ITEM_TABLE' || type === 'ACCOUNT_TABLE';
}

export type ColumnKey = (typeof COLUMN_KEYS)[number];

export type ItemColumn = {
  key: ColumnKey;
  /** Overrides the default heading; the default comes from the column catalogue. */
  label?: string;
  widthMm: number;
  align?: 'left' | 'center' | 'right';
  show: boolean;
};

/** The rows a totals block may print, in the order the add menu offers them. */
export const TOTALS_ROWS = [
  'subtotal',
  'discount',
  'taxable_value',
  'cgst',
  'sgst',
  'igst',
  'cess',
  'round_off',
  'grand_total',
  'amount_in_words',
  'outstanding_balance',
] as const;

export type TotalsRow = (typeof TOTALS_ROWS)[number];

export type CanvasElement = {
  id: string;
  type: ElementKind;
  /** Millimetres from the page's top-left corner. */
  xMm: number;
  yMm: number;
  widthMm: number;
  heightMm: number;
  zIndex?: number;
  /** Static text. The renderer prints it as text, never as markup. */
  content?: string;
  bindingPath?: BindingPath;
  label?: string;
  /** Names an `invoice_template_asset`; the service checks it belongs to the company. */
  assetId?: string;
  style?: ElementStyle;
  /* — typed options, per element type — */
  symbology?: 'CODE128' | 'EAN13' | 'QR' | 'DATAMATRIX';
  showValue?: boolean;
  imageFit?: 'contain' | 'cover' | 'fill';
  columns?: ItemColumn[];
  rowOptions?: {
    descriptionUnderItem?: boolean;
    zebra?: boolean;
    repeatHeader?: boolean;
    /** Filler rows for pre-printed stationery, so the ruled box always looks full. */
    blankRows?: number;
  };
  totalsRows?: TotalsRow[];
  taxGrouping?: 'by_rate' | 'by_hsn' | 'none';
  showCess?: boolean;
};

export type SectionKind =
  | 'HEADER'
  | 'BILLING_SHIPPING'
  | 'ITEM_TABLE'
  | 'TAX_SUMMARY'
  | 'TOTALS'
  | 'FOOTER'
  | 'CUSTOM';

export type CanvasSection = {
  id: string;
  type: SectionKind;
  title?: string;
  /** Millimetre box of the zone itself — what the editor outlines and selects. */
  xMm: number;
  yMm: number;
  widthMm: number;
  heightMm: number;
  /** Names an `invoice_template_component` whose content this zone renders. */
  componentCode?: string;
  /**
   * Off: the zone lays its elements out itself and the inspector offers typed options.
   * On: the elements keep their own millimetre coordinates and can be dragged.
   */
  freePlacement?: boolean;
  elements: CanvasElement[];
};

/* ---------------------------------------------------------------- page */

export type CopyLabel =
  | 'ORIGINAL_FOR_RECIPIENT'
  | 'DUPLICATE_FOR_TRANSPORTER'
  | 'TRIPLICATE_FOR_SUPPLIER'
  | 'EXTRA_COPY';

export const COPY_LABELS: Record<CopyLabel, string> = {
  ORIGINAL_FOR_RECIPIENT: 'Original for Recipient',
  DUPLICATE_FOR_TRANSPORTER: 'Duplicate for Transporter',
  TRIPLICATE_FOR_SUPPLIER: 'Triplicate for Supplier',
  EXTRA_COPY: 'Extra Copy',
};

export type PrintOptions = {
  /** One printed copy per entry, each carrying its own mark. */
  copies: CopyLabel[];
  copyMarkPosition?: 'top-right' | 'top-center' | 'watermark';
  /** The letterhead is already on the stock, so the header area prints blank. */
  prePrintedStationery?: boolean;
};

export type CanvasTheme = {
  primaryColor: Colour;
  secondaryColor?: Colour;
  fontFamily: string;
  fontSizePt: number;
};

export type CanvasMargins = {
  top: number;
  right: number;
  bottom: number;
  left: number;
  unit: 'mm';
};

export type CanvasPage = {
  size: 'A4' | 'LETTER' | 'A5' | 'THERMAL_80MM' | 'THERMAL_58MM' | 'CUSTOM';
  orientation: 'PORTRAIT' | 'LANDSCAPE';
  widthMm?: number;
  heightMm?: number;
  margins: CanvasMargins;
  gridSnap: boolean;
  gridStepMm: number;
};

export type CanvasDefinition = {
  schemaVersion: typeof SCHEMA_VERSION;
  page: CanvasPage;
  theme: CanvasTheme;
  print: PrintOptions;
  sections: CanvasSection[];
};

/* ---------------------------------------------------------------- template */

export type TemplateStatus = 'DRAFT' | 'PUBLISHED' | 'ARCHIVED';

export type TemplateVersionSummary = {
  id: string;
  versionNumber: number;
  changeSummary?: string;
  createdAt: string;
  publishedAt?: string;
};

export type DesignTemplate = {
  id: string;
  code: string;
  name: string;
  description?: string;
  status: TemplateStatus;
  /** Shipped designs are read-only: a tenant copies one rather than editing it. */
  isSystem: boolean;
  /** `null` until a version has been published — a new template prints nothing. */
  liveVersionId: string | null;
  versions: TemplateVersionSummary[];
  layout: CanvasDefinition;
  /** What the design is for (plan P1): the voucher kind it prints, absent for "any kind". */
  voucherKind?: string;
  /** Whether its lines are products, accounts/expenses, or both. */
  lineProfile?: LineProfile;
};

/** Products, accounts and expenses, or both — what a design's line tables show (plan D2). */
export type LineProfile = 'ITEMS' | 'ACCOUNTS' | 'MIXED';
export const LINE_PROFILES: { value: LineProfile; label: string }[] = [
  { value: 'ITEMS', label: 'Products' },
  { value: 'ACCOUNTS', label: 'Accounts and expenses' },
  { value: 'MIXED', label: 'Products and accounts' },
];

/** The default column set for a GST tax invoice, used when a table is first placed. */
export const DEFAULT_COLUMNS: ItemColumn[] = [
  { key: 'serial_no', widthMm: 8, align: 'right', show: true },
  { key: 'description', widthMm: 62, show: true },
  { key: 'hsn_sac', widthMm: 18, show: true },
  { key: 'quantity', widthMm: 16, align: 'right', show: true },
  { key: 'unit', widthMm: 12, show: true },
  { key: 'rate', widthMm: 20, align: 'right', show: true },
  { key: 'taxable_value', widthMm: 22, align: 'right', show: true },
  { key: 'cgst_amount', widthMm: 16, align: 'right', show: true },
  { key: 'sgst_amount', widthMm: 16, align: 'right', show: true },
  { key: 'amount', widthMm: 22, align: 'right', show: true },
];

/** Default heading per column. A template may override any of them. */
export const COLUMN_LABELS: Record<ColumnKey, string> = {
  serial_no: '#',
  description: 'Description of goods',
  hsn_sac: 'HSN/SAC',
  batch: 'Batch',
  expiry: 'Expiry',
  quantity: 'Qty',
  unit: 'Unit',
  rate: 'Rate',
  mrp: 'MRP',
  discount: 'Disc.',
  taxable_value: 'Taxable value',
  cgst_rate: 'CGST %',
  cgst_amount: 'CGST',
  sgst_rate: 'SGST %',
  sgst_amount: 'SGST',
  igst_rate: 'IGST %',
  igst_amount: 'IGST',
  cess: 'Cess',
  amount: 'Amount',
  account: 'Account',
};

/** An accounts table's starting columns: the ledger, what it was for, and the amount. */
export const DEFAULT_ACCOUNT_COLUMNS: ItemColumn[] = [
  { key: 'serial_no', widthMm: 8, align: 'right', show: true },
  { key: 'account', widthMm: 54, show: true },
  { key: 'description', widthMm: 78, show: true },
  { key: 'taxable_value', widthMm: 25, align: 'right', show: true },
  { key: 'amount', widthMm: 25, align: 'right', show: true },
];

export const TOTALS_LABELS: Record<TotalsRow, string> = {
  subtotal: 'Subtotal',
  discount: 'Discount',
  taxable_value: 'Taxable value',
  cgst: 'CGST',
  sgst: 'SGST',
  igst: 'IGST',
  cess: 'Cess',
  round_off: 'Round off',
  grand_total: 'Total',
  amount_in_words: 'Amount in words',
  outstanding_balance: 'Outstanding balance',
};

/** Columns whose figures are read as numbers, so they are tabular and right-aligned. */
export const NUMERIC_COLUMNS = new Set<ColumnKey>([
  'serial_no',
  'quantity',
  'rate',
  'mrp',
  'discount',
  'taxable_value',
  'cgst_rate',
  'cgst_amount',
  'sgst_rate',
  'sgst_amount',
  'igst_rate',
  'igst_amount',
  'cess',
  'amount',
]);
