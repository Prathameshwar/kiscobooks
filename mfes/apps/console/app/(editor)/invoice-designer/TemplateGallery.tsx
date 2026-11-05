import Link from 'next/link';
import { Badge, PaperThumbnail, pageGeometry } from '@janso/ui';

import { DocumentLayer } from './DocumentLayer';
import type { DesignTemplate } from './layout-model';
import { checkLayout, summarise } from './layout-warnings';
import { publicationBadge, publicationOf, versionDate } from './publication';
import { LINE_PROFILES } from './layout-model';
import { kindLabel } from '../../lib/voucher-kinds';

/** What a design is for, in words: "Purchase · Products", or "Any voucher". */
export function templatePurpose(template: Pick<DesignTemplate, 'voucherKind' | 'lineProfile'>): string {
  if (!template.voucherKind) return 'Any voucher';
  const lines = LINE_PROFILES.find((entry) => entry.value === template.lineProfile)?.label;
  return lines ? `${kindLabel(template.voucherKind)} · ${lines}` : kindLabel(template.voucherKind);
}

/**
 * The templates, as cards you can tell apart.
 *
 * Each card draws the **real document**, scaled: "the one with the logo on the left" is how
 * anyone finds a template, and four identical page icons would make this list worse than a
 * plain one. It costs a document render per card, which is four, and the thumbnail can
 * never go stale against the layout it depicts because it *is* the layout.
 *
 * Three things a designer needs before opening anything: whether it prints at all (Live
 * against Draft — a template with no published version prints nothing), whether they are
 * allowed to change it (a shipped template is read-only), and whether it is sound. The last
 * is phase 6's `checkLayout` on the card, so a broken template is visible from the gallery
 * rather than discovered after opening it.
 *
 * A server component: the fixtures need no client state, and a grid of four static cards
 * has nothing to hydrate.
 */

type TemplateGalleryProps = {
  templates: readonly DesignTemplate[];
};

export function TemplateGallery({ templates }: TemplateGalleryProps) {
  return (
    <main className="janso-gallery">
      <GalleryNav />
      <div className="janso-gallery__head">
        <h1 className="janso-editor__title">Print templates</h1>
        <span className="janso-editor__subtitle">
          {templates.length === 1 ? '1 template' : `${templates.length} templates`}
        </span>
      </div>

      {templates.length === 0 ? (
        /* Not reachable from the fixtures, and present anyway: the first thing a real
         * tenant sees is an empty gallery, and "nothing here" with no next step is the
         * worst screen in any product. */
        <p className="janso-editor__empty">
          No templates yet. A shipped design can be copied to start one.
        </p>
      ) : (
        <ul className="janso-gallery__grid">
          {templates.map((template) => {
            const publication = publicationOf(template);
            const badge = publicationBadge(publication);
            const warnings = checkLayout(template.layout);
            const live = template.versions.find(
              (version) => version.id === template.liveVersionId,
            );

            return (
              <li key={template.id}>
                <article className="janso-gallery__card">
                  <div className="janso-gallery__preview">
                    <PaperThumbnail page={pageGeometry(template.layout.page)} boxPx={190}>
                      <DocumentLayer layout={template.layout} />
                    </PaperThumbnail>
                  </div>

                  <h2 className="janso-gallery__name">
                    {template.name}
                    <Badge tone={badge.tone}>{badge.label}</Badge>
                    {template.isSystem ? <Badge tone="info">Shipped</Badge> : null}
                  </h2>
                  <span className="janso-gallery__code">{template.code}</span>
                  <span className="janso-gallery__note" data-testid="template-purpose">{templatePurpose(template)}</span>

                  {template.description ? (
                    <p className="janso-gallery__note">{template.description}</p>
                  ) : null}

                  <p className="janso-gallery__note">
                    {live
                      ? `Version ${live.versionNumber} live since ${versionDate(live.publishedAt ?? live.createdAt)}`
                      : 'Never published — this template prints nothing yet'}
                  </p>

                  <div className="janso-gallery__foot">
                    <Link className="janso-editor__button" href={`/invoice-designer/${template.id}`}>
                      {template.isSystem ? 'Inspect' : 'Design'}
                    </Link>
                    {warnings.length > 0 ? (
                      <Badge
                        tone={
                          warnings.some((warning) => warning.severity === 'error')
                            ? 'danger'
                            : 'warn'
                        }
                      >
                        {summarise(warnings)}
                      </Badge>
                    ) : null}
                  </div>
                </article>
              </li>
            );
          })}
        </ul>
      )}
    </main>
  );
}

/**
 * The way back into the console. The gallery shares the editor's full-bleed route group, so
 * it has no rail of its own; without these the browser's Back was the only exit.
 */
export function GalleryNav() {
  return (
    <nav className="janso-gallery__nav" aria-label="Print templates">
      <Link className="janso-editor__button" href="/">
        ← Back to home
      </Link>
      <Link className="janso-link" href="/documents/vouchers">
        Voucher print
      </Link>
    </nav>
  );
}
