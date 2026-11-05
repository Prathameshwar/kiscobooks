'use client';

import { type ReactNode, useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';
import {
  type CanvasCursor,
  DesignCanvas,
  ConfirmDialog,
  type Guide,
  GuideLayer,
  type Handle,
  SelectionLayer,
  type TransformGesture,
  ZoomControl,
  alignmentGuides,
  clampZoom,
  fitZoom,
  formatMm,
  moveRect,
  pageGeometry,
  resizeRect,
  roundMm,
  zoomIn,
  zoomOut,
} from '@janso/ui';
import Link from 'next/link';
import { ArrangePanel, type ArrangeHandlers } from './ArrangePanel';
import { VersionPanel } from './VersionPanel';
import { DRAG_ELEMENT, DRAG_FIELD, FieldPalette } from './FieldPalette';
import { templatePurpose } from './TemplateGallery';
import { useUnsavedChanges } from '../../lib/use-unsaved-changes';
import { WarningsPanel } from './WarningsPanel';
import { ColumnHandles } from './ColumnHandles';
import { DocumentLayer, type ValueMode } from './DocumentLayer';
import { assetSourceOf, useDesignAssets } from '../../lib/design-assets';
import { ElementTree } from './ElementTree';
import { InlineTextEditor } from './InlineTextEditor';
import { type InspectorHandlers, SelectionInspector } from './SelectionInspector';
import {
  type BindingPath,
  COPY_LABELS,
  type CanvasDefinition,
  type CopyLabel,
  type DesignTemplate,
  isLineTable,
} from './layout-model';
import {
  addColumn,
  addCopy,
  addTotalsRow,
  availableCopies,
  boundPaths,
  moveCopy,
  type AddableKind,
  ADDABLE_ELEMENTS,
  placeElement,
  placeField,
  type ZonePoint,
  removeCopy,
  distributeColumns,
  moveColumn,
  moveTotalsRow,
  removeColumn,
  removeTotalsRow,
  drawnPageHeightMm,
  resizeColumnBoundary,
  setElementStyle,
  setMargins,
  setPage,
  setPrint,
  setTheme,
  updateColumn,
  updateElement,
  updateSection,
} from './layout-edit';
import {
  type History,
  canRedo,
  canUndo,
  createHistory,
  record,
  redo,
  redoLabel,
  undo,
  undoLabel,
} from './history';
import {
  alignElements,
  deleteElements,
  depthOf,
  distributeElements,
  duplicateElements,
  moveSelection,
  reorderElements,
  selectionBounds,
} from './layout-arrange';
import { type KnownAssetIds, checkLayout } from './layout-warnings';
import { type PrintManifest, imageProblems, printProblems } from './print-capabilities';
import {
  type Publication,
  canPublish,
  nextVersionNumber,
  publicationOf,
  publish,
  snapshotOf,
} from './publication';
import { PRESETS, type PresetId, activePreset, applyPreset } from './presets';
import { navigate, targetById, targetsInRect, targetsOf } from './selection';

/**
 * The designer's frame, and the only place that owns state.
 *
 * It owns four things, each because more than one view reads it: the **layout history**
 * (the inspector and the canvas both change it, and undo has to see every change), the
 * **selection** (canvas and tree are two views of one), **zoom**, and the **gesture in
 * progress** (the drag reports deltas; the guides and the status bar read them).
 *
 * Edits funnel through one `edit()` that applies a pure change and records it under a
 * label, so a burst of keystrokes is one undo and a drag is another.
 *
 * Nothing is persisted: the layout starts from the fixture and lives in memory for the
 * session (`docs/invoice-design-ui-todo.md`).
 */

/**
 * How a publish reaches the outside world, if it does.
 *
 * A **port**, and optional on purpose. Without it the editor behaves exactly as it did against
 * the fixtures: it publishes into local state, and the footer says plainly that nothing is
 * saved. With it, publishing appends an immutable version to the `design` service and makes it
 * live. Keeping it optional is what let eight phases of editor behaviour — and their suites —
 * stay untouched while the data source changed underneath them.
 *
 * `saveDraft` is separate from `publish` because the service separates them: a draft version is
 * appended without becoming what documents print on. The editor had no such notion while it was
 * local, because there was nothing to save *to*.
 */
export type DesignerPersistence = {
  /** Append a version. Resolves to it, or `null` when the write did not complete. */
  saveDraft: (
    layout: CanvasDefinition,
    changeSummary: string,
  ) => Promise<{ id: string; versionNumber: number } | null>;
  /** Append a version and make it live. */
  publish: (
    layout: CanvasDefinition,
    changeSummary: string,
  ) => Promise<{ id: string; versionNumber: number; publishedAt: string | null } | null>;
  pending: boolean;
  failure: string | null;
  /** A 5xx left the outcome unknown; retrying must repeat the identical request. */
  uncertain: boolean;
  /** Re-read the template, so the panel shows the service's history rather than a guess. */
  reload: () => void;
  /** Fetch one permitted published version on demand; absent means local snapshots only. */
  loadVersion?: (versionId: string) => Promise<CanvasDefinition>;
};

type DesignerShellProps = {
  templates: readonly DesignTemplate[];
  initialTemplateId: string;
  /** Absent means this session's edits stay in this session, and the footer says so. */
  persistence?: DesignerPersistence;
  /** Why this design cannot be written to, if it cannot — a shipped design, an old format. */
  readOnlyReason?: string;
  /** Where Back leads: the print templates, unless the designer was opened from elsewhere. */
  backHref?: string;
  /** What the printer of the kind this template prints for accepts, when a rule points at it. */
  printManifest?: PrintManifest;
  /** Absent in a company-less session (a fixture, a test): the asset picker and live preview of a real upload stay off. */
  company?: string;
  /** Where this design is used, and the control that assigns it (plan R4) — the route owns its data. */
  usage?: ReactNode;
  /**
   * Preview a saved version on a saved bill (plan R4). Absent: the control is not offered. Called
   * only with a version that holds exactly what is on the canvas; with unsaved edits the designer
   * asks for a save first, and continues here with the version that save made.
   */
  onPreviewWithBill?: (version: { id: string; versionNumber: number }) => void;
};

/** One empty list, so a memo keyed on the asset list does not see a new `[]` every render. */
const NO_ASSETS: readonly never[] = [];

/** Moving and resizing with the keyboard: alt is the transform modifier. */
const NUDGE_KEYS: Record<string, { dxMm: number; dyMm: number }> = {
  ArrowLeft: { dxMm: -1, dyMm: 0 },
  ArrowRight: { dxMm: 1, dyMm: 0 },
  ArrowUp: { dxMm: 0, dyMm: -1 },
  ArrowDown: { dxMm: 0, dyMm: 1 },
};

/** Input types that own the keyboard while focused. */
const TEXT_ENTRY_TYPES = new Set(['text', 'search', 'url', 'tel', 'email', 'password', 'number']);

type Rect = { xMm: number; yMm: number; widthMm: number; heightMm: number };

export function DesignerShell({
  templates,
  initialTemplateId,
  persistence,
  readOnlyReason,
  backHref = '/invoice-designer',
  printManifest,
  company,
  usage,
  onPreviewWithBill,
}: DesignerShellProps) {
  // Withdrawn assets too, so a picture withdrawn since it was placed can be named as such.
  const assets = useDesignAssets(company, { includeInactive: true });
  const assetItems = assets.items.length > 0 ? assets.items : NO_ASSETS;
  const assetSource = useMemo(() => assetSourceOf(assets.items), [assets.items]);
  const [leaving, setLeaving] = useState(false);
  /** Set the moment a confirmed leave starts, so the page's own unload warning stands down. */
  const left = useRef(false);
  const [templateId, setTemplateId] = useState(initialTemplateId);
  const [restorePending, setRestorePending] = useState(false);
  const [restoreFailure, setRestoreFailure] = useState<string | null>(null);
  const restoreLock = useRef(false);
  /** Edit history per template. A template absent from here is still its fixture. */
  const [histories, setHistories] = useState<Record<string, History<CanvasDefinition>>>({});
  const [editCount, setEditCount] = useState(0);
  const [zoom, setZoom] = useState(1);
  const [panel, setPanel] = useState<'palette' | 'properties' | null>(null);
  const panelId = useId();
  const panelTrigger = useRef<HTMLButtonElement | null>(null);
  function closePanel() { setPanel(null); panelTrigger.current?.focus(); }
  const [cursor, setCursor] = useState<CanvasCursor | null>(null);
  const [copy, setCopy] = useState<CopyLabel | null>(null);
  /**
   * The selection is a set, with the **last entry active**: the one the keyboard acts on,
   * the one the handles attach to, the one a drag is anchored on. A single `selectedId`
   * plus a list would be two sources of truth for the same thing.
   */
  const [selectedIds, setSelectedIds] = useState<readonly string[]>([]);
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [guides, setGuides] = useState<readonly Guide[]>([]);
  const [editingText, setEditingText] = useState<string | null>(null);
  /** Sample values or the bindings behind them. A view, so it is not part of the layout. */
  const [valueMode, setValueMode] = useState<ValueMode>('resolved');
  /** Publication state per template: what is live, the history, and this session's snapshots. */
  const [publications, setPublications] = useState<Record<string, Publication>>({});
  /** History depth at each template's last publish, so the panel can count what is pending. */
  const [baseline, setBaseline] = useState<Record<string, number>>({});
  /**
   * Which act the version dialog is confirming. One dialog, two outcomes: it asks for the same
   * `change_summary` either way, and a second dialog to type the same sentence into is how one
   * of them ends up empty. An explicit intent is what stops "Save draft" confirming a publish.
   */
  const [intent, setIntent] = useState<'publish' | 'draft'>('publish');
  const [publishOpen, setPublishOpen] = useState(false);
  const [summary, setSummary] = useState('');
  const [publishError, setPublishError] = useState<string | null>(null);
  /** "Save this design first?", asked before a preview of a canvas no saved version holds. */
  const [saveFirst, setSaveFirst] = useState(false);
  /** A draft saved from that question continues straight on to the preview of what it saved. */
  const previewAfterSave = useRef(false);
  const stageRef = useRef<HTMLDivElement | null>(null);
  /** The rectangle a drag started from, so every move is measured from one origin. */
  const gestureOrigin = useRef<{ id: string; rect: Rect } | null>(null);

  const template = useMemo(
    () => templates.find((candidate) => candidate.id === templateId) ?? templates[0],
    [templates, templateId],
  );

  const history = template ? histories[template.id] : undefined;
  const layout = history?.present.state ?? template?.layout;

  const page = useMemo(
    () =>
      layout
        ? /* A roll's drawn length follows its content: see `drawnPageHeightMm`. The model
           * keeps the nominal height, which is what the stock actually is. */
          { ...pageGeometry(layout.page), heightMm: drawnPageHeightMm(layout) }
        : null,
    [layout],
  );

  const targets = useMemo(() => (layout ? targetsOf(layout) : []), [layout]);
  const selectedId = selectedIds.at(-1) ?? null;
  const selection = targetById(targets, selectedId);
  /** The selected *elements*. A zone is never arranged, so it never counts here. */
  const chosenElementIds = useMemo(
    () =>
      selectedIds.filter(
        (id) => targetById(targets, id)?.kind === 'element',
      ),
    [selectedIds, targets],
  );

  /** Replace the selection, or add to it. `null` means "nothing". */
  const select = useCallback((id: string | null, intent?: { additive?: boolean }) => {
    setEditingText(null);
    setSelectedIds((current) => {
      if (!id) return [];
      if (!intent?.additive) return [id];
      // Clicking a member again removes it, which is how every multi-select works and the
      // only way to correct a mis-shift-click without starting over.
      return current.includes(id)
        ? current.filter((entry) => entry !== id)
        : [...current, id];
    });
  }, []);

  // An id that the switched-to template, an undo, or a delete no longer contains must not
  // stay selected: everything downstream reads the selection as live geometry.
  useEffect(() => {
    setSelectedIds((current) => {
      const live = current.filter((id) => targets.some((target) => target.id === id));
      return live.length === current.length ? current : live;
    });
  }, [targets]);

  const copies = layout?.print.copies ?? [];
  // A copy the switched-to template does not print must not stay selected.
  useEffect(() => {
    setCopy((current) => (current && copies.includes(current) ? current : null));
  }, [copies]);

  /**
   * Every edit funnels through here.
   *
   * The label is what makes undo usable: consecutive changes with the same label inside a
   * short window collapse into one entry, so typing a heading is one undo rather than
   * eleven, while typing then dragging then typing is three.
   *
   * It reports whether the change was applied, because some callers have a second half: a
   * duplicate selects its copies, a delete clears the selection. Those must not happen when
   * the edit itself did not.
   */
  const edit = useCallback(
    (
      change: (current: CanvasDefinition) => CanvasDefinition,
      label: string,
      /**
       * `discrete` marks a whole action — a button, a shortcut — so it never merges with
       * the press before it. Leave it off for continuous input, where merging is the
       * point: typing a heading is one undo, dragging an element is another.
       */
      options: { discrete?: boolean } = {},
    ): boolean => {
      if (!template || !layout) return false;
      // Read-only is enforced here, not only on the controls that offer it. Disabling an
      // input stops the inspector; it does not stop alt+arrow, a drag, or anything added
      // later — and "copy it to change it" has to hold for every route into the layout.
      if (template.isSystem || (restoreLock.current && !label.startsWith('restore:'))) return false;
      const next = change(layout);
      if (next === layout) return false;
      setHistories((current) => {
        const existing = current[template.id] ?? createHistory(template.layout, 0);
        return {
          ...current,
          [template.id]: record(existing, next, label, Date.now(), {
            coalesce: !options.discrete,
          }),
        };
      });
      setEditCount((count) => count + 1);
      return true;
    },
    [layout, template],
  );

  const handlers: InspectorHandlers = useMemo(
    () => ({
      onPage: (patch) => edit((current) => setPage(current, patch), 'page'),
      onMargins: (patch) => edit((current) => setMargins(current, patch), 'margins'),
      onTheme: (patch) => edit((current) => setTheme(current, patch), 'theme'),
      onPrint: (patch) => edit((current) => setPrint(current, patch), 'print'),
      onSection: (id, patch) => edit((current) => updateSection(current, id, patch), `zone:${id}`),
      onElement: (id, patch) =>
        edit((current) => updateElement(current, id, patch), `element:${id}`),
      onStyle: (id, patch) => edit((current) => setElementStyle(current, id, patch), `style:${id}`),
      onColumn: (id, key, patch) =>
        edit((current) => updateColumn(current, id, key, patch), `column:${id}:${key}`),
      // Everything below is a button: one press, one undo. Only the rows above coalesce,
      // because only they carry typing.
      onAddColumn: (id, key) =>
        edit((current) => addColumn(current, id, key), 'column:add', { discrete: true }),
      onRemoveColumn: (id, key) =>
        edit((current) => removeColumn(current, id, key), 'column:remove', { discrete: true }),
      onMoveColumn: (id, key, direction) =>
        edit((current) => moveColumn(current, id, key, direction), 'column:move', {
          discrete: true,
        }),
      onDistribute: (id) =>
        edit((current) => distributeColumns(current, id), 'column:fit', { discrete: true }),
      onAddTotalsRow: (id, row) =>
        edit((current) => addTotalsRow(current, id, row), 'totals:add', { discrete: true }),
      onRemoveTotalsRow: (id, row) =>
        edit((current) => removeTotalsRow(current, id, row), 'totals:remove', { discrete: true }),
      onMoveTotalsRow: (id, row, direction) =>
        edit((current) => moveTotalsRow(current, id, row, direction), 'totals:move', {
          discrete: true,
        }),
      onAddCopy: (copy) => edit((current) => addCopy(current, copy), 'copy:add', { discrete: true }),
      onRemoveCopy: (copy) =>
        edit((current) => removeCopy(current, copy), 'copy:remove', { discrete: true }),
      onMoveCopy: (copy, direction) =>
        edit((current) => moveCopy(current, copy, direction), 'copy:move', { discrete: true }),
    }),
    [edit],
  );

  /**
   * Align, distribute, restack, duplicate and delete, over the selected elements.
   *
   * Every one of these is `discrete`: they are buttons and shortcuts, and a designer walks
   * an element up a stack or stamps out copies by pressing the same one repeatedly. Each
   * press is a step they can take back on its own.
   */
  const arrange: ArrangeHandlers = useMemo(
    () => ({
      onAlign: (edge) =>
        edit((current) => alignElements(current, chosenElementIds, edge), `align:${edge}`, {
          discrete: true,
        }),
      onDistribute: (axis) =>
        edit(
          (current) => distributeElements(current, chosenElementIds, axis),
          `distribute:${axis}`,
          { discrete: true },
        ),
      onReorder: (order) =>
        edit((current) => reorderElements(current, chosenElementIds, order), `stack:${order}`, {
          discrete: true,
        }),
      onDuplicate: () => {
        if (!layout) return;
        const copied = duplicateElements(layout, chosenElementIds);
        if (copied.ids.length === 0) return;
        // The copies become the selection, so the next drag moves them and not the
        // originals they are sitting on top of — but only if the copy actually happened.
        if (edit(() => copied.layout, 'duplicate', { discrete: true })) {
          setSelectedIds(copied.ids);
        }
      },
      onDelete: () => {
        if (
          edit((current) => deleteElements(current, chosenElementIds), 'delete', {
            discrete: true,
          })
        ) {
          setSelectedIds([]);
        }
      },
    }),
    [chosenElementIds, edit, layout],
  );

  /**
   * Where a palette click puts a field: the selected zone, or the zone of the selected
   * element, and the page's first zone when nothing is selected — so the palette is never a
   * column of disabled rows waiting for a selection nobody knew to make. A zone is always
   * the destination — an element cannot contain another one.
   */
  const destination = useMemo(() => {
    const id = selection?.zoneId ?? (selection?.kind === 'zone' ? selection.id : null);
    const zone = targetById(targets, id);
    const fallback = zone ?? targets.find((target) => target.kind === 'zone');
    return fallback ? { id: fallback.id, label: fallback.label } : null;
  }, [selection, targets]);

  /**
   * Add a field or an object, then select it. Selected on arrival: a clicked one lands below
   * whatever was already in the zone, which may be the bottom edge, and the first thing
   * anyone does is move it.
   */
  const insert = useCallback(
    (what: { field: string } | { kind: AddableKind }, zoneId?: string, at?: ZonePoint) => {
      const zone = zoneId ?? destination?.id;
      if (!layout || !zone) return;
      const options = at ? { at } : {};
      const result =
        'field' in what
          ? placeField(layout, zone, what.field as BindingPath, options)
          : placeElement(layout, zone, what.kind, options);
      if (!result.id) return;
      const label = 'field' in what ? 'place-field' : 'place-element';
      if (edit(() => result.layout, label, { discrete: true })) {
        setSelectedIds([result.id]);
      }
    },
    [destination, edit, layout],
  );
  const place = useCallback((path: string) => insert({ field: path }), [insert]);

  /** A palette row let go over the page: into the zone under the pointer, at that point. */
  const drop = useCallback(
    (point: ZonePoint, data: DataTransfer) => {
      const field = data.getData(DRAG_FIELD);
      const kind = data.getData(DRAG_ELEMENT);
      const what = field
        ? { field }
        : kind in ADDABLE_ELEMENTS
          ? { kind: kind as AddableKind }
          : null;
      if (!what) return;
      // Where zones overlap, the one drawn last — on top — is the one under the pointer.
      const zone = [...targets]
        .reverse()
        .find(
          (target) =>
            target.kind === 'zone' &&
            point.xMm >= target.rect.xMm &&
            point.xMm <= target.rect.xMm + target.rect.widthMm &&
            point.yMm >= target.rect.yMm &&
            point.yMm <= target.rect.yMm + target.rect.heightMm,
        );
      // Outside every zone it still lands somewhere visible: below the rest of the destination.
      if (!zone) {
        insert(what);
        return;
      }
      insert(what, zone.id, { xMm: point.xMm - zone.rect.xMm, yMm: point.yMm - zone.rect.yMm });
    },
    [insert, targets],
  );

  /** Everything wrong with the page, recomputed only when the layout actually changes. */
  // A layout routed to a kind is also checked against what that kind can print: publishing one
  // its printer refuses would break printing for every voucher routed to it.
  //
  // Pictures are judged against the company's own asset list once it has been read: `undefined`
  // in a fixture session (its pictures are the sample ones), `null` while a company's list is
  // unknown, so no picture is called missing on a read that has not answered.
  const knownAssets = useMemo<KnownAssetIds>(
    () =>
      !company ? undefined : assets.failure || (assets.loading && assetItems.length === 0) ? null : new Set(assetItems.map((asset) => asset.id)),
    [assetItems, assets.failure, assets.loading, company],
  );
  const warnings = useMemo(() => {
    if (!layout) return [];
    const printing = printManifest
      ? [...printProblems(layout, printManifest), ...imageProblems(layout, printManifest, assetItems)]
      : [];
    // An image without a picture is the printer's error; the same frame as a layout warning
    // would say it twice.
    const refused = new Set(printing.map((problem) => problem.targetId));
    return [
      ...checkLayout(layout, knownAssets).filter((warning) => !(warning.code === 'asset-missing' && refused.has(warning.targetId))),
      ...printing,
    ];
  }, [assetItems, knownAssets, layout, printManifest]);

  /** Which paths are already printed, for the palette's marks. Scanned once per layout,
   *  not once per render: a drag re-renders on every pointer event. */
  const placed = useMemo(() => (layout ? boundPaths(layout) : new Set<string>()), [layout]);

  /* ------------------------------------------------------- versions and publishing */

  const publication = useMemo(
    () => (template ? (publications[template.id] ?? publicationOf(template)) : null),
    [publications, template],
  );

  /** The layout that is actually live — only for a version this session published. */
  const liveLayout =
    publication?.liveVersionId ? snapshotOf(publication, publication.liveVersionId) : null;

  /**
   * Whether publishing would carry anything.
   *
   * Compared by reference against the published snapshot, which is exact rather than
   * approximate: every edit returns a new tree and history keeps the actual objects, so
   * undoing back to the published state restores that very object and this correctly says
   * "nothing has changed" again. Counting edits could not do that — undo would leave the
   * tally positive while the layout was identical to what is live.
   */
  const depth = history?.past.length ?? 0;
  const dirty = liveLayout ? layout !== liveLayout : depth > 0;
  const pending = dirty ? Math.max(1, depth - (template ? (baseline[template.id] ?? 0) : 0)) : 0;
  /** Edits since the last save or publish — what leaving the designer would lose. */
  const unsaved = !!template && !template.isSystem && depth !== (baseline[template.id] ?? 0);
  useUnsavedChanges(useCallback(() => unsaved && !left.current, [unsaved]));
  const leave = useCallback(() => {
    left.current = true;
    window.location.assign(backHref);
  }, [backHref]);

  const verdict = useMemo(
    () =>
      !template
        ? ({ ok: false, reason: 'No template.' } as const)
        : readOnlyReason
          ? ({ ok: false, reason: readOnlyReason } as const)
          : persistence?.pending || restorePending
            ? ({ ok: false, reason: 'Saving…' } as const)
            : canPublish(template, warnings, dirty),
    [dirty, persistence?.pending, readOnlyReason, restorePending, template, warnings],
  );

  /** The one thing both save and publish need: a summary worth keeping. */
  const describedChange = useCallback((): string | null => {
    const changeSummary = summary.trim();
    if (!changeSummary) {
      // The dialog's own error channel, so it stays open with what was typed. A version
      // history of "Published from the editor" four times over is not a history.
      setPublishError('Say what changed — a version history is only worth keeping if each entry means something.');
      return null;
    }
    return changeSummary;
  }, [summary]);

  const confirmPublish = useCallback(async () => {
    if (!template || !layout || !publication || restoreLock.current) return;
    const changeSummary = describedChange();
    if (!changeSummary) return;

    if (persistence) {
      const version = await persistence.publish(layout, changeSummary);
      if (!version) {
        /*
         * Left open, holding what was typed: a closed dialog with an unsaved layout is how
         * work gets lost. Nothing is set here on purpose — the dialog renders
         * `persistence.failure`, which is live state. Copying it into `publishError` inside
         * this callback read the value captured when the callback was *created*, so the real
         * reason was replaced by the generic fallback. The test for an unconfirmed publish is
         * what caught it.
         */
        return;
      }
      // The service owns version numbers, ids and timestamps, so the panel is refreshed from
      // it rather than from a local guess at what it just did.
      persistence.reload();
      setBaseline((current) => ({ ...current, [template.id]: depth }));
      setPublishOpen(false);
      setSummary('');
      setPublishError(null);
      return;
    }

    setPublications((current) => ({
      ...current,
      [template.id]: publish(publication, template, layout, changeSummary, new Date()),
    }));
    setBaseline((current) => ({ ...current, [template.id]: depth }));
    setPublishOpen(false);
    setSummary('');
    setPublishError(null);
  }, [depth, describedChange, layout, persistence, publication, summary, template]);

  /**
   * Save without publishing — only meaningful when there is somewhere to save to.
   *
   * Reuses the publish dialog's summary field rather than inventing a second one: the service
   * wants a `change_summary` either way, and two places to type the same sentence is how one of
   * them ends up empty.
   */
  const saveDraft = useCallback(async () => {
    if (!template || !layout || !persistence || restoreLock.current) return;
    const changeSummary = describedChange();
    if (!changeSummary) return;

    const version = await persistence.saveDraft(layout, changeSummary);
    // As above: the dialog shows the live failure rather than a stale copy of it.
    if (!version) return;
    persistence.reload();
    setBaseline((current) => ({ ...current, [template.id]: depth }));
    setPublishOpen(false);
    setSummary('');
    setPublishError(null);
    if (previewAfterSave.current) {
      previewAfterSave.current = false;
      onPreviewWithBill?.({ id: version.id, versionNumber: version.versionNumber });
    }
  }, [depth, describedChange, layout, onPreviewWithBill, persistence, template]);

  /**
   * The newest saved version: what the canvas shows when nothing is unsaved, because the editor
   * opens on the newest version and every save appends one.
   */
  const newestVersion = useMemo(
    () => (template ? [...template.versions].sort((a, b) => b.versionNumber - a.versionNumber)[0] : undefined),
    [template],
  );
  /** A preview prints a *saved* version, so a canvas with unsaved edits is saved first. */
  const previewWithBill = useCallback(() => {
    if (!onPreviewWithBill) return;
    if (newestVersion && !unsaved) {
      onPreviewWithBill({ id: newestVersion.id, versionNumber: newestVersion.versionNumber });
      return;
    }
    setSaveFirst(true);
  }, [newestVersion, onPreviewWithBill, unsaved]);

  /** Load a published layout back into the editor, as one undoable edit. */
  const restore = useCallback(
    async (versionId: string) => {
      if (!publication || restoreLock.current || readOnlyReason || template?.isSystem) return;
      setRestoreFailure(null);
      restoreLock.current = true;
      setRestorePending(true);
      try {
        const snapshot = snapshotOf(publication, versionId) ?? await persistence?.loadVersion?.(versionId);
        if (snapshot) edit(() => snapshot, `restore:${versionId}`, { discrete: true });
      } catch {
        setRestoreFailure('This version could not be loaded. Your current layout is preserved. Try again.');
      } finally { restoreLock.current = false; setRestorePending(false); }
    },
    [edit, persistence, publication, readOnlyReason, restorePending, template],
  );

  const presetId = layout ? activePreset(layout) : null;

  const selectTemplate = useCallback((id: string) => {
    setTemplateId(id);
    setSelectedIds([]);
    setHoveredId(null);
    setEditingText(null);
  }, []);

  const fit = useCallback(() => {
    const stage = stageRef.current;
    if (!stage || !page) return;
    setZoom(fitZoom(page, { width: stage.clientWidth, height: stage.clientHeight }));
  }, [page]);

  const stepHistory = useCallback(
    (direction: 'undo' | 'redo') => {
      if (!template || restoreLock.current) return;
      setHistories((current) => {
        const existing = current[template.id];
        if (!existing) return current;
        const next = direction === 'undo' ? undo(existing) : redo(existing);
        return next === existing ? current : { ...current, [template.id]: next };
      });
    },
    [template],
  );

  /**
   * Move or resize the selected element, applying the layout's own rules: the grid when
   * snapping is on, the zone as bounds, and the nearest alignment as a final correction.
   * The gesture reports raw deltas, so this is the only place those rules live.
   */
  const transform = useCallback(
    (
      gesture: { handle: Handle | null; dxMm: number; dyMm: number },
      label: string,
      /**
       * `aim` is what separates a pointer from a key. A drag is approximate, so it snaps
       * to the grid and accepts the nearest alignment as a correction. A keyboard nudge is
       * exact: alt+arrow means *one millimetre*, and a 1mm correction that cancels a 1mm
       * nudge leaves the key looking broken. So the keyboard passes its own `snapMm` and
       * turns aiming off.
       */
      options: { aim?: boolean; snapMm?: number } = {},
    ) => {
      if (!layout || !selection?.element || selection.kind !== 'element') return;
      const alone = chosenElementIds.length <= 1;
      // Resizing a group is proportional scaling — a different feature, and the reason the
      // handles are hidden for one. The keyboard follows the pointer rather than quietly
      // resizing whichever member happens to be active.
      if (gesture.handle && !alone) return;
      const zone = selection.section;
      const element = selection.element;
      const base: Rect =
        gestureOrigin.current?.id === element.id
          ? gestureOrigin.current.rect
          : {
              xMm: element.xMm,
              yMm: element.yMm,
              widthMm: element.widthMm,
              heightMm: element.heightMm,
            };

      const aiming = options.aim ?? true;
      const snapMm =
        options.snapMm ?? (layout.page.gridSnap ? layout.page.gridStepMm : 0);
      const bounds = { widthMm: zone.widthMm, heightMm: zone.heightMm };

      let next = gesture.handle
        ? resizeRect(base, gesture.handle, gesture, { bounds, snapMm, minMm: 1 })
        : moveRect(base, gesture, { bounds, snapMm });

      if (aiming) {
        // Alignment is measured in page coordinates, because what a designer aligns to is
        // usually in another zone — a total under a column, a logo over an address. For a
        // group it is the anchor that aims: it is the one under the pointer, and the one
        // whose edges the designer is watching.
        //
        // **The whole selection is excluded, not just the anchor.** A group-mate travels
        // with the anchor, so the offset between them never changes and there is nothing
        // to aim at. Leave them in and two elements sharing a baseline cannot be dragged a
        // short distance at all: the correction pulls the anchor back onto the edge it is
        // carrying with it, the step rounds to nothing, and the page sits still.
        const travelling = new Set<string>([element.id, ...chosenElementIds]);
        const others = targets
          .filter((target) => target.kind === 'element' && !travelling.has(target.id))
          .map((target) => target.rect);
        const aim = alignmentGuides(
          {
            xMm: next.xMm + zone.xMm,
            yMm: next.yMm + zone.yMm,
            widthMm: next.widthMm,
            heightMm: next.heightMm,
          },
          others,
          1,
        );
        // Only a move is corrected: nudging a resized edge onto someone else's edge would
        // fight the handle the designer is holding.
        if (!gesture.handle && (aim.snapDxMm !== 0 || aim.snapDyMm !== 0)) {
          next = moveRect(next, { dxMm: aim.snapDxMm, dyMm: aim.snapDyMm }, { bounds, snapMm: 0 });
        }
        setGuides(aim.guides);
      }

      if (alone) {
        edit(
          (current) =>
            updateElement(current, element.id, {
              xMm: next.xMm,
              yMm: next.yMm,
              widthMm: next.widthMm,
              heightMm: next.heightMm,
            }),
          label,
        );
        return;
      }

      /*
       * A group moves by the step the *anchor* just achieved — the element under the
       * pointer, whose snapping and alignment the designer is watching. The step is taken
       * from the anchor's current position rather than from the gesture's origin, so the
       * model can reduce it for the whole group (`moveSelection`) without that reduction
       * compounding: the next event recomputes the anchor's absolute target afresh.
       */
      const step = {
        dxMm: roundMm(next.xMm - element.xMm),
        dyMm: roundMm(next.yMm - element.yMm),
      };
      if (step.dxMm === 0 && step.dyMm === 0) return;
      edit(
        (current) => moveSelection(current, chosenElementIds, step, { anchorId: element.id }),
        label,
      );
    },
    [chosenElementIds, edit, layout, selection, targets],
  );

  const onTransform = useCallback(
    (gesture: TransformGesture) => {
      if (gesture.phase === 'end') {
        gestureOrigin.current = null;
        setGuides([]);
        return;
      }
      if (!selection?.element) return;
      // Pinned on `start`, so every later event measures from the same rectangle and a
      // gesture whose pointerup went missing cannot leave a stale origin behind.
      if (gesture.phase === 'start') {
        gestureOrigin.current = {
          id: gesture.id,
          rect: {
            xMm: selection.element.xMm,
            yMm: selection.element.yMm,
            widthMm: selection.element.widthMm,
            heightMm: selection.element.heightMm,
          },
        };
      }
      transform(gesture, `${gesture.handle ? 'resize' : 'move'}:${gesture.id}`);
    },
    [selection, transform],
  );

  /*
   * Window-level keys. Zoom and history are `ctrl`/`cmd`; the transform modifier is `alt`,
   * so the plain arrows stay with the canvas's own selection movement and nothing is modal.
   *
   * **While you are in a text field, the keyboard belongs to the field.** Undo and the
   * nudges step aside: `ctrl+Z` half way through typing a margin means "take that word
   * back", not "take the last layout change back", and alt+arrow must not move an element
   * out from under someone editing its label. Zoom has no such conflict and stays global.
   */
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      const node = event.target as HTMLElement | null;
      // A radio, a checkbox or a switch is an input but not a text field: pressing ctrl+Z
      // after flipping one means "undo that", so only text entry takes the keys away.
      const typing =
        (node instanceof HTMLInputElement && TEXT_ENTRY_TYPES.has(node.type)) ||
        node instanceof HTMLTextAreaElement ||
        node?.isContentEditable === true;
      const meta = event.ctrlKey || event.metaKey;
      if (meta && !event.altKey) {
        const key = event.key.toLowerCase();
        if (key === 'z' && !event.shiftKey) {
          if (typing) return;
          event.preventDefault();
          stepHistory('undo');
          return;
        }
        if ((key === 'z' && event.shiftKey) || key === 'y') {
          if (typing) return;
          event.preventDefault();
          stepHistory('redo');
          return;
        }
        if (event.key === '+' || event.key === '=') {
          event.preventDefault();
          setZoom((current) => zoomIn(current));
          return;
        }
        if (event.key === '-') {
          event.preventDefault();
          setZoom((current) => zoomOut(current));
          return;
        }
        if (event.key === '0') {
          event.preventDefault();
          setZoom(1);
          return;
        }
        if (event.key === '9') {
          event.preventDefault();
          fit();
          return;
        }
        if (key === 'a' && !typing) {
          event.preventDefault();
          // Everything in the zone you are working in, not everything on the page: a
          // designer pressing ctrl+A in the footer means the footer. With nothing
          // selected there is no such context, so it means the whole page.
          const zoneId = selection?.zoneId ?? selection?.id ?? null;
          setSelectedIds(
            targets
              .filter(
                (target) => target.kind === 'element' && (!zoneId || target.zoneId === zoneId),
              )
              .map((target) => target.id),
          );
          return;
        }
        if (key === 'd' && !typing) {
          event.preventDefault();
          arrange.onDuplicate();
          return;
        }
        if ((event.key === ']' || event.key === '[') && !typing) {
          event.preventDefault();
          const forwards = event.key === ']';
          arrange.onReorder(
            event.shiftKey ? (forwards ? 'front' : 'back') : forwards ? 'forward' : 'backward',
          );
          return;
        }
      }

      if ((event.key === 'Delete' || event.key === 'Backspace') && !typing && !meta) {
        if (chosenElementIds.length === 0) return;
        event.preventDefault();
        arrange.onDelete();
        return;
      }

      const nudge = NUDGE_KEYS[event.key];
      if (!nudge || !event.altKey || typing) return;
      event.preventDefault();
      // Two steps, and they mean different things. Shift is coarse — a grid step, landing
      // on a grid line — and plain alt is one exact millimetre, off-grid if that is where
      // the element already was. A fine nudge that silently snapped back to the grid would
      // be a key that does nothing, which is how a designer stops trusting the keyboard.
      const grid = layout?.page.gridStepMm ?? 5;
      const coarse = event.shiftKey;
      const step = coarse ? grid : 1;
      const snapMm = coarse && layout?.page.gridSnap ? grid : 0;
      const delta = { dxMm: nudge.dxMm * step, dyMm: nudge.dyMm * step };
      if (meta) {
        // alt+ctrl grows or shrinks from the bottom-right, the handle a mouse reaches for.
        transform({ handle: 'se', ...delta }, `resize:${selectedId}`, { aim: false, snapMm });
      } else {
        transform({ handle: null, ...delta }, `move:${selectedId}`, { aim: false, snapMm });
      }
      // A keyboard transform is a discrete act, so its guides do not linger.
      setGuides([]);
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [arrange, chosenElementIds, fit, layout, selectedId, selection, stepHistory, targets, transform]);

  if (!template || !layout || !page) {
    return (
      <div className="janso-editor">
        <p className="janso-editor__status">No template to design.</p>
      </div>
    );
  }

  const live = publication?.versions.find((version) => version.id === publication.liveVersionId);
  const hovered = targetById(targets, hoveredId);
  const readOnly = template.isSystem || restorePending;
  const editing = editingText ? targetById(targets, editingText) : null;

  return (
    <div className="janso-editor" data-panel={panel ?? ''}>
      <header className="janso-editor__toolbar">
        {/* The way out. The editor is full-bleed, so without it the browser's own Back was
          * the only exit; an unsaved layout is asked about before it is left behind. */}
        <Link
          className="janso-editor__button janso-editor__back"
          href={backHref}
          onClick={(event) => {
            if (!unsaved) return;
            event.preventDefault();
            setLeaving(true);
          }}
        >
          ← Back to templates
        </Link>
        <h1 className="janso-editor__title">
          {template.name}
          <span className="janso-editor__subtitle">
            {templatePurpose(template)} · {live ? `Live · version ${live.versionNumber}` : 'Draft · not printing yet'}
            {readOnly ? ' · shipped template, read-only' : ''}
          </span>
        </h1>

        <span className="janso-editor__spacer" />
        <div className="janso-editor__compact-controls">
          <button type="button" className="janso-editor__button" aria-expanded={panel === 'palette'} aria-controls={panelId+'-palette'} onClick={event => { panelTrigger.current = event.currentTarget; setPanel(panel === 'palette' ? null : 'palette'); }}>Palette and versions</button>
          <button type="button" className="janso-editor__button" aria-expanded={panel === 'properties'} aria-controls={panelId+'-properties'} onClick={event => { panelTrigger.current = event.currentTarget; setPanel(panel === 'properties' ? null : 'properties'); }}>Properties panel</button>
        </div>

        <span className="janso-zoom" role="group" aria-label="History">
          <button
            type="button"
            className="janso-zoom__btn"
            onClick={() => stepHistory('undo')}
            disabled={!history || !canUndo(history)}
            aria-label="Undo"
            title={history && undoLabel(history) ? `Undo ${undoLabel(history)}` : 'Nothing to undo'}
          >
            ↶
          </button>
          <button
            type="button"
            className="janso-zoom__btn"
            onClick={() => stepHistory('redo')}
            disabled={!history || !canRedo(history)}
            aria-label="Redo"
            title={history && redoLabel(history) ? `Redo ${redoLabel(history)}` : 'Nothing to redo'}
          >
            ↷
          </button>
        </span>

        <label className="janso-editor__stat">
          <span className="janso-editor__stat-key">Values</span>
          <select
            className="janso-editor__select"
            aria-label="What the page prints in place of data"
            value={valueMode}
            onChange={(event) => setValueMode(event.target.value as ValueMode)}
          >
            <option value="resolved">Sample data</option>
            <option value="placeholder">Field names</option>
          </select>
        </label>

        {/* A preset reshapes the layout, so it is an edit and a shipped template refuses
          * it — and it is one history entry, which is the honest way back. */}
        <label className="janso-editor__stat">
          <span className="janso-editor__stat-key">Paper</span>
          <select
            className="janso-editor__select"
            aria-label="Apply a paper preset"
            value={presetId ?? ''}
            disabled={readOnly}
            onChange={(event) =>
              edit((current) => applyPreset(current, event.target.value as PresetId), 'preset', {
                discrete: true,
              })
            }
          >
            {presetId ? null : <option value="">Custom</option>}
            {PRESETS.map((preset) => (
              <option key={preset.id} value={preset.id} title={preset.hint}>
                {preset.label}
              </option>
            ))}
          </select>
        </label>

        {copies.length > 0 ? (
          <label className="janso-editor__stat">
            <span className="janso-editor__stat-key">Copy</span>
            <select
              className="janso-editor__select"
              aria-label="Printed copy to preview"
              value={copy ?? ''}
              onChange={(event) => setCopy((event.target.value || null) as CopyLabel | null)}
            >
              <option value="">No mark</option>
              {copies.map((label) => (
                <option key={label} value={label}>
                  {COPY_LABELS[label]}
                </option>
              ))}
            </select>
          </label>
        ) : null}

        {/*
          * Present and disabled, not absent.
          *
          * A designer who has just built a template looks for export, and a control that
          * is not there reads as "it must be somewhere else" — they go hunting. Disabled
          * with the reason attached says the true thing: the authoritative PDF needs a
          * server renderer that produces the same result as this preview, and until it
          * exists there is nothing honest to hand over (`docs/invoice-design.md` §9.1).
          * Producing one from the client would ship a second, different answer.
          */}
        <button
          type="button"
          className="janso-editor__button"
          disabled
          aria-label="Download PDF — no renderer yet"
          title="The authoritative PDF needs the design service's renderer, which does not exist yet. This canvas is the editor's own preview."
        >
          Download PDF
        </button>

        <ZoomControl zoom={zoom} onChange={(next) => setZoom(clampZoom(next))} onFit={fit} />
      </header>

      <nav id={panelId+'-palette'} className="janso-editor__rail" aria-label="Templates and page structure" onKeyDown={event => { if (event.key === 'Escape' && panel) { event.stopPropagation(); closePanel(); } }}>
        <button type="button" className="janso-editor__button janso-editor__panel-close" onClick={closePanel}>Close palette and versions</button>
        <div className="janso-editor__group">
          <p className="janso-editor__group-label" id="designer-templates">
            Templates
          </p>
          <ul className="janso-editor__list" aria-labelledby="designer-templates">
            {templates.map((candidate) => (
              <li key={candidate.id}>
                <button
                  type="button"
                  className="janso-editor__item"
                  aria-current={candidate.id === template.id}
                  onClick={() => selectTemplate(candidate.id)}
                  disabled={restorePending}
                >
                  {candidate.name}
                  <span className="janso-editor__item-meta">
                    {candidate.status === 'PUBLISHED' ? 'Live' : 'Draft'}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>

        <div className="janso-editor__group">
          <p className="janso-editor__group-label">Page structure</p>
          <ElementTree
            layout={layout}
            targets={targets}
            selectedId={selectedId}
            selectedIds={selectedIds}
            onSelect={select}
            onHover={setHoveredId}
          />
        </div>

        <FieldPalette
          destination={destination}
          placed={placed}
          onPlace={place}
          onAdd={(kind) => insert({ kind })}
          readOnly={readOnly}
          {...(template.lineProfile ? { lineProfile: template.lineProfile } : {})}
        />

        {publication ? (
          <VersionPanel
            publication={publication}
            changeCount={pending}
            verdict={verdict}
            onPublish={() => {
              previewAfterSave.current = false;
              setPublishError(null);
              setIntent('publish');
              setPublishOpen(true);
            }}
            onRestore={restore}
            canLoadVersion={!!persistence?.loadVersion && !readOnlyReason && !template.isSystem}
            restoreFailure={restoreFailure}
            {...(persistence && !readOnlyReason
              ? {
                  onSaveDraft: () => {
                    previewAfterSave.current = false;
                    setPublishError(null);
                    setIntent('draft');
                    setPublishOpen(true);
                  },
                }
              : {})}
            busy={!!persistence?.pending || restorePending}
          />
        ) : null}

        {onPreviewWithBill ? (
          <div className="janso-editor__group">
            <p className="janso-editor__group-label">Check on a real bill</p>
            <div className="janso-editor__publish">
              <button
                type="button"
                className="janso-editor__button"
                disabled={!!persistence?.pending || restorePending || (!newestVersion && !persistence)}
                onClick={previewWithBill}
              >
                Preview with a saved bill
              </button>
              <p className="janso-editor__row-hint" data-testid="bill-preview-state">
                {newestVersion && !unsaved
                  ? `Prints version ${newestVersion.versionNumber} on a saved bill you choose, as a PDF marked as a preview.`
                  : persistence
                    ? 'Your changes are saved as a draft version first; then you choose a bill.'
                    : 'This design has no saved version to preview yet.'}
              </p>
            </div>
          </div>
        ) : null}
        {usage}
      </nav>

      {/* A `main` landmark, not a bare div: the editor has a banner, a nav, a complementary
        * panel and a contentinfo, and without this the one region that holds the work has
        * no name and no skip target. Phase 8 found it missing. */}
      <main className="janso-editor__stage" ref={stageRef} aria-label="Document canvas">
        <DesignCanvas
          paper={{
            size: layout.page.size,
            orientation: layout.page.orientation,
            widthMm: layout.page.widthMm,
            heightMm: layout.page.heightMm,
          }}
          /* A roll is drawn as long as its content: the chip and the sheet must agree. */
          drawnHeightMm={page.heightMm}
          margins={layout.page.margins}
          zoom={zoom}
          gridStepMm={layout.page.gridStepMm}
          onCursorChange={setCursor}
          chip={`${page.label} · ${formatMm(page.widthMm)} × ${formatMm(page.heightMm)} mm${
            copy ? ` · ${COPY_LABELS[copy]}` : ''
          }`}
          label={`${template.name}, ${page.label} ${layout.page.orientation.toLowerCase()}`}
          {...(readOnly ? {} : { dropTypes: [DRAG_FIELD, DRAG_ELEMENT], onDrop: drop })}
        >
          <DocumentLayer layout={layout} copy={copy} values={valueMode} company={company} assets={assetSource} />
          <GuideLayer guides={guides} />
          {selection?.element && isLineTable(selection.element.type) && !readOnly ? (
            <ColumnHandles
              target={selection}
              element={selection.element}
              zoom={zoom}
              /* A divider moves a boundary: the width it gains comes from the next
               * column, so the table's total stays put. Typing a width in the inspector
               * is the other gesture, and is capped at the free space instead. */
              onResize={(id, key, widthMm) =>
                edit(
                  (current) => resizeColumnBoundary(current, id, key, widthMm),
                  `column:${id}:${key}`,
                )
              }
            />
          ) : null}
          <SelectionLayer
            targets={targets}
            selectedId={selectedId}
            selectedIds={selectedIds}
            hoveredId={hoveredId}
            zoom={zoom}
            onSelect={select}
            onHover={setHoveredId}
            onKeyCommand={(command, intent) => {
              const next = navigate(targets, selectedId, command);
              // Shift extends: the arrow still decides *which* target, and the set keeps
              // what it already had, so one press adds one neighbour.
              select(next, intent);
            }}
            onMarquee={(rect, intent) => {
              const caught = targetsInRect(targets, rect);
              setEditingText(null);
              setSelectedIds((current) =>
                intent?.additive
                  ? [...current, ...caught.filter((id) => !current.includes(id))]
                  : caught,
              );
            }}
            onTransform={readOnly ? undefined : onTransform}
            onActivate={
              readOnly
                ? undefined
                : (id) => {
                    const candidate = targetById(targets, id);
                    // Only text carries text: activating a table or an image has no
                    // meaning yet, and opening an empty editor over one would be a lie.
                    if (candidate?.element?.content !== undefined) setEditingText(id);
                  }
            }
          />
          {editing?.element && !readOnly ? (
            <InlineTextEditor
              target={editing}
              element={editing.element}
              onChange={(content) =>
                edit(
                  (current) => updateElement(current, editing.element!.id, { content }),
                  `content:${editing.element!.id}`,
                )
              }
              onClose={() => setEditingText(null)}
            />
          ) : null}
        </DesignCanvas>
      </main>

      <aside id={panelId+'-properties'} className="janso-editor__inspector" aria-label="Properties" onKeyDown={event => { if (event.key === 'Escape' && panel) { event.stopPropagation(); closePanel(); } }}>
        <button type="button" className="janso-editor__button janso-editor__panel-close" onClick={closePanel}>Close properties</button>
        {/* First, because a clipped zone outranks a font size. */}
        <WarningsPanel warnings={warnings} onSelect={(id) => select(id)} />

        <ArrangePanel
          count={chosenElementIds.length}
          bounds={selectionBounds(layout, chosenElementIds)}
          depth={
            chosenElementIds.length === 1 && chosenElementIds[0]
              ? depthOf(layout, chosenElementIds[0])
              : null
          }
          handlers={arrange}
          readOnly={readOnly}
        />
        {/* The typed per-element panel only makes sense for one thing at a time: a font
         * size shown for four elements with four different sizes is a lie whichever one it
         * picks. With a group selected, Arrange above is the whole panel. */}
        {chosenElementIds.length > 1 ? null : (
          <SelectionInspector
            layout={layout}
            selection={selection}
            handlers={handlers}
            readOnly={readOnly}
            company={company}
          />
        )}
      </aside>

      <footer className="janso-editor__status">
        <span className="janso-editor__stat">
          <span className="janso-editor__stat-key">Cursor</span>
          <span className="janso-editor__stat-value" data-testid="cursor-readout">
            {cursor ? `${formatMm(cursor.xMm)}, ${formatMm(cursor.yMm)} mm` : 'off page'}
          </span>
        </span>
        <span className="janso-editor__stat">
          <span className="janso-editor__stat-key">Zoom</span>
          <span className="janso-editor__stat-value" data-testid="zoom-readout">
            {Math.round(zoom * 100)}%
          </span>
        </span>
        <span className="janso-editor__stat">
          <span className="janso-editor__stat-key">Selected</span>
          {/*
            A live region over the *selection* only: it moves by keyboard, and a
            screen-reader user needs to hear what they landed on — including after a nudge,
            which changes its position.
          */}
          <span
            className="janso-editor__stat-value"
            data-testid="selection-readout"
            aria-live="polite"
            aria-atomic="true"
          >
            {chosenElementIds.length > 1
              ? `${chosenElementIds.length} elements · ${selection?.label ?? ''} active`
              : selection
                ? `${selection.label} · ${formatMm(selection.rect.xMm)}, ${formatMm(
                    selection.rect.yMm,
                  )} mm · ${formatMm(selection.rect.widthMm)} × ${formatMm(
                    selection.rect.heightMm,
                  )} mm`
                : 'nothing'}
          </span>
        </span>
        {hovered && !selection ? (
          <span className="janso-editor__stat-key" data-testid="hover-readout">
            {hovered.label} (hovered)
          </span>
        ) : null}
        {guides.length > 0 ? (
          <span className="janso-editor__stat" data-testid="guide-readout">
            aligned on {guides.length} {guides.length === 1 ? 'guide' : 'guides'}
          </span>
        ) : null}
        <span className="janso-editor__spacer" />
        <span className="janso-editor__stat" data-testid="edit-count">
          {/* This read "nothing is saved yet" unconditionally, which was honest against the
            * fixtures and becomes a lie the moment there is a service behind it. */}
          {editCount === 0
            ? persistence
              ? 'No changes'
              : 'No changes · nothing is saved yet'
            : `${editCount} change${editCount === 1 ? '' : 's'}${persistence ? ' · not saved yet' : ' · nothing is saved yet'}`}
        </span>
      </footer>

      <ConfirmDialog
        open={leaving && unsaved}
        title="Leave the designer?"
        confirmLabel="Leave without saving"
        onCancel={() => setLeaving(false)}
        onConfirm={leave}
      >
        <p>
          Changes made since the last save will be lost. Save a draft or publish first to keep
          them.
        </p>
      </ConfirmDialog>

      <ConfirmDialog
        open={saveFirst && !!persistence}
        title="Save this design first?"
        confirmLabel="Save a draft"
        onCancel={() => setSaveFirst(false)}
        onConfirm={() => {
          setSaveFirst(false);
          previewAfterSave.current = true;
          setPublishError(null);
          setIntent('draft');
          setPublishOpen(true);
        }}
      >
        <p>
          A preview prints a saved version of this design on a saved bill, so what is on the canvas
          is saved as a draft version first. Nothing prints on a draft until it is published.
        </p>
      </ConfirmDialog>

      {publication ? (
        <ConfirmDialog
          open={publishOpen}
          title={
            intent === 'draft'
              ? `Save version ${nextVersionNumber(publication)} as a draft?`
              : `Publish version ${nextVersionNumber(publication)}?`
          }
          confirmLabel={intent === 'draft' ? 'Save draft' : 'Publish'}
          /* The locally-detected problem (an empty summary) or the service's own, whichever
           * there is. Both keep the dialog open; neither loses the layout. */
          error={publishError ?? persistence?.failure ?? null}
          onCancel={() => {
            previewAfterSave.current = false;
            setPublishOpen(false);
            setPublishError(null);
          }}
          onConfirm={() => {
            void (intent === 'draft' ? saveDraft() : confirmPublish());
          }}
          busy={persistence?.pending ?? false}
        >
          <p>
            {intent === 'draft'
              ? 'It is kept as a version you can come back to. What documents print on does not change.'
              : 'It becomes the live version immediately, and every document printed from this template will use it. Earlier versions are left as they are.'}
          </p>

          {warnings.length > 0 ? (
            /* Errors cannot reach here — they disable the button — so everything in this
             * list is something that may be deliberate. It is stated rather than blocked,
             * and stated *here*, which is the last moment anyone will read it. */
            <div data-testid="publish-warnings">
              <p>
                Publishing with {warnings.length} {warnings.length === 1 ? 'warning' : 'warnings'}:
              </p>
              <ul>
                {warnings.map((warning) => (
                  <li key={`${warning.code}-${warning.targetId}`}>{warning.message}</li>
                ))}
              </ul>
            </div>
          ) : null}

          <label className="janso-editor__search">
            <span className="janso-editor__row-label">What changed</span>
            <input
              type="text"
              className="janso-editor__input"
              value={summary}
              placeholder="Widened the description column"
              onChange={(event) => setSummary(event.target.value)}
            />
          </label>
        </ConfirmDialog>
      ) : null}
    </div>
  );
}
