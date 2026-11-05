'use client';

import { useState } from 'react';
import { ErrorState, Notice, Skeleton } from '@janso/ui';
import { useDesignTemplates } from '../../lib/design-templates';
import { NewTemplateDialog } from './NewTemplateDialog';
import { emptyLayout, paperOf, templateToEditor } from '../../lib/design-canvas';
import { GalleryNav, TemplateGallery } from './TemplateGallery';

/**
 * The gallery, on this company's real designs.
 *
 * `TemplateGallery` stays presentational — it takes templates and draws cards, exactly as it
 * did against the fixtures. What changed is where the list comes from, which is the whole point
 * of the phase: the editor's eight phases of work did not need rewriting to be connected.
 *
 * A card needs a layout only for its thumbnail, and the list projection deliberately carries no
 * layout tree (one per card would be a page of trees to draw four cards). Each card therefore
 * gets an empty layout and the thumbnail shows the page shape; opening one loads its real tree.
 */
export function DesignGalleryRoute({
  company,
  canManage = false,
}: {
  company: string;
  /** `design.template.manage` — without it there is nothing to start a template with. */
  canManage?: boolean;
}) {
  const { templates, loading, failure } = useDesignTemplates(company);
  const [creating, setCreating] = useState(false);

  if (failure) {
    return (
      <main className="janso-gallery">
        <GalleryNav />
        <ErrorState
          status={failure.status === 403 ? 403 : 500}
          detail={failure.message}
        />
      </main>
    );
  }
  if (loading) {
    return (
      <main className="janso-gallery">
        <GalleryNav />
        <div className="janso-gallery__head">
          <h1 className="janso-editor__title">Print templates</h1>
        </div>
        <Skeleton lines={3} />
      </main>
    );
  }

  return (
    <>
      {canManage ? (
        <div className="janso-gallery__head">
          <button
            type="button"
            className="janso-btn janso-btn--primary"
            onClick={() => setCreating(true)}
          >
            New template
          </button>
        </div>
      ) : null}
      <NewTemplateDialog company={company} open={creating} onClose={() => setCreating(false)} />
      {templates.some((template) => template.is_system) ? (
        <Notice>
          Shipped designs are read-only. Duplicate one to make it yours.
        </Notice>
      ) : null}
      <TemplateGallery
        templates={templates.map((template) =>
          templateToEditor(template, emptyLayout(paperOf(template))),
        )}
      />
    </>
  );
}
