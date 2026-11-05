'use client';

import {
  ColourField,
  EditorSelect,
  EditorTextField,
  InspectorEmpty,
  InspectorGroup,
  InspectorRow,
  InspectorStack,
  Kbd,
  MeasureField,
  SegmentedControl,
  Toggle,
  formatMm,
} from '@janso/ui';
import {
  COLUMN_LABELS,
  COPY_LABELS,
  type CopyLabel,
  TOTALS_LABELS,
  type CanvasDefinition,
  type CanvasElement,
  type CanvasSection,
  type ColumnKey,
  type ElementStyle,
  type ItemColumn,
} from './layout-model';
import { availableColumns, availableCopies, availableTotalsRows, pageBox } from './layout-edit';
import { ColumnDesigner, type ColumnDesignerHandlers } from './ColumnDesigner';
import { TotalsBuilder, type TotalsBuilderHandlers } from './TotalsBuilder';
import { AssetPicker } from './AssetPicker';
import type { Target } from './selection';
import { sampleValue } from './sample-document';

/**
 * The inspector: what is selected, and every typed control that changes it.
 *
 * **Typed controls, not a style string.** Each row maps to one field the schema declares,
 * which is why there is no "custom CSS" escape hatch: the one thing this editor must never
 * produce is a layout carrying markup or a stylesheet into a renderer
 * (`docs/invoice-design.md` §6.2). The cost is that a new option means a new typed field,
 * and that is the intended trade.
 *
 * **Every change is live.** The layout is in memory, so there is nothing to debounce and
 * no save button to wait for — the page redraws as the value changes, which is the whole
 * reason to build a designer rather than a form.
 */

/**
 * Document inks offered as one click, and the ink a colour field shows while unset.
 *
 * Literal hex on purpose: these are decisions about the *page*, not about the app's
 * palette. The design system refuses a colour literal for exactly that reason, so the
 * value lives here, with the layout it describes.
 */
const INK_SWATCHES = ['#101114', '#4a4f59', '#1e40af', '#5b6c00', '#8a4b10', '#8c1f2f'];
const DEFAULT_INK = '#101114';

/** Families a print renderer can be relied on to have. */
const FONT_FAMILIES = [
  { value: 'Inter, sans-serif', label: 'Inter (sans)' },
  { value: 'Helvetica, Arial, sans-serif', label: 'Helvetica (sans)' },
  { value: 'Georgia, serif', label: 'Georgia (serif)' },
  { value: 'Times New Roman, serif', label: 'Times (serif)' },
  { value: 'Courier New, monospace', label: 'Courier (mono)' },
] as const;

const PAPER_OPTIONS = [
  { value: 'A4', label: 'A4 · 210 × 297' },
  { value: 'LETTER', label: 'Letter · 216 × 279' },
  { value: 'A5', label: 'A5 · 148 × 210' },
  { value: 'THERMAL_80MM', label: '80mm roll' },
  { value: 'THERMAL_58MM', label: '58mm roll' },
  { value: 'CUSTOM', label: 'Custom' },
] as const;

const ALIGN = [
  { value: 'left', label: '◀', title: 'Left' },
  { value: 'center', label: '■', title: 'Centre' },
  { value: 'right', label: '▶', title: 'Right' },
  { value: 'justify', label: '≡', title: 'Justify' },
] as const;

const WEIGHT = [
  { value: 'normal', label: 'R', title: 'Regular' },
  { value: 'medium', label: 'M', title: 'Medium' },
  { value: 'semibold', label: 'S', title: 'Semibold' },
  { value: 'bold', label: 'B', title: 'Bold' },
] as const;

const VERTICAL = [
  { value: 'top', label: '⌃', title: 'Top' },
  { value: 'middle', label: '–', title: 'Middle' },
  { value: 'bottom', label: '⌄', title: 'Bottom' },
] as const;

const BORDER = [
  { value: 'none', label: 'None' },
  { value: 'solid', label: 'Solid' },
  { value: 'dashed', label: 'Dashed' },
  { value: 'dotted', label: 'Dotted' },
] as const;

export type InspectorHandlers = ColumnDesignerHandlers &
  TotalsBuilderHandlers & {
  onPage: (patch: Partial<CanvasDefinition['page']>) => void;
  onMargins: (patch: Partial<Omit<CanvasDefinition['page']['margins'], 'unit'>>) => void;
  onTheme: (patch: Partial<CanvasDefinition['theme']>) => void;
  onPrint: (patch: Partial<CanvasDefinition['print']>) => void;
  onSection: (id: string, patch: Partial<Omit<CanvasSection, 'id' | 'elements'>>) => void;
  onElement: (id: string, patch: Partial<Omit<CanvasElement, 'id' | 'type'>>) => void;
  onStyle: (id: string, patch: ElementStyle) => void;
  onAddCopy: (copy: CopyLabel) => void;
  onRemoveCopy: (copy: CopyLabel) => void;
  onMoveCopy: (copy: CopyLabel, direction: 'up' | 'down') => void;
  };

type SelectionInspectorProps = {
  layout: CanvasDefinition;
  selection: Target | null;
  handlers: InspectorHandlers;
  /** A shipped template is read-only to every actor: copy it to change it. */
  readOnly?: boolean;
  /** Absent in a company-less session (a fixture, a test): the asset picker stays off. */
  company?: string;
};

export function SelectionInspector({
  layout,
  selection,
  handlers,
  readOnly = false,
  company,
}: SelectionInspectorProps) {
  const box = pageBox(layout.page);

  if (!selection) {
    return (
      <>
        <PageGroup layout={layout} handlers={handlers} readOnly={readOnly} />
        <InspectorEmpty>
          Nothing selected. Click a zone on the page, or press <Kbd>↓</Kbd> on the canvas to
          step through them — <Kbd>→</Kbd> enters a zone, <Kbd>←</Kbd> leaves it, <Kbd>Esc</Kbd>{' '}
          clears.
        </InspectorEmpty>
      </>
    );
  }

  const { rect, section, element } = selection;
  const style = element?.style ?? {};
  const setStyle = (patch: ElementStyle) => element && handlers.onStyle(element.id, patch);

  return (
    <>
      <InspectorGroup title={selection.kind === 'zone' ? 'Zone' : 'Element'}>
        <InspectorRow label="Name">{selection.label}</InspectorRow>
        <InspectorRow label="Type">
          {(element?.type ?? section.type).toLowerCase().replace(/_/g, ' ')}
        </InspectorRow>
        {selection.kind === 'zone' ? (
          <>
            <InspectorRow label="Title">
              <EditorTextField
                label="Zone title"
                value={section.title ?? ''}
                maxLength={60}
                placeholder={section.type.toLowerCase()}
                disabled={readOnly}
                onChange={(title) => handlers.onSection(section.id, { title: title || undefined })}
              />
            </InspectorRow>
            <InspectorRow
              label="Free place"
              hint={
                section.freePlacement
                  ? 'Elements keep their own coordinates in this zone.'
                  : 'The zone lays its elements out. Turn this on to move them by hand.'
              }
            >
              <Toggle
                label="Free placement"
                checked={section.freePlacement ?? false}
                disabled={readOnly}
                onChange={(freePlacement) =>
                  handlers.onSection(section.id, { freePlacement })
                }
              />
            </InspectorRow>
          </>
        ) : (
          <InspectorRow label="In zone">{section.title ?? section.type.toLowerCase()}</InspectorRow>
        )}
      </InspectorGroup>

      <InspectorGroup
        title="Geometry"
        hint="Millimetres. A zone is placed on the page; an element is placed inside its zone."
      >
        <InspectorRow label="X">
          <MeasureField
            label="X position"
            value={selection.kind === 'zone' ? section.xMm : (element?.xMm ?? 0)}
            max={box.widthMm}
            disabled={readOnly}
            onChange={(xMm) =>
              selection.kind === 'zone'
                ? handlers.onSection(section.id, { xMm })
                : element && handlers.onElement(element.id, { xMm })
            }
          />
        </InspectorRow>
        <InspectorRow label="Y">
          <MeasureField
            label="Y position"
            value={selection.kind === 'zone' ? section.yMm : (element?.yMm ?? 0)}
            max={box.heightMm}
            disabled={readOnly}
            onChange={(yMm) =>
              selection.kind === 'zone'
                ? handlers.onSection(section.id, { yMm })
                : element && handlers.onElement(element.id, { yMm })
            }
          />
        </InspectorRow>
        <InspectorRow label="Width">
          <MeasureField
            label="Width"
            value={selection.kind === 'zone' ? section.widthMm : (element?.widthMm ?? 0)}
            min={1}
            max={box.widthMm}
            disabled={readOnly}
            onChange={(widthMm) =>
              selection.kind === 'zone'
                ? handlers.onSection(section.id, { widthMm })
                : element && handlers.onElement(element.id, { widthMm })
            }
          />
        </InspectorRow>
        <InspectorRow label="Height">
          <MeasureField
            label="Height"
            value={selection.kind === 'zone' ? section.heightMm : (element?.heightMm ?? 0)}
            min={1}
            max={box.heightMm}
            disabled={readOnly}
            onChange={(heightMm) =>
              selection.kind === 'zone'
                ? handlers.onSection(section.id, { heightMm })
                : element && handlers.onElement(element.id, { heightMm })
            }
          />
        </InspectorRow>
        <InspectorRow label="On page">
          {formatMm(rect.xMm)}, {formatMm(rect.yMm)} mm
        </InspectorRow>
      </InspectorGroup>

      {element ? (
        <>
          {element.type === 'TEXT' || element.content !== undefined ? (
            <InspectorGroup title="Content">
              <InspectorStack label="Text">
                <EditorTextField
                  label="Static text"
                  value={element.content ?? ''}
                  multiline
                  disabled={readOnly}
                  onChange={(content) => handlers.onElement(element.id, { content })}
                />
              </InspectorStack>
            </InspectorGroup>
          ) : null}

          {element.bindingPath ? (
            <InspectorGroup title="Binding">
              <InspectorRow label="Path">{element.bindingPath}</InspectorRow>
              <InspectorRow label="Label">
                <EditorTextField
                  label="Field label"
                  value={element.label ?? ''}
                  maxLength={200}
                  placeholder="none"
                  disabled={readOnly}
                  onChange={(label) => handlers.onElement(element.id, { label: label || undefined })}
                />
              </InspectorRow>
              <InspectorRow
                label="Sample"
                hint={
                  sampleValue(element.bindingPath) === null
                    ? 'The sample document cannot resolve this path, so the page shows the path instead.'
                    : undefined
                }
              >
                {sampleValue(element.bindingPath) ?? '—'}
              </InspectorRow>
            </InspectorGroup>
          ) : null}

          <InspectorGroup title="Type">
            <InspectorRow label="Size">
              <MeasureField
                label="Font size"
                value={style.fontSizePt ?? Number.NaN}
                unit="pt"
                min={4}
                max={72}
                step={0.5}
                placeholder="inherit"
                disabled={readOnly}
                onChange={(fontSizePt) => setStyle({ fontSizePt })}
              />
            </InspectorRow>
            <InspectorRow label="Weight">
              <SegmentedControl
                label="Font weight"
                value={style.fontWeight ?? null}
                options={WEIGHT}
                disabled={readOnly}
                onChange={(fontWeight) => setStyle({ fontWeight })}
              />
            </InspectorRow>
            <InspectorRow label="Align">
              <SegmentedControl
                label="Text alignment"
                value={style.textAlign ?? null}
                options={ALIGN}
                disabled={readOnly}
                onChange={(textAlign) => setStyle({ textAlign })}
              />
            </InspectorRow>
            <InspectorRow label="Vertical">
              <SegmentedControl
                label="Vertical alignment"
                value={style.verticalAlign ?? null}
                options={VERTICAL}
                disabled={readOnly}
                onChange={(verticalAlign) => setStyle({ verticalAlign })}
              />
            </InspectorRow>
            <InspectorRow label="Italic">
              <Toggle
                label="Italic"
                checked={style.fontStyle === 'italic'}
                disabled={readOnly}
                onChange={(italic) => setStyle({ fontStyle: italic ? 'italic' : undefined })}
              />
            </InspectorRow>
            <InspectorRow label="Uppercase">
              <Toggle
                label="Uppercase"
                checked={style.uppercase ?? false}
                disabled={readOnly}
                onChange={(uppercase) => setStyle({ uppercase: uppercase || undefined })}
              />
            </InspectorRow>
            <InspectorRow label="Line height">
              <MeasureField
                label="Line height"
                value={style.lineHeight ?? Number.NaN}
                unit="×"
                min={0.5}
                max={4}
                step={0.05}
                placeholder="inherit"
                disabled={readOnly}
                onChange={(lineHeight) => setStyle({ lineHeight })}
              />
            </InspectorRow>
            <InspectorStack label="Colour">
              <ColourField
                label="Text colour"
                value={style.color ?? null}
                swatches={INK_SWATCHES}
                fallback={DEFAULT_INK}
                disabled={readOnly}
                onChange={(color) => setStyle({ color })}
              />
            </InspectorStack>
          </InspectorGroup>

          <InspectorGroup title="Box">
            <InspectorRow label="Padding">
              <MeasureField
                label="Padding"
                value={style.paddingMm ?? Number.NaN}
                min={0}
                max={50}
                step={0.5}
                placeholder="none"
                disabled={readOnly}
                onChange={(paddingMm) => setStyle({ paddingMm })}
              />
            </InspectorRow>
            <InspectorRow label="Border">
              <SegmentedControl
                label="Border style"
                value={style.borderStyle ?? null}
                options={BORDER}
                disabled={readOnly}
                onChange={(borderStyle) =>
                  setStyle({
                    borderStyle,
                    // A border with no width is invisible; give it one the first time.
                    borderWidthMm:
                      borderStyle === 'none' ? undefined : (style.borderWidthMm ?? 0.2),
                  })
                }
              />
            </InspectorRow>
            {style.borderStyle && style.borderStyle !== 'none' ? (
              <>
                <InspectorRow label="Thickness">
                  <MeasureField
                    label="Border thickness"
                    value={style.borderWidthMm ?? 0.2}
                    min={0.1}
                    max={10}
                    step={0.1}
                    disabled={readOnly}
                    onChange={(borderWidthMm) => setStyle({ borderWidthMm })}
                  />
                </InspectorRow>
                <InspectorStack label="Border colour">
                  <ColourField
                    label="Border colour"
                    value={style.borderColor ?? null}
                    swatches={INK_SWATCHES}
                fallback={DEFAULT_INK}
                    disabled={readOnly}
                    onChange={(borderColor) => setStyle({ borderColor })}
                  />
                </InspectorStack>
              </>
            ) : null}
            <InspectorStack label="Background">
              <ColourField
                label="Background colour"
                value={style.backgroundColor ?? null}
                swatches={INK_SWATCHES}
                fallback={DEFAULT_INK}
                disabled={readOnly}
                onChange={(backgroundColor) => setStyle({ backgroundColor })}
              />
            </InspectorStack>
          </InspectorGroup>

          {element.type === 'IMAGE' ? (
            <InspectorGroup title="Image">
              {company ? (
                <AssetPicker
                  company={company}
                  elementType="IMAGE"
                  value={element.assetId}
                  disabled={readOnly}
                  onChange={(assetId) => handlers.onElement(element.id, { assetId })}
                />
              ) : null}
              <InspectorRow label="Fit">
                <SegmentedControl
                  label="Image fit"
                  value={element.imageFit ?? 'contain'}
                  options={[
                    { value: 'contain', label: 'Contain' },
                    { value: 'cover', label: 'Cover' },
                    { value: 'fill', label: 'Fill' },
                  ]}
                  disabled={readOnly}
                  onChange={(imageFit) => handlers.onElement(element.id, { imageFit })}
                />
              </InspectorRow>
            </InspectorGroup>
          ) : null}

          {element.type === 'SIGNATURE' && company ? (
            <InspectorGroup title="Signature image" hint="A scanned signature or stamp, printed above the signatory line.">
              <AssetPicker
                company={company}
                elementType="SIGNATURE"
                value={element.assetId}
                disabled={readOnly}
                onChange={(assetId) => handlers.onElement(element.id, { assetId })}
              />
            </InspectorGroup>
          ) : null}

          {element.type === 'QR_CODE' || element.type === 'BARCODE' ? (
            <InspectorGroup title="Symbol">
              <InspectorRow label="Symbology">
                <EditorSelect
                  label="Symbology"
                  value={element.symbology ?? 'QR'}
                  options={[
                    { value: 'QR', label: 'QR' },
                    { value: 'CODE128', label: 'Code 128' },
                    { value: 'EAN13', label: 'EAN-13' },
                    { value: 'DATAMATRIX', label: 'Data Matrix' },
                  ]}
                  disabled={readOnly}
                  onChange={(symbology) => handlers.onElement(element.id, { symbology })}
                />
              </InspectorRow>
              <InspectorRow label="Show value">
                <Toggle
                  label="Print the value under the symbol"
                  checked={element.showValue ?? false}
                  disabled={readOnly}
                  onChange={(showValue) => handlers.onElement(element.id, { showValue })}
                />
              </InspectorRow>
            </InspectorGroup>
          ) : null}

          {element.type === 'TAX_SUMMARY' ? (
            <InspectorGroup title="Tax summary">
              <InspectorRow label="Group by">
                <SegmentedControl
                  label="Tax grouping"
                  value={element.taxGrouping ?? 'by_hsn'}
                  options={[
                    { value: 'by_rate', label: 'Rate' },
                    { value: 'by_hsn', label: 'HSN' },
                    { value: 'none', label: 'None' },
                  ]}
                  disabled={readOnly}
                  onChange={(taxGrouping) => handlers.onElement(element.id, { taxGrouping })}
                />
              </InspectorRow>
              <InspectorRow label="Cess">
                <Toggle
                  label="Show cess"
                  checked={element.showCess ?? false}
                  disabled={readOnly}
                  onChange={(showCess) => handlers.onElement(element.id, { showCess })}
                />
              </InspectorRow>
            </InspectorGroup>
          ) : null}

          {element.columns ? (
            <ColumnDesigner
              element={element}
              available={availableColumns(element)}
              handlers={handlers}
              readOnly={readOnly}
            />
          ) : null}

          {element.totalsRows ? (
            <TotalsBuilder
              element={element}
              available={availableTotalsRows(element)}
              handlers={handlers}
              readOnly={readOnly}
            />
          ) : null}
        </>
      ) : null}

      <PageGroup layout={layout} handlers={handlers} readOnly={readOnly} />
    </>
  );
}

function PageGroup({
  layout,
  handlers,
  readOnly,
}: {
  layout: CanvasDefinition;
  handlers: InspectorHandlers;
  readOnly: boolean;
}) {
  const box = pageBox(layout.page);
  const custom = layout.page.size === 'CUSTOM';
  const roll = layout.page.size === 'THERMAL_80MM' || layout.page.size === 'THERMAL_58MM';

  return (
    <>
      <InspectorGroup title="Page">
        <InspectorRow label="Paper">
          <EditorSelect
            label="Paper size"
            value={layout.page.size}
            options={PAPER_OPTIONS}
            disabled={readOnly}
            onChange={(size) => handlers.onPage({ size })}
          />
        </InspectorRow>
        <InspectorRow
          label="Orientation"
          hint={roll ? 'Roll stock has a fixed width, so it does not rotate.' : undefined}
        >
          <SegmentedControl
            label="Orientation"
            value={layout.page.orientation}
            options={[
              { value: 'PORTRAIT', label: 'Portrait' },
              { value: 'LANDSCAPE', label: 'Landscape' },
            ]}
            disabled={readOnly || roll}
            onChange={(orientation) => handlers.onPage({ orientation })}
          />
        </InspectorRow>
        {custom ? (
          <>
            <InspectorRow label="Width">
              <MeasureField
                label="Page width"
                value={layout.page.widthMm ?? 210}
                min={20}
                max={1000}
                disabled={readOnly}
                onChange={(widthMm) => handlers.onPage({ widthMm })}
              />
            </InspectorRow>
            <InspectorRow label="Height">
              <MeasureField
                label="Page height"
                value={layout.page.heightMm ?? 297}
                min={20}
                max={2000}
                disabled={readOnly}
                onChange={(heightMm) => handlers.onPage({ heightMm })}
              />
            </InspectorRow>
          </>
        ) : (
          <InspectorRow label="Size">
            {formatMm(box.widthMm)} × {formatMm(box.heightMm)} mm
          </InspectorRow>
        )}
      </InspectorGroup>

      <InspectorGroup title="Margins" hint="Content outside these does not print.">
        {(['top', 'right', 'bottom', 'left'] as const).map((edge) => (
          <InspectorRow key={edge} label={edge[0]!.toUpperCase() + edge.slice(1)}>
            <MeasureField
              label={`${edge} margin`}
              value={layout.page.margins[edge]}
              min={0}
              max={Math.max(0, (edge === 'top' || edge === 'bottom' ? box.heightMm : box.widthMm) / 2)}
              disabled={readOnly}
              onChange={(value) => handlers.onMargins({ [edge]: value })}
            />
          </InspectorRow>
        ))}
      </InspectorGroup>

      <InspectorGroup title="Grid">
        <InspectorRow label="Step">
          <MeasureField
            label="Grid step"
            value={layout.page.gridStepMm}
            min={1}
            max={50}
            disabled={readOnly}
            onChange={(gridStepMm) => handlers.onPage({ gridStepMm })}
          />
        </InspectorRow>
        <InspectorRow label="Snap">
          <Toggle
            label="Snap to grid"
            checked={layout.page.gridSnap}
            disabled={readOnly}
            onChange={(gridSnap) => handlers.onPage({ gridSnap })}
          />
        </InspectorRow>
      </InspectorGroup>

      <InspectorGroup title="Theme" hint="The document's own voice, not the app's palette.">
        <InspectorRow label="Font">
          <EditorSelect
            label="Font family"
            value={layout.theme.fontFamily}
            options={FONT_FAMILIES}
            disabled={readOnly}
            onChange={(fontFamily) => handlers.onTheme({ fontFamily })}
          />
        </InspectorRow>
        <InspectorRow label="Base size">
          <MeasureField
            label="Base font size"
            value={layout.theme.fontSizePt}
            unit="pt"
            min={4}
            max={24}
            step={0.5}
            disabled={readOnly}
            onChange={(fontSizePt) => handlers.onTheme({ fontSizePt })}
          />
        </InspectorRow>
        <InspectorStack label="Primary">
          <ColourField
            label="Primary colour"
            value={layout.theme.primaryColor}
            swatches={INK_SWATCHES}
            fallback={DEFAULT_INK}
            disabled={readOnly}
            onChange={(primaryColor) => handlers.onTheme({ primaryColor })}
          />
        </InspectorStack>
      </InspectorGroup>

      <InspectorGroup title="Print">
        <InspectorRow
          label="Letterhead"
          hint="Pre-printed stationery already carries the header, so it prints blank."
        >
          <Toggle
            label="Pre-printed stationery"
            checked={layout.print.prePrintedStationery ?? false}
            disabled={readOnly}
            onChange={(prePrintedStationery) => handlers.onPrint({ prePrintedStationery })}
          />
        </InspectorRow>
        <InspectorRow label="Copy mark">
          <SegmentedControl
            label="Copy mark position"
            value={layout.print.copyMarkPosition ?? 'top-right'}
            options={[
              { value: 'top-right', label: 'Right' },
              { value: 'top-center', label: 'Centre' },
              { value: 'watermark', label: 'Mark' },
            ]}
            disabled={readOnly}
            onChange={(copyMarkPosition) => handlers.onPrint({ copyMarkPosition })}
          />
        </InspectorRow>

        {/* The set of copies, in the order they come off the printer. A list rather than a
          * count, because the mark on each is what makes a GST invoice set legal: the
          * transporter's copy is not interchangeable with the supplier's. */}
        <InspectorRow
          label="Copies"
          hint={`${layout.print.copies.length} printed per document, in this order.`}
        >
          <ul className="janso-editor__list">
            {layout.print.copies.map((copy, index) => (
              <li key={copy} className="janso-editor__row--stack">
                <span className="janso-editor__row-value">{COPY_LABELS[copy]}</span>
                <span className="janso-editor__arrange janso-editor__arrange--pair">
                  <button
                    type="button"
                    className="janso-editor__button"
                    aria-label={`Move ${COPY_LABELS[copy]} earlier`}
                    disabled={readOnly || index === 0}
                    onClick={() => handlers.onMoveCopy(copy, 'up')}
                  >
                    ↑
                  </button>
                  <button
                    type="button"
                    className="janso-editor__button"
                    aria-label={`Move ${COPY_LABELS[copy]} later`}
                    disabled={readOnly || index === layout.print.copies.length - 1}
                    onClick={() => handlers.onMoveCopy(copy, 'down')}
                  >
                    ↓
                  </button>
                  <button
                    type="button"
                    className="janso-editor__button janso-editor__button--danger"
                    aria-label={`Remove ${COPY_LABELS[copy]}`}
                    /* Never the last one: a template that prints no copies prints
                     * nothing, and the add menu reads the list it just emptied. */
                    disabled={readOnly || layout.print.copies.length <= 1}
                    onClick={() => handlers.onRemoveCopy(copy)}
                  >
                    Remove
                  </button>
                </span>
              </li>
            ))}
          </ul>
        </InspectorRow>

        {availableCopies(layout).length > 0 ? (
          <InspectorRow label="Add copy">
            <EditorSelect
              label="Add a printed copy"
              value=""
              options={[
                { value: '', label: 'Choose a copy…' },
                ...availableCopies(layout).map((copy) => ({
                  value: copy,
                  label: COPY_LABELS[copy],
                })),
              ]}
              disabled={readOnly}
              onChange={(value) => {
                if (value) handlers.onAddCopy(value as CopyLabel);
              }}
            />
          </InspectorRow>
        ) : null}
      </InspectorGroup>
    </>
  );
}
