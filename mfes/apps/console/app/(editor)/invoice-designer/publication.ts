/**
 * Versions, publishing and what is live — the local half of it.
 *
 * A template's *design* is editable; what it **prints** is a published version, and the two
 * are deliberately not the same thing. Editing a live invoice layout must not change the
 * document a customer receives until someone decides it should
 * (`docs/invoice-design.md` — immutable layout versions). So a draft accumulates edits and
 * publishing takes a snapshot of them.
 *
 * **Publishing is gated on the layout being printable.** Phase 6's `checkLayout` exists for
 * this moment: an `error` means something will be clipped, dropped or overlaid, and there
 * is no reading of "publish" under which shipping that to a printer is what anyone meant.
 * Warnings are listed and can be accepted, because a warning may be deliberate.
 *
 * **What is local, and what is honest about being local.** This session can publish, and it
 * keeps the layout it published, so that version can be looked at and restored. The
 * versions the fixtures arrived with have no layout here — the service will serve those on
 * request, and until it exists the panel says so rather than offering a button that
 * silently does nothing.
 *
 * Pure and clock-injected, like `history.ts`, so none of this needs a rendered component
 * to test and the same functions can move behind the service's API unchanged.
 */

import type {
  CanvasDefinition,
  DesignTemplate,
  TemplateStatus,
  TemplateVersionSummary,
} from './layout-model';
import type { LayoutWarning } from './layout-warnings';

export type Publication = {
  readonly status: TemplateStatus;
  /** `null` until something has been published — a template that prints nothing. */
  readonly liveVersionId: string | null;
  /** Newest first, which is the order a history is read in. */
  readonly versions: readonly TemplateVersionSummary[];
  /**
   * The layouts *this session* published, by version id. Deliberately partial: the
   * fixtures' own versions are not here, and the panel must not pretend otherwise.
   */
  readonly snapshots: Readonly<Record<string, CanvasDefinition>>;
};

/** The publication state a template arrives with. */
export function publicationOf(template: DesignTemplate): Publication {
  return {
    status: template.status,
    liveVersionId: template.liveVersionId,
    versions: [...template.versions].sort((a, b) => b.versionNumber - a.versionNumber),
    snapshots: {},
  };
}

export type PublishVerdict =
  | { readonly ok: true }
  | { readonly ok: false; readonly reason: string };

/**
 * Whether this layout may be published, and if not, why in one sentence the rail can show.
 *
 * A shipped template is refused for the same reason it is read-only everywhere else: a
 * tenant copies one rather than editing it.
 */
export function canPublish(
  template: Pick<DesignTemplate, 'isSystem'>,
  warnings: readonly LayoutWarning[],
  /** Whether the layout differs from the live version — not how many edits it took. */
  dirty: boolean,
): PublishVerdict {
  if (template.isSystem) {
    return { ok: false, reason: 'A shipped template is read-only. Copy it to publish your own.' };
  }
  const errors = warnings.filter((warning) => warning.severity === 'error');
  if (errors.length > 0) {
    return {
      ok: false,
      reason: `Fix ${errors.length === 1 ? 'the error' : `all ${errors.length} errors`} first — a clipped document prints wrong on every copy.`,
    };
  }
  if (!dirty) {
    return { ok: false, reason: 'Nothing has changed since the last published version.' };
  }
  return { ok: true };
}

/** The next version number: one past the highest, never a gap and never a reuse. */
export function nextVersionNumber(publication: Publication): number {
  return publication.versions.reduce((highest, version) => Math.max(highest, version.versionNumber), 0) + 1;
}

/**
 * Publish the current layout as a new version, and make it the live one.
 *
 * The snapshot is the layout **object**, not a copy of it: every edit function in this
 * editor is pure and returns a new tree, so the published version cannot be changed by
 * later editing. That is the immutability the service's contract requires, and it holds
 * here for free precisely because nothing mutates.
 */
export function publish(
  publication: Publication,
  template: Pick<DesignTemplate, 'id'>,
  layout: CanvasDefinition,
  changeSummary: string,
  at: Date,
): Publication {
  const versionNumber = nextVersionNumber(publication);
  const id = `${template.id}-v${versionNumber}`;
  const stamp = at.toISOString();

  const version: TemplateVersionSummary = {
    id,
    versionNumber,
    changeSummary,
    createdAt: stamp,
    publishedAt: stamp,
  };

  return {
    status: 'PUBLISHED',
    liveVersionId: id,
    versions: [version, ...publication.versions],
    snapshots: { ...publication.snapshots, [id]: layout },
  };
}

/** The layout of a version, when this session is the one that published it. */
export function snapshotOf(
  publication: Publication,
  versionId: string,
): CanvasDefinition | null {
  return publication.snapshots[versionId] ?? null;
}

/** Whether a version's layout can be looked at and restored from here. */
export function isRestorable(publication: Publication, versionId: string): boolean {
  return versionId in publication.snapshots;
}

/** A readable date for the history list. Fixed format, never the client's locale. */
export function versionDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const day = `${date.getUTCDate()}`.padStart(2, '0');
  const month = MONTHS[date.getUTCMonth()] ?? '';
  return `${day} ${month} ${date.getUTCFullYear()}`;
}

const MONTHS = [
  'Jan',
  'Feb',
  'Mar',
  'Apr',
  'May',
  'Jun',
  'Jul',
  'Aug',
  'Sep',
  'Oct',
  'Nov',
  'Dec',
];

/** What the gallery card says about a template's state, in one word plus a tone. */
export function publicationBadge(publication: Publication): {
  label: string;
  tone: 'success' | 'neutral';
} {
  return publication.liveVersionId
    ? { label: 'Live', tone: 'success' }
    : { label: 'Draft', tone: 'neutral' };
}
