import type { CSSProperties, ReactNode } from 'react';
import {
  COLUMN_LABELS,
  COPY_LABELS,
  type CanvasDefinition,
  type CanvasElement,
  type CanvasSection,
  type CopyLabel,
  type ElementStyle,
  type ItemColumn,
  NUMERIC_COLUMNS,
  TOTALS_LABELS,
  type TotalsRow,
} from './layout-model';
import { SAMPLE_ASSETS } from './sample-templates';
import { SAMPLE_ACCOUNT_LINES, SAMPLE_DOCUMENT, type AccountLine, type DocumentLine, sampleValue } from './sample-document';
import type { AssetSource } from '../../lib/design-assets';

/**
 * Renders a layout tree onto the paper.
 *
 * This is the client's own rendering of the document — the editor's live preview. The
 * authoritative PDF will come from a server renderer that must produce the same result
 * (`docs/invoice-design.md` §9.1); until it exists, this is the only thing that draws an
 * invoice, and "Download PDF" stays disabled rather than shipping a second, different
 * answer.
 *
 * Three rules it follows, because they are the schema's rules:
 *
 *   **Geometry is inline and in millimetres.** Position and size come from the layout at
 *   runtime, so they cannot live in a stylesheet; everything else is a token class.
 *
 *   **Text is printed as text.** `content` is rendered into a text node, never as markup,
 *   and the typed style fields are the only thing that can change its appearance.
 *
 *   **A missing binding shows its placeholder.** An element bound to a path the document
 *   cannot resolve renders the path in brackets, so a designer sees the gap on the page
 *   instead of an empty box they assume is a layout bug.
 */

function box(element: Pick<CanvasElement, 'xMm' | 'yMm' | 'widthMm' | 'heightMm' | 'zIndex'>) {
  return {
    left: `${element.xMm}mm`,
    top: `${element.yMm}mm`,
    width: `${element.widthMm}mm`,
    height: `${element.heightMm}mm`,
    zIndex: element.zIndex,
  } satisfies CSSProperties;
}

/** The typed style fields, as CSS. Nothing here accepts a free-form string. */
function styleOf(style: ElementStyle | undefined): CSSProperties {
  if (!style) return {};
  const weight = { normal: 400, medium: 500, semibold: 600, bold: 700 };
  return {
    fontSize: style.fontSizePt ? `${style.fontSizePt}pt` : undefined,
    fontWeight: style.fontWeight ? weight[style.fontWeight] : undefined,
    fontStyle: style.fontStyle,
    color: style.color,
    background: style.backgroundColor,
    textAlign: style.textAlign,
    borderWidth: style.borderWidthMm ? `${style.borderWidthMm}mm` : undefined,
    borderStyle: style.borderStyle,
    borderColor: style.borderColor,
    padding: style.paddingMm ? `${style.paddingMm}mm` : undefined,
    opacity: style.opacity,
    lineHeight: style.lineHeight,
    textTransform: style.uppercase ? 'uppercase' : undefined,
    display: style.verticalAlign ? 'flex' : undefined,
    alignItems:
      style.verticalAlign === 'middle'
        ? 'center'
        : style.verticalAlign === 'bottom'
          ? 'flex-end'
          : style.verticalAlign === 'top'
            ? 'flex-start'
            : undefined,
  };
}

/**
 * Whether the page prints the sample document's values or the bindings themselves.
 *
 * `placeholder` is not a debug view. "Nandini Trading Company" on the page tells a
 * designer nothing about whether that box is `company.name` or `company.legal_name`, and
 * picking the wrong one is a mistake that only surfaces for the customer whose two differ.
 * So the mode swaps every resolved value for the path behind it, and leaves everything
 * else — labels, headings, the number of rows — exactly where it was, because the geometry
 * is the thing a WYSIWYG canvas is for and a mode that reflowed the page would be useless
 * for checking it.
 */
export type ValueMode = 'resolved' | 'placeholder';

/** A binding printed as itself. */
function placeholder(path: string) {
  return <span className="janso-doc-binding">{`{{${path}}}`}</span>;
}

function accountCell(line: AccountLine, key: ItemColumn['key']): string {
  const map: Partial<Record<ItemColumn['key'], string>> = {
    serial_no: line.serialNo,
    account: line.account,
    description: line.description,
    taxable_value: line.taxableValue,
    cgst_rate: line.cgstRate,
    cgst_amount: line.cgstAmount,
    sgst_rate: line.sgstRate,
    sgst_amount: line.sgstAmount,
    amount: line.amount,
  };
  return map[key] ?? '—';
}

/** Accounts and expenses: the ledger each line posts to, with sample expense lines. */
function AccountTable({ element, mode }: { element: CanvasElement; mode: ValueMode }) {
  const shown = (element.columns ?? []).filter((column) => column.show);
  const blanks = Array.from({ length: element.rowOptions?.blankRows ?? 0 }, (_, index) => index);
  return (
    <table className="janso-doc-table">
      <thead>
        <tr>
          {shown.map((column) => (
            <th key={column.key} className={NUMERIC_COLUMNS.has(column.key) ? 'janso-doc-table__num' : undefined} style={{ width: `${column.widthMm}mm` }}>
              {column.label ?? (column.key === 'description' ? 'Particulars' : COLUMN_LABELS[column.key])}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {SAMPLE_ACCOUNT_LINES.map((line) => (
          <tr key={line.serialNo}>
            {shown.map((column) => (
              <td key={column.key} className={NUMERIC_COLUMNS.has(column.key) ? 'janso-doc-table__num' : undefined}>
                {mode === 'placeholder' ? placeholder(column.key) : accountCell(line, column.key)}
              </td>
            ))}
          </tr>
        ))}
        {blanks.map((index) => (
          <tr key={`blank-${index}`} className="janso-doc-table__blank">
            {shown.map((column) => <td key={column.key} />)}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function cellValue(line: DocumentLine, key: ItemColumn['key']): string {
  const map: Partial<Record<ItemColumn['key'], string | undefined>> = {
    serial_no: line.serialNo,
    description: line.description,
    hsn_sac: line.hsnSac,
    batch: line.batch,
    expiry: line.expiry,
    quantity: line.quantity,
    unit: line.unit,
    rate: line.rate,
    mrp: line.mrp,
    discount: line.discount,
    taxable_value: line.taxableValue,
    cgst_rate: line.cgstRate,
    cgst_amount: line.cgstAmount,
    sgst_rate: line.sgstRate,
    sgst_amount: line.sgstAmount,
    amount: line.amount,
  };
  return map[key] ?? '—';
}

function totalsValue(row: TotalsRow): string {
  const t = SAMPLE_DOCUMENT.totals;
  const map: Record<TotalsRow, string> = {
    subtotal: t.subtotal,
    discount: t.discount,
    taxable_value: t.taxableValue,
    cgst: t.cgst,
    sgst: t.sgst,
    igst: t.igst,
    cess: t.cess,
    round_off: t.roundOff,
    grand_total: t.grandTotal,
    amount_in_words: t.amountInWords,
    outstanding_balance: t.outstandingBalance,
  };
  return map[row];
}

function ItemTable({ element, mode }: { element: CanvasElement; mode: ValueMode }) {
  const shown = (element.columns ?? []).filter((column) => column.show);
  const options = element.rowOptions ?? {};
  const blanks = Array.from({ length: options.blankRows ?? 0 }, (_, index) => index);

  return (
    <table className="janso-doc-table">
      <thead>
        <tr>
          {shown.map((column) => (
            <th
              key={column.key}
              className={NUMERIC_COLUMNS.has(column.key) ? 'janso-doc-table__num' : undefined}
              style={{ width: `${column.widthMm}mm` }}
            >
              {column.label ?? COLUMN_LABELS[column.key]}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {SAMPLE_DOCUMENT.lines.map((line) => (
          <tr key={line.serialNo}>
            {shown.map((column) => (
              <td
                key={column.key}
                className={NUMERIC_COLUMNS.has(column.key) ? 'janso-doc-table__num' : undefined}
              >
                {/* The heading already names the column, so a cell says the leaf of its
                  * path rather than `line.description` — a 14mm quantity column cannot
                  * carry the prefix and does not need it. */}
                {mode === 'placeholder' ? placeholder(column.key) : cellValue(line, column.key)}
                {mode === 'resolved' &&
                column.key === 'description' &&
                options.descriptionUnderItem &&
                line.subDescription ? (
                  <div className="janso-doc-table__desc">{line.subDescription}</div>
                ) : null}
              </td>
            ))}
          </tr>
        ))}
        {/* Filler rows keep a ruled box looking full on pre-printed stationery. */}
        {blanks.map((index) => (
          <tr key={`blank-${index}`} className="janso-doc-table__blank">
            {shown.map((column) => (
              <td key={column.key} />
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function TaxSummary({ element, mode }: { element: CanvasElement; mode: ValueMode }) {
  const grouped = element.taxGrouping ?? 'by_hsn';
  if (grouped === 'none') return null;
  return (
    <table className="janso-doc-table">
      <thead>
        <tr>
          <th>{grouped === 'by_hsn' ? 'HSN/SAC' : 'Rate'}</th>
          <th className="janso-doc-table__num">Taxable value</th>
          <th className="janso-doc-table__num">CGST</th>
          <th className="janso-doc-table__num">SGST</th>
        </tr>
      </thead>
      <tbody>
        {SAMPLE_DOCUMENT.taxSummary.map((row) => (
          <tr key={row.hsnSac}>
            <td>
              {mode === 'placeholder'
                ? placeholder(grouped === 'by_hsn' ? 'hsn_sac' : 'rate')
                : grouped === 'by_hsn'
                  ? row.hsnSac
                  : `${row.cgstRate}% + ${row.sgstRate}%`}
            </td>
            <td className="janso-doc-table__num">
              {mode === 'placeholder' ? placeholder('taxable_value') : row.taxableValue}
            </td>
            <td className="janso-doc-table__num">
              {mode === 'placeholder' ? placeholder('cgst') : row.cgstAmount}
            </td>
            <td className="janso-doc-table__num">
              {mode === 'placeholder' ? placeholder('sgst') : row.sgstAmount}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function TotalsBlock({ element, mode }: { element: CanvasElement; mode: ValueMode }) {
  const rows = element.totalsRows ?? [];
  const value = (row: TotalsRow) =>
    mode === 'placeholder' ? placeholder(row) : totalsValue(row);
  return (
    <div className="janso-doc-totals">
      {rows.map((row) =>
        row === 'amount_in_words' ? (
          <div key={row} className="janso-doc-totals__row janso-doc-totals__row--words">
            {TOTALS_LABELS[row]}: {value(row)}
          </div>
        ) : (
          <div
            key={row}
            className={`janso-doc-totals__row${row === 'grand_total' ? ' janso-doc-totals__row--grand' : ''}`}
          >
            <span>{TOTALS_LABELS[row]}</span>
            <span className="janso-doc-totals__amount">{value(row)}</span>
          </div>
        ),
      )}
    </div>
  );
}

/**
 * Where an `assetId` resolves to a rendered image: a fixture (the sample templates ship ids
 * like `asset-logo`), or a real upload — `company` and `assets` are absent for a fixture-only
 * session, in which case a real `assetId` has nothing to resolve against and the element shows
 * its empty state rather than guessing.
 */
function resolveImage(
  assetId: string | undefined,
  company: string | undefined,
  assets: AssetSource | undefined,
): { src: string; alt: string } | null {
  if (!assetId) return null;
  const sample = SAMPLE_ASSETS[assetId];
  if (sample) return { src: sample.dataUri, alt: sample.name };
  const real = assets?.[assetId];
  if (!company || !real) return null;
  return {
    src: `/api/design-asset?company=${company}&asset=${assetId}&token=${encodeURIComponent(real.downloadToken)}`,
    alt: 'Brand asset',
  };
}

function elementBody(
  element: CanvasElement,
  mode: ValueMode,
  company: string | undefined,
  assets: AssetSource | undefined,
): ReactNode {
  switch (element.type) {
    case 'TEXT':
      return <span className="janso-doc-text">{element.content}</span>;

    case 'FIELD_BINDING': {
      const value = element.bindingPath ? sampleValue(element.bindingPath) : null;
      return (
        <span className="janso-doc-text">
          {/* A label is static text the document always prints, so it survives the mode. */}
          {element.label ? <span className="janso-doc-text--label">{element.label} </span> : null}
          {mode === 'placeholder'
            ? placeholder(element.bindingPath ?? 'unbound')
            : (value ?? `[${element.bindingPath ?? 'unbound'}]`)}
        </span>
      );
    }

    case 'IMAGE': {
      const image = resolveImage(element.assetId, company, assets);
      return (
        <span className="janso-doc-image">
          {image ? (
            // eslint-disable-next-line @next/next/no-img-element -- a data URI or a signed download, measured in mm
            <img src={image.src} alt={image.alt} style={{ objectFit: element.imageFit }} />
          ) : (
            <span className="janso-doc-qr">No asset</span>
          )}
        </span>
      );
    }

    case 'ITEM_TABLE':
      return <ItemTable element={element} mode={mode} />;

    case 'ACCOUNT_TABLE':
      return <AccountTable element={element} mode={mode} />;

    case 'TAX_SUMMARY':
      return <TaxSummary element={element} mode={mode} />;

    case 'TOTALS_BLOCK':
      return <TotalsBlock element={element} mode={mode} />;

    case 'QR_CODE':
    case 'BARCODE':
      // A placeholder, not a drawn symbol: an encoder belongs with the renderer, and a
      // fake barcode in a preview is worse than an honest box.
      return <span className="janso-doc-qr">{element.symbology ?? element.type}</span>;

    case 'SIGNATURE': {
      const image = resolveImage(element.assetId, company, assets);
      return (
        <span className="janso-doc-sign">
          {image ? (
            // eslint-disable-next-line @next/next/no-img-element -- a data URI or a signed download, measured in mm
            <img src={image.src} alt={image.alt} style={{ maxHeight: '60%' }} />
          ) : null}
          <span>{element.content}</span>
          {element.label ? <span className="janso-doc-text--label">{element.label}</span> : null}
        </span>
      );
    }

    case 'DIVIDER':
      return <span className="janso-doc-divider" />;

    case 'SHAPE':
      return null;

    default:
      return null;
  }
}

type DocumentLayerProps = {
  layout: CanvasDefinition;
  /** Which printed copy to preview; its mark is part of the page. */
  copy?: CopyLabel | null;
  /** Sample values, or the bindings behind them. Resolved is the working default. */
  values?: ValueMode;
  /** Absent in a company-less session: a real `assetId` then shows its empty state. */
  company?: string;
  assets?: AssetSource;
};

export function DocumentLayer({ layout, copy = null, values = 'resolved', company, assets }: DocumentLayerProps) {
  const mark = copy ? COPY_LABELS[copy] : null;

  return (
    <div
      className="janso-doc"
      style={{ fontFamily: layout.theme.fontFamily, fontSize: `${layout.theme.fontSizePt}pt` }}
    >
      {mark && layout.print.copyMarkPosition === 'watermark' ? (
        <span className="janso-doc-copymark">{mark}</span>
      ) : null}

      {layout.sections.map((sectionNode: CanvasSection) => (
        <div
          key={sectionNode.id}
          className="janso-doc__section"
          style={box(sectionNode)}
          data-section={sectionNode.id}
          data-section-type={sectionNode.type}
        >
          {/* The letterhead is already on the stock, so the header area prints blank. */}
          {layout.print.prePrintedStationery && sectionNode.type === 'HEADER'
            ? null
            : sectionNode.elements.map((element) => (
                <div
                  key={element.id}
                  className="janso-doc__el"
                  style={{ ...box(element), ...styleOf(element.style) }}
                  data-element={element.id}
                  data-element-type={element.type}
                >
                  {elementBody(element, values, company, assets)}
                </div>
              ))}
        </div>
      ))}

      {mark && layout.print.copyMarkPosition !== 'watermark' ? (
        <div
          className="janso-doc__el janso-doc-text--label"
          style={{
            left: `${layout.page.margins.left}mm`,
            top: '2mm',
            width: `${(layout.page.widthMm ?? 210) - layout.page.margins.left * 2}mm`,
            height: '4mm',
            textAlign: layout.print.copyMarkPosition === 'top-center' ? 'center' : 'right',
          }}
          data-element="copy-mark"
        >
          {mark}
        </div>
      ) : null}
    </div>
  );
}
