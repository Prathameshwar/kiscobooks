'use client';

import { Badge } from '@janso/ui';

import {
  type Publication,
  type PublishVerdict,
  isRestorable,
  nextVersionNumber,
  versionDate,
} from './publication';

/**
 * What this template has printed, and the control that changes it.
 *
 * The distinction this panel exists to make visible: a draft accumulates edits, and what a
 * customer receives is a *published version*. Nothing here is live because it is on screen.
 *
 * **Restore is offered only where it can be honoured.** This session keeps the layouts it
 * published and nothing else; the versions the template arrived with live in the service
 * that has not been built yet. A greyed row that says why beats a button that quietly does
 * nothing, which is the version of this panel that would get written if nobody looked.
 */

type VersionPanelProps = {
  publication: Publication;
  /** Edits since the layout was loaded, so the panel can say what publishing would carry. */
  changeCount: number;
  verdict: PublishVerdict;
  onPublish: () => void;
  onRestore: (versionId: string) => void;
  /**
   * Offered only when there is somewhere to save *to*. A draft version is appended without
   * becoming what documents print on, which is a distinction the editor could not make while
   * its publications were local — there was nothing to save to and nothing to be live.
   */
  onSaveDraft?: () => void;
  /** Disables both actions while a write is in flight, so neither is pressed twice. */
  busy?: boolean;
  canLoadVersion?: boolean;
  restoreFailure?: string | null;
};

export function VersionPanel({
  publication,
  changeCount,
  verdict,
  onPublish,
  onRestore,
  onSaveDraft,
  busy = false,
  canLoadVersion = false,
  restoreFailure = null,
}: VersionPanelProps) {
  return (
    <div className="janso-editor__group">
      <p className="janso-editor__group-label" id="designer-versions">
        Versions
      </p>

      <div className="janso-editor__publish">
        <button
          type="button"
          className="janso-editor__button"
          disabled={!verdict.ok || busy}
          onClick={onPublish}
          aria-label={`Publish version ${nextVersionNumber(publication)}`}
        >
          Publish version {nextVersionNumber(publication)}
        </button>
        {onSaveDraft ? (
          /* Beside publish, not instead of it. The common act is saving work in progress;
           * the deliberate act is making it what customers receive. */
          <button
            type="button"
            className="janso-editor__button"
            disabled={busy || changeCount === 0}
            onClick={onSaveDraft}
            aria-label={`Save version ${nextVersionNumber(publication)} as a draft`}
          >
            {busy ? 'Saving…' : 'Save draft'}
          </button>
        ) : null}
        {/* Always a sentence, never a disabled button on its own: "why can I not press
          * this" is the question a disabled control asks and must answer. */}
        <p className="janso-editor__row-hint" data-testid="publish-state">
          {verdict.ok
            ? `${changeCount === 1 ? '1 change' : `${changeCount} changes`} will go live`
            : verdict.reason}
        </p>
      </div>

      <ul className="janso-editor__versions" aria-labelledby="designer-versions">
        {publication.versions.map((version) => {
          const isLive = version.id === publication.liveVersionId;
          const restorable = isRestorable(publication, version.id) || (canLoadVersion && !!version.publishedAt);

          return (
            <li key={version.id}>
              <div className="janso-editor__version" data-live={isLive}>
                <span className="janso-editor__version-head">
                  Version {version.versionNumber}
                  {isLive ? <Badge tone="success">Live</Badge> : null}
                </span>
                <span className="janso-editor__version-meta">
                  {version.changeSummary ?? 'No summary'} ·{' '}
                  {version.publishedAt
                    ? `published ${versionDate(version.publishedAt)}`
                    : `drafted ${versionDate(version.createdAt)}`}
                </span>
                {restorable && !isLive ? (
                  <button
                    type="button"
                    className="janso-editor__button"
                    aria-label={`Restore version ${version.versionNumber} into the editor`}
                    onClick={() => onRestore(version.id)}
                    disabled={busy}
                  >
                    Restore
                  </button>
                ) : null}
                {!restorable ? (
                  <span className="janso-editor__version-meta">
                    Layout held by the design service — not available offline
                  </span>
                ) : null}
              </div>
            </li>
          );
        })}
      </ul>
      {restoreFailure && <p className="janso-editor__row-hint" role="alert">{restoreFailure}</p>}
    </div>
  );
}
