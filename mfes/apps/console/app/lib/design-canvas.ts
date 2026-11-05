import type { components } from '@janso/api-client/design';
import type {
  CanvasDefinition,
  CanvasElement,
  CanvasMargins,
  CanvasPage,
  CanvasSection,
  CanvasTheme,
  ColumnKey,
  CopyLabel,
  DesignTemplate,
  ElementStyle,
  ItemColumn,
  PrintOptions,
  TemplateStatus,
  TemplateVersionSummary,
  TotalsRow,
  LineProfile,
} from '../(editor)/invoice-designer/layout-model';
import { SCHEMA_VERSION } from '../(editor)/invoice-designer/layout-model';

type Wire = components['schemas'];
type WireCanvas = Wire['CanvasV11'];
type WireSection = Wire['CanvasSectionV11'];
type WireElement = Wire['CanvasElementV11'];
type WireStyle = Wire['CanvasStyle'];
type WireTheme = Wire['CanvasTheme'];
type WireMargins = Wire['CanvasMargins'];
type WirePrint = Wire['PrintOptions'];
type WireColumn = Wire['ItemColumn'];

/**
 * The boundary between the `design` service's canvas and the editor's own layout model.
 *
 * Both halves were built honestly and they do not speak the same dialect, so something has to
 * translate — and the translation is small, total and tested rather than scattered through the
 * editor. Three kinds of difference, and it is worth being clear which is which:
 *
 *  1. **Case.** The service is snake_case like every other service in the platform; the editor
 *     is camelCase like every other React tree. Mechanical.
 *  2. **Unit in the name.** The editor spells geometry `xMm`/`widthMm` because a number called
 *     `x` in a React prop is the thing that eventually gets multiplied by a zoom factor and
 *     silently becomes pixels. Inside the service's tree everything is millimetres by
 *     construction, so it says `x`. Also mechanical, but not a case change — which is exactly
 *     why this file is hand-written and type-checked rather than a generic key converter: the
 *     compiler catches the day one of these shapes moves and a converter would not.
 *  3. **Ownership.** Paper size and orientation are the *template row's*, not the layout's
 *     (docs/invoice-design.md, decision 2026-10-27). So `toEditor` needs the row to assemble
 *     the editor's `page`, and `toWire` deliberately drops those fields rather than sending a
 *     second, disagreeing copy of them.
 *
 * `print_options` ⇄ `print` is the one plain rename, kept because renaming it in the editor
 * would have touched a dozen call sites for no gain.
 *
 * **Round-tripping is the contract**, and `design-canvas.test.ts` asserts it: a layout that
 * leaves the service and comes back must be byte-identical, or an untouched save would produce
 * a new `layout_digest` and the version history would fill with revisions nobody made.
 */

/* ------------------------------------------------------------------ service → editor */

function marginsToEditor(wire: WireMargins | undefined): CanvasMargins {
  return {
    top: wire?.top ?? 10,
    right: wire?.right ?? 10,
    bottom: wire?.bottom ?? 10,
    left: wire?.left ?? 10,
    unit: 'mm',
  };
}

function themeToEditor(wire: WireTheme | undefined): CanvasTheme {
  return {
    primaryColor: wire?.primary_color ?? '#1E40AF',
    ...(wire?.secondary_color != null ? { secondaryColor: wire.secondary_color } : {}),
    fontFamily: wire?.font_family ?? 'Inter, sans-serif',
    fontSizePt: wire?.font_size_pt ?? 9,
  };
}

/** Undefined-valued keys are omitted rather than written, so a round trip adds no nulls. */
function styleToEditor(wire: WireStyle | null | undefined): ElementStyle | undefined {
  if (!wire) return undefined;
  const style: ElementStyle = {};
  if (wire.font_size_pt != null) style.fontSizePt = wire.font_size_pt;
  if (wire.font_weight != null) style.fontWeight = wire.font_weight;
  if (wire.font_style != null) style.fontStyle = wire.font_style;
  if (wire.color != null) style.color = wire.color;
  if (wire.background_color != null) style.backgroundColor = wire.background_color;
  if (wire.text_align != null) style.textAlign = wire.text_align;
  if (wire.vertical_align != null) style.verticalAlign = wire.vertical_align;
  if (wire.border_width_mm != null) style.borderWidthMm = wire.border_width_mm;
  if (wire.border_style != null) style.borderStyle = wire.border_style;
  if (wire.border_color != null) style.borderColor = wire.border_color;
  if (wire.padding_mm != null) style.paddingMm = wire.padding_mm;
  if (wire.opacity != null) style.opacity = wire.opacity;
  if (wire.line_height != null) style.lineHeight = wire.line_height;
  if (wire.uppercase != null) style.uppercase = wire.uppercase;
  return Object.keys(style).length ? style : undefined;
}

function printToEditor(wire: WirePrint | undefined): PrintOptions {
  return {
    copies: (wire?.copies ?? ['ORIGINAL_FOR_RECIPIENT']) as CopyLabel[],
    ...(wire?.copy_mark_position != null ? { copyMarkPosition: wire.copy_mark_position } : {}),
    // `!= null`, not truthiness. A template that says "no, this stock is blank" wrote
    // `false` deliberately, and collapsing it to an absent key is a different document —
    // the round-trip test is what caught this.
    ...(wire?.pre_printed_stationery != null
      ? { prePrintedStationery: wire.pre_printed_stationery }
      : {}),
  };
}

function columnToEditor(wire: WireColumn): ItemColumn {
  return {
    key: wire.key as ColumnKey,
    ...(wire.label != null ? { label: wire.label } : {}),
    widthMm: wire.width_mm,
    ...(wire.align != null ? { align: wire.align } : {}),
    show: wire.show ?? true,
  };
}

function elementToEditor(wire: WireElement): CanvasElement {
  const style = styleToEditor(wire.style);
  return {
    id: wire.id,
    type: wire.type,
    xMm: wire.x,
    yMm: wire.y,
    widthMm: wire.width,
    heightMm: wire.height,
    ...(wire.z_index != null ? { zIndex: wire.z_index } : {}),
    ...(wire.content != null ? { content: wire.content } : {}),
    ...(wire.binding_path != null ? { bindingPath: wire.binding_path as CanvasElement['bindingPath'] } : {}),
    ...(wire.label != null ? { label: wire.label } : {}),
    ...(wire.asset_id != null ? { assetId: wire.asset_id } : {}),
    ...(style ? { style } : {}),
    ...(wire.symbology != null ? { symbology: wire.symbology } : {}),
    ...(wire.show_value != null ? { showValue: wire.show_value } : {}),
    ...(wire.image_fit != null ? { imageFit: wire.image_fit } : {}),
    ...(wire.columns != null ? { columns: wire.columns.map(columnToEditor) } : {}),
    ...(wire.row_options != null
      ? {
          rowOptions: {
            ...(wire.row_options.description_under_item != null
              ? { descriptionUnderItem: wire.row_options.description_under_item }
              : {}),
            ...(wire.row_options.zebra != null ? { zebra: wire.row_options.zebra } : {}),
            ...(wire.row_options.repeat_header != null
              ? { repeatHeader: wire.row_options.repeat_header }
              : {}),
            ...(wire.row_options.blank_rows != null ? { blankRows: wire.row_options.blank_rows } : {}),
          },
        }
      : {}),
    ...(wire.totals_rows != null ? { totalsRows: wire.totals_rows as TotalsRow[] } : {}),
    ...(wire.tax_grouping != null ? { taxGrouping: wire.tax_grouping } : {}),
    ...(wire.show_cess != null ? { showCess: wire.show_cess } : {}),
  };
}

function sectionToEditor(wire: WireSection): CanvasSection {
  return {
    id: wire.id,
    type: wire.type,
    ...(wire.title != null ? { title: wire.title } : {}),
    xMm: wire.x,
    yMm: wire.y,
    widthMm: wire.width,
    heightMm: wire.height,
    ...(wire.component_code != null ? { componentCode: wire.component_code } : {}),
    ...(wire.free_placement != null ? { freePlacement: wire.free_placement } : {}),
    elements: (wire.elements ?? []).map(elementToEditor),
  };
}

/** The template row's paper, which the layout no longer restates. */
export type PaperRow = {
  paper_size: string;
  page_orientation: string;
  page_width_mm?: string | null;
  page_height_mm?: string | null;
};

function pageToEditor(wire: WireCanvas['page'], row: PaperRow): CanvasPage {
  // `page_width_mm` is a `DECIMAL(19,4)` and therefore a *string* on the wire — never
  // parsed into a float anywhere a total could be computed from it, but page setup is
  // display geometry and the editor lays out in numbers (docs/invoice-design.md §4.2).
  const width = row.page_width_mm != null ? Number(row.page_width_mm) : undefined;
  const height = row.page_height_mm != null ? Number(row.page_height_mm) : undefined;
  return {
    size: row.paper_size as CanvasPage['size'],
    orientation: row.page_orientation as CanvasPage['orientation'],
    ...(width != null && Number.isFinite(width) ? { widthMm: width } : {}),
    ...(height != null && Number.isFinite(height) ? { heightMm: height } : {}),
    margins: marginsToEditor(wire?.margins),
    gridSnap: wire?.grid_snap ?? true,
    gridStepMm: wire?.grid_step_mm ?? 5,
  };
}

/**
 * A stored layout as the editor manipulates it.
 *
 * Only `1.1.0` is editable. A stored `1.0.0` version is still *readable* — it prints, and its
 * history is intact — but it cannot express a column set, a totals block or a zone box, so the
 * editor would have to invent geometry for it and then save that invention back as if the
 * author had chosen it. Callers surface it as read-only and offer an upgrade instead.
 */
export function layoutToEditor(wire: Wire['CanvasV11'], row: PaperRow): CanvasDefinition {
  return {
    schemaVersion: SCHEMA_VERSION,
    page: pageToEditor(wire.page, row),
    theme: themeToEditor(wire.theme),
    print: printToEditor(wire.print_options),
    sections: (wire.sections ?? []).map(sectionToEditor),
  };
}

export function isEditableLayout(
  layout: Wire['CanvasV10'] | Wire['CanvasV11'],
): layout is Wire['CanvasV11'] {
  return layout.schema_version === SCHEMA_VERSION;
}

/* ------------------------------------------------------------------ editor → service */

function styleToWire(style: ElementStyle | undefined): WireStyle | undefined {
  if (!style) return undefined;
  const wire: WireStyle = {};
  if (style.fontSizePt !== undefined) wire.font_size_pt = style.fontSizePt;
  if (style.fontWeight !== undefined) wire.font_weight = style.fontWeight;
  if (style.fontStyle !== undefined) wire.font_style = style.fontStyle;
  if (style.color !== undefined) wire.color = style.color;
  if (style.backgroundColor !== undefined) wire.background_color = style.backgroundColor;
  if (style.textAlign !== undefined) wire.text_align = style.textAlign;
  if (style.verticalAlign !== undefined) wire.vertical_align = style.verticalAlign;
  if (style.borderWidthMm !== undefined) wire.border_width_mm = style.borderWidthMm;
  if (style.borderStyle !== undefined) wire.border_style = style.borderStyle;
  if (style.borderColor !== undefined) wire.border_color = style.borderColor;
  if (style.paddingMm !== undefined) wire.padding_mm = style.paddingMm;
  if (style.opacity !== undefined) wire.opacity = style.opacity;
  if (style.lineHeight !== undefined) wire.line_height = style.lineHeight;
  if (style.uppercase !== undefined) wire.uppercase = style.uppercase;
  return Object.keys(wire).length ? wire : undefined;
}

function elementToWire(element: CanvasElement): WireElement {
  const style = styleToWire(element.style);
  return {
    id: element.id,
    type: element.type,
    x: element.xMm,
    y: element.yMm,
    width: element.widthMm,
    height: element.heightMm,
    ...(element.zIndex !== undefined ? { z_index: element.zIndex } : {}),
    ...(element.content !== undefined ? { content: element.content } : {}),
    ...(element.bindingPath !== undefined ? { binding_path: element.bindingPath } : {}),
    ...(element.label !== undefined ? { label: element.label } : {}),
    ...(element.assetId !== undefined ? { asset_id: element.assetId } : {}),
    ...(style ? { style } : {}),
    ...(element.symbology !== undefined ? { symbology: element.symbology } : {}),
    ...(element.showValue !== undefined ? { show_value: element.showValue } : {}),
    ...(element.imageFit !== undefined ? { image_fit: element.imageFit } : {}),
    ...(element.columns !== undefined
      ? {
          columns: element.columns.map((column) => ({
            key: column.key,
            ...(column.label !== undefined ? { label: column.label } : {}),
            width_mm: column.widthMm,
            ...(column.align !== undefined ? { align: column.align } : {}),
            show: column.show,
          })),
        }
      : {}),
    ...(element.rowOptions !== undefined
      ? {
          row_options: {
            ...(element.rowOptions.descriptionUnderItem !== undefined
              ? { description_under_item: element.rowOptions.descriptionUnderItem }
              : {}),
            ...(element.rowOptions.zebra !== undefined ? { zebra: element.rowOptions.zebra } : {}),
            ...(element.rowOptions.repeatHeader !== undefined
              ? { repeat_header: element.rowOptions.repeatHeader }
              : {}),
            ...(element.rowOptions.blankRows !== undefined
              ? { blank_rows: element.rowOptions.blankRows }
              : {}),
          },
        }
      : {}),
    ...(element.totalsRows !== undefined ? { totals_rows: element.totalsRows } : {}),
    ...(element.taxGrouping !== undefined ? { tax_grouping: element.taxGrouping } : {}),
    ...(element.showCess !== undefined ? { show_cess: element.showCess } : {}),
  };
}

function sectionToWire(section: CanvasSection): WireSection {
  return {
    id: section.id,
    type: section.type,
    ...(section.title !== undefined ? { title: section.title } : {}),
    x: section.xMm,
    y: section.yMm,
    width: section.widthMm,
    height: section.heightMm,
    ...(section.componentCode !== undefined ? { component_code: section.componentCode } : {}),
    ...(section.freePlacement !== undefined ? { free_placement: section.freePlacement } : {}),
    elements: section.elements.map(elementToWire),
  };
}

/**
 * The layout as the service stores it.
 *
 * Paper size and orientation are **not** sent: they are the row's, and a template whose paper
 * changed is a `PUT /templates/{id}`, not a new version. Sending them here would recreate the
 * two-sources-of-truth problem 1.1.0 exists to remove.
 */
export function layoutToWire(layout: CanvasDefinition): WireCanvas {
  return {
    schema_version: SCHEMA_VERSION,
    page: {
      margins: {
        top: layout.page.margins.top,
        right: layout.page.margins.right,
        bottom: layout.page.margins.bottom,
        left: layout.page.margins.left,
        unit: layout.page.margins.unit,
      },
      grid_snap: layout.page.gridSnap,
      grid_step_mm: layout.page.gridStepMm,
    },
    theme: {
      primary_color: layout.theme.primaryColor,
      ...(layout.theme.secondaryColor !== undefined
        ? { secondary_color: layout.theme.secondaryColor }
        : {}),
      font_family: layout.theme.fontFamily,
      font_size_pt: layout.theme.fontSizePt,
    },
    print_options: {
      copies: layout.print.copies,
      ...(layout.print.copyMarkPosition !== undefined
        ? { copy_mark_position: layout.print.copyMarkPosition }
        : {}),
      ...(layout.print.prePrintedStationery !== undefined
        ? { pre_printed_stationery: layout.print.prePrintedStationery }
        : {}),
    },
    sections: layout.sections.map(sectionToWire),
  };
}

/* ------------------------------------------------------------------ template */

export function versionToEditor(wire: Wire['VersionItem']): TemplateVersionSummary {
  return {
    id: wire.id,
    versionNumber: wire.version_number,
    ...(wire.change_summary != null ? { changeSummary: wire.change_summary } : {}),
    createdAt: wire.created_at,
    ...(wire.published_at != null ? { publishedAt: wire.published_at } : {}),
  };
}

/**
 * A template as the gallery and the editor want it.
 *
 * `versions` and `layout` arrive from their own requests, so they are arguments rather than
 * something this reaches for: a gallery card needs neither, and making the row carry an empty
 * layout would have every card pretend it knows one.
 */
export function templateToEditor(
  wire: Wire['TemplateDetail'] | Wire['TemplateItem'],
  layout: CanvasDefinition,
  versions: TemplateVersionSummary[] = [],
): DesignTemplate {
  const description = 'description' in wire ? wire.description : null;
  return {
    id: wire.id,
    code: wire.code,
    name: wire.name,
    ...(description ? { description } : {}),
    status: wire.status as TemplateStatus,
    isSystem: wire.is_system,
    liveVersionId: wire.current_version_id ?? null,
    versions,
    layout,
    ...(wire.voucher_kind ? { voucherKind: wire.voucher_kind } : {}),
    ...(wire.line_profile && ['ITEMS', 'ACCOUNTS', 'MIXED'].includes(wire.line_profile)
      ? { lineProfile: wire.line_profile as LineProfile }
      : {}),
  };
}

/** The paper facts off any template row — list projection or detail, both carry them. */
export function paperOf(row: PaperRow): PaperRow {
  return {
    paper_size: row.paper_size,
    page_orientation: row.page_orientation,
    page_width_mm: row.page_width_mm ?? null,
    page_height_mm: row.page_height_mm ?? null,
  };
}

/**
 * A layout with nothing in it, on this template's paper.
 *
 * What a draft created without a canvas opens on, and what a gallery card draws its thumbnail
 * from: the list projection deliberately carries no layout tree — one per card would be a page
 * of trees fetched to draw four thumbnails — so a card knows the page shape and nothing more.
 */
export function emptyLayout(paper: PaperRow): CanvasDefinition {
  return layoutToEditor({ schema_version: SCHEMA_VERSION }, paper);
}
