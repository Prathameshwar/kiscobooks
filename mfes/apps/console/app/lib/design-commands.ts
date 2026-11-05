'use client';
import { useCallback, useMemo } from 'react';
import type { components } from '@janso/api-client/design';
import { assertDesignRow, assertDesignVersion, designBase, designRequest } from './design-api';
import { layoutToWire } from './design-canvas';
import { useServiceCommand } from './service-resource';
import type { CanvasDefinition } from '../(editor)/invoice-designer/layout-model';

type Wire = components['schemas'];

export type SavedVersion = { id: string; versionNumber: number; publishedAt: string | null };

/**
 * Writing a design back to the service.
 *
 * **Saving and publishing are two requests, deliberately not one.** The service appends an
 * immutable version and then, separately, makes one of them the layout every future document
 * prints on (docs/invoice-design.md §5.1). Collapsing them into a single "publish" call would
 * make every intermediate save live, which is the one thing the version model exists to
 * prevent: editing a live invoice layout must not change the document a customer receives
 * until somebody decides it should.
 *
 * Every write goes through `useServiceCommand`, which is where the replay rule lives: the same
 * body keeps the same idempotency key across a retry, and a 5xx leaves the command *uncertain*
 * rather than pretending it failed. A design write is not money, so the service does not
 * require a key — but "the save may or may not have landed" is exactly as confusing for a
 * layout as for a payment, and the retry has to be the same request rather than a second one.
 */
export type DesignWrites = {
  /** Append a version. Does not change what prints. */
  saveVersion: (layout: CanvasDefinition, changeSummary: string) => Promise<SavedVersion | null>;
  /** Append a version and make it live, in that order. */
  publishVersion: (layout: CanvasDefinition, changeSummary: string) => Promise<SavedVersion | null>;
  pending: boolean;
  /** Why the last write did not complete, as one sentence a panel can show. */
  failure: string | null;
  /** A 5xx left the outcome unknown; the next attempt must be the identical request. */
  uncertain: boolean;
  clear: () => void;
};

export function useDesignWrites(company: string, templateId: string): DesignWrites {
  const command = useServiceCommand(designRequest, 'design service');
  const base = designBase(company, '/' + templateId);

  const append = useCallback(
    async (layout: CanvasDefinition, changeSummary: string) => {
      const summary = changeSummary.trim();
      return command.execute<Wire['VersionDetail']>(
        {
          path: base + '/versions',
          method: 'POST',
          body: {
            layout_definition: layoutToWire(layout),
            ...(summary ? { change_summary: summary } : {}),
          },
        },
        (value) => {
          assertDesignVersion(value as never, templateId);
        },
      );
    },
    [base, command, templateId],
  );

  const saveVersion = useCallback(
    async (layout: CanvasDefinition, changeSummary: string) => {
      const version = await append(layout, changeSummary);
      return version ? received(version) : null;
    },
    [append],
  );

  const publishVersion = useCallback(
    async (layout: CanvasDefinition, changeSummary: string) => {
      const version = await append(layout, changeSummary);
      if (!version) return null;
      /*
       * A second command for the second request, so a failure here is reported as a failure
       * to *publish* rather than to save — the version exists either way, and telling someone
       * their work was lost when it was not is worse than telling them it is not live yet.
       */
      const published = await command.execute<Wire['TemplateDetail']>(
        { path: `${base}/versions/${version.id}/publish`, method: 'POST' },
        (value) => {
          assertDesignRow(value as never, company, templateId);
          if (value.current_version_id !== version.id) {
            throw {
              status: 502,
              message: 'The service did not confirm this version as the live one. Reload before continuing.',
            };
          }
        },
      );
      return published ? { ...received(version), publishedAt: published.updated_at } : null;
    },
    [append, base, command, company, templateId],
  );

  return useMemo(
    () => ({
      saveVersion,
      publishVersion,
      pending: command.pending,
      failure: command.failure?.message ?? null,
      uncertain: command.uncertain,
      clear: command.clear,
    }),
    [command.clear, command.failure, command.pending, command.uncertain, publishVersion, saveVersion],
  );
}

function received(version: Wire['VersionDetail']): SavedVersion {
  return {
    id: version.id,
    versionNumber: version.version_number,
    publishedAt: version.published_at ?? null,
  };
}

/* ------------------------------------------------------------------ templates */

export type TemplateDraft = {
  name: string;
  code: string;
  paperSize: string;
  orientation: string;
  widthMm?: string;
  heightMm?: string;
  /** What the design is for; empty for "any voucher". */
  voucherKind?: string;
  lineProfile?: string;
};

export type TemplateWrites = {
  /**
   * Create the template. With `initialCanvas`, its first version is saved in the same request
   * (a draft: nothing prints on it until it is published).
   */
  create: (draft: TemplateDraft, initialCanvas?: CanvasDefinition | null) => Promise<{ id: string } | null>;
  pending: boolean;
  failure: string | null;
  /** Per-field messages from a 422, so a form can put each one beside its input. */
  fields: Record<string, string> | null;
  clear: () => void;
};

/**
 * Creating a template.
 *
 * A template is created empty and its first version is saved from the editor — the create form
 * knows a name, a code and what paper this prints on, not a layout. The one exception is a
 * caller that *does* know one: *Customize layout* for Purchase starts from a copy of the standard
 * Purchase layout (plan R4), sent as `initial_canvas`, which the service stores as version 1, a
 * draft. The service refuses the whole create if that canvas does not fit the paper, so no
 * half-made template survives a bad starter.
 */
export function useTemplateWrites(company: string): TemplateWrites {
  const command = useServiceCommand(designRequest, 'design service');

  const create = useCallback(
    async (draft: TemplateDraft, initialCanvas?: CanvasDefinition | null) => {
      const created = await command.execute<Wire['TemplateCreated']>(
        {
          path: designBase(company),
          method: 'POST',
          body: {
            name: draft.name.trim(),
            code: draft.code.trim(),
            paper_size: draft.paperSize,
            page_orientation: draft.orientation,
            // `DECIMAL(19,4)` on the wire, so a string — never a float, which would re-scale
            // a page size on the way through (docs/invoice-design.md §4.2).
            ...(draft.paperSize === 'CUSTOM' && draft.widthMm ? { page_width_mm: draft.widthMm } : {}),
            ...(draft.paperSize === 'CUSTOM' && draft.heightMm ? { page_height_mm: draft.heightMm } : {}),
            ...(draft.voucherKind ? { voucher_kind: draft.voucherKind } : {}),
            ...(draft.voucherKind && draft.lineProfile ? { line_profile: draft.lineProfile } : {}),
            ...(initialCanvas ? { initial_canvas: layoutToWire(initialCanvas) } : {}),
          },
        },
        (value) => {
          assertDesignRow(value as never, company);
        },
      );
      return created ? { id: created.id } : null;
    },
    [command, company],
  );

  return useMemo(
    () => ({
      create,
      pending: command.pending,
      failure: command.failure?.message ?? null,
      fields: command.failure?.fields ?? null,
      clear: command.clear,
    }),
    [command.clear, command.failure, command.pending, create],
  );
}
