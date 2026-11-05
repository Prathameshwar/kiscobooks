'use client';
import { useEffect, useMemo, useRef, useState } from 'react';
import type { components } from '@janso/api-client/design';
import type { PageMeta } from '@janso/ui';
import { assertDesignRow, designBase, designRequest } from './design-api';
import {
  isEditableLayout,
  layoutToEditor,
  templateToEditor,
  versionToEditor,
  type PaperRow,
} from './design-canvas';
import { requestFailure, type RequestFailure } from './service-call';
import { useServiceRead } from './service-resource';
import type { DesignTemplate } from '../(editor)/invoice-designer/layout-model';

type Wire = components['schemas'];

/** Load only the selected published version; denied or legacy layouts never replace work. */
export async function readPublishedDesignVersion(company: string, templateId: string, versionId: string, paper: PaperRow) {
  const version = await designRequest<Wire['VersionDetail']>({ path: `${designBase(company)}/${templateId}/versions/${versionId}` });
  assertDesignRow(version, company, versionId);
  if (version.template_id !== templateId || !version.published_at || !isEditableLayout(version.layout_definition)) {
    throw new Error('This published version cannot be edited.');
  }
  return layoutToEditor(version.layout_definition, paper);
}

/**
 * Reading the real designs, in place of the fixtures the editor was built against.
 *
 * **Not `useServiceList`.** That helper appends `sort=-id` to every query, and the design
 * service takes no `sort` — its lists are keyset-ordered newest-first by construction, and the
 * console's own allowlist refuses a query key the service would only reject with a 422 anyway.
 * Borrowing the helper would have meant widening the boundary to carry a parameter nothing
 * honours. The gallery and the version panel each want one page, so one page is what these read.
 */

/** A gallery page. 200 is the service's own ceiling, and no gallery pages beyond it yet. */
const PAGE = 200;

export type TemplateList = {
  templates: Wire['TemplateItem'][];
  /** More templates exist than this page holds — a caller that looks one up by id may not find it. */
  hasMore: boolean;
  loading: boolean;
  failure: RequestFailure | null;
  refresh: () => void;
};

export function useDesignTemplates(company: string | undefined): TemplateList {
  const read = useServiceRead<{ items: Wire['TemplateItem'][]; page: PageMeta }>(
    company ? `/v1/companies/${company}/templates?limit=${PAGE}` : undefined,
    designRequest,
    (value) => {
      if (!Array.isArray(value.items)) {
        throw { status: 502, message: 'The template list could not be verified.' };
      }
      // Every row, not just the first: a cross-company item in a list is the same breach as a
      // cross-company detail, and it is the list that the gallery links from.
      for (const item of value.items) assertDesignRow(item, company!);
    },
    'design service',
  );
  return {
    templates: read.data?.items ?? [],
    hasMore: !!read.data?.page?.has_more,
    loading: read.loading,
    failure: read.failure,
    refresh: read.refresh,
  };
}

export type TemplateEditorState = {
  /** The template as the editor model wants it, or `null` while loading or on failure. */
  template: DesignTemplate | null;
  /** The row's paper, which the layout no longer restates. */
  paper: PaperRow | null;
  /** The version the layout came from, so a save knows what it is appending to. */
  versionId: string | null;
  /**
   * Why this template cannot be edited, if it cannot. A `1.0.0` layout prints and keeps its
   * history but cannot express a column set, a totals block or a zone box, so the editor would
   * have to invent geometry and then save the invention back as the author's choice. A shipped
   * system design is read-only by domain rule — a tenant copies one rather than editing it.
   */
  readOnlyReason: string | null;
  loading: boolean;
  failure: RequestFailure | null;
  refresh: () => void;
};

/**
 * One template, its newest version's layout, and its history.
 *
 * Three requests, in one effect rather than three hooks, because the layout request depends on
 * which version the history says is newest — and a hook cannot be called conditionally. A
 * template with no version at all is a real state (a draft created without a canvas), and it
 * opens on an empty layout rather than an error.
 */
export function useDesignTemplate(
  company: string | undefined,
  templateId: string | undefined,
): TemplateEditorState {
  const [state, setState] = useState<Omit<TemplateEditorState, 'refresh'>>({
    template: null,
    paper: null,
    versionId: null,
    readOnlyReason: null,
    loading: !!company && !!templateId,
    failure: null,
  });
  const [revision, setRevision] = useState(0);
  const latest = useRef(0);

  useEffect(() => {
    if (!company || !templateId) {
      setState({
        template: null,
        paper: null,
        versionId: null,
        readOnlyReason: null,
        loading: false,
        failure: null,
      });
      return;
    }
    const controller = new AbortController();
    const ticket = ++latest.current;
    setState((current) => ({ ...current, loading: true, failure: null }));

    const base = designBase(company, '/' + templateId);
    void (async () => {
      try {
        const detail = await designRequest<Wire['TemplateDetail']>({
          path: base,
          signal: controller.signal,
        });
        assertDesignRow(detail, company, templateId);

        const history = await designRequest<{ items: Wire['VersionItem'][] }>({
          path: `${base}/versions?limit=${PAGE}`,
          signal: controller.signal,
        });
        if (!Array.isArray(history.items)) {
          throw { status: 502, message: 'The revision history could not be verified.' };
        }
        // Newest first, per the service. The live version is what prints; the newest is what
        // an editor should open, because that is where the last edit went.
        const newest = history.items[0];

        const paper: PaperRow = {
          paper_size: detail.paper_size,
          page_orientation: detail.page_orientation,
          page_width_mm: detail.page_width_mm ?? null,
          page_height_mm: detail.page_height_mm ?? null,
        };
        let readOnlyReason: string | null = detail.is_system
          ? 'This is a shipped design. Duplicate it to make changes.'
          : null;
        let layout = layoutToEditor({ schema_version: '1.1.0' }, paper);

        if (newest) {
          const version = await designRequest<Wire['VersionDetail']>({
            path: `${base}/versions/${newest.id}`,
            signal: controller.signal,
          });
          assertDesignRow(version, company, newest.id);
          if (isEditableLayout(version.layout_definition)) {
            layout = layoutToEditor(version.layout_definition, paper);
          } else {
            readOnlyReason ??=
              'This design was saved on an older layout format. Duplicate it to continue editing.';
          }
        }

        if (controller.signal.aborted || ticket !== latest.current) return;
        setState({
          template: templateToEditor(detail, layout, history.items.map(versionToEditor)),
          paper,
          versionId: newest?.id ?? null,
          readOnlyReason,
          loading: false,
          failure: null,
        });
      } catch (error) {
        if (controller.signal.aborted || ticket !== latest.current) return;
        setState({
          template: null,
          paper: null,
          versionId: null,
          readOnlyReason: null,
          loading: false,
          failure: requestFailure(error, 'design service'),
        });
      }
    })();
    return () => controller.abort();
  }, [company, templateId, revision]);

  return useMemo(
    () => ({ ...state, refresh: () => setRevision((value) => value + 1) }),
    [state],
  );
}
