'use client';
import { useCallback, useMemo, useState } from 'react';
import type { components } from '@janso/api-client/design';
import type { PageMeta } from '@janso/ui';
import { assertDesignRow, designRequest } from './design-api';
import { useServiceCommand, useServiceRead } from './service-resource';
import type { RequestFailure } from './service-call';

type Wire = components['schemas'];

/**
 * Which layout a document prints on.
 *
 * Authoring a template answers "what could this look like"; a routing rule answers "what does
 * a *sales invoice* actually print on". The service had the whole surface for this — create,
 * list, amend, and a `POST /resolve` that answers the question the renderer will ask — and the
 * console had no screen for any of it, so a tenant could design a document and never route one.
 */

const PAGE = 200;

export type RoutingRules = {
  rules: Wire['AssignmentItem'][];
  /**
   * More rules exist than this page holds. A count or a "nothing routed" read off an incomplete
   * page is a wrong answer, so a caller that tallies must check this first.
   */
  hasMore: boolean;
  loading: boolean;
  failure: RequestFailure | null;
  refresh: () => void;
};

/**
 * Every rule, active and inactive.
 *
 * `include_inactive` is always on: a rule is retired by being deactivated rather than deleted,
 * and hiding the retired ones makes "why does this still print the old design?" unanswerable
 * from the screen that owns the answer.
 *
 * `kind` narrows the read to one voucher kind, through the service's own `voucher_kind` filter —
 * the per-kind print page wants one kind's rules, not a page of everyone's to sift.
 */
export function useRoutingRules(company: string | undefined, kind?: string): RoutingRules {
  const read = useServiceRead<{ items: Wire['AssignmentItem'][]; page?: PageMeta }>(
    company
      ? `/v1/companies/${company}/assignments?include_inactive=true&limit=${PAGE}` +
          (kind ? `&voucher_kind=${encodeURIComponent(kind)}` : '')
      : undefined,
    designRequest,
    (value) => {
      if (!Array.isArray(value.items)) {
        throw { status: 502, message: 'The routing rules could not be verified.' };
      }
      for (const item of value.items) {
        assertDesignRow(item, company!);
        // A row of another kind in a one-kind list is the same breach as another company's.
        if (kind && item.voucher_kind !== kind) {
          throw { status: 502, message: 'The routing rules could not be verified.' };
        }
      }
    },
    'design service',
  );
  return {
    rules: read.data?.items ?? [],
    hasMore: !!read.data?.page?.has_more,
    loading: read.loading,
    failure: read.failure,
    refresh: read.refresh,
  };
}

/**
 * Where one design is used: the rules **in force** that name it (plan R4, 2026-11-04).
 *
 * The service's own `template_id` filter, so the designer reads the handful of rules that point at
 * this template rather than a company's whole routing table to sift. Retired rules are left out on
 * purpose — "used for" is what prints now; the history stays on the routing pages.
 */
export function useTemplateRules(company: string | undefined, templateId: string): RoutingRules {
  const read = useServiceRead<{ items: Wire['AssignmentItem'][]; page?: PageMeta }>(
    company ? `/v1/companies/${company}/assignments?template_id=${encodeURIComponent(templateId)}&limit=${PAGE}` : undefined,
    designRequest,
    (value) => {
      if (!Array.isArray(value.items)) {
        throw { status: 502, message: 'Where this design is used could not be verified.' };
      }
      for (const item of value.items) {
        assertDesignRow(item, company!);
        // A rule for another design, or a retired one, in this answer is not this design's use.
        if (item.template_id !== templateId || !item.is_active) {
          throw { status: 502, message: 'Where this design is used could not be verified.' };
        }
      }
    },
    'design service',
  );
  return {
    rules: read.data?.items ?? [],
    hasMore: !!read.data?.page?.has_more,
    loading: read.loading,
    failure: read.failure,
    refresh: read.refresh,
  };
}

/**
 * What a rule is conditional on, in words: "Currency INR · Tax category B2B", or "Any" for the
 * kind's default. One wording for the routing page and the per-kind print page, so the two never
 * describe the same rule differently.
 */
export function ruleConditions(rule: Wire['AssignmentItem']): string {
  return (
    [
      rule.voucher_type_id ? 'Specific voucher type' : null,
      rule.branch_id ? 'Specific branch' : null,
      rule.currency_code ? `Currency ${rule.currency_code}` : null,
      rule.customer_tax_category ? `Tax category ${rule.customer_tax_category}` : null,
      rule.specific_version_id ? 'Pinned to one version' : null,
    ]
      .filter(Boolean)
      .join(' · ') || 'Any'
  );
}

/**
 * Whether a rule is the kind's default: no voucher type, branch, currency or tax category.
 *
 * The service allows one *active* rule per exact set of those four, whichever template it names — so a
 * second default for a kind is a 409 until the first is retired, and a caller that offers to add one has
 * to know whether one is already in force.
 */
export function isDefaultRule(rule: Wire['AssignmentItem']): boolean {
  return !rule.voucher_type_id && !rule.branch_id && !rule.currency_code && !rule.customer_tax_category;
}

type Rule = Wire['AssignmentItem'];
type Template = Wire['TemplateItem'];

/** How many of the four criteria a rule pins — the service's own `specificity`. */
function pinned(rule: Rule): number {
  return [rule.voucher_type_id, rule.branch_id, rule.currency_code, rule.customer_tax_category].filter((value) => value !== null && value !== undefined).length;
}

/**
 * Resolution order, highest first: **priority**, then how many criteria the rule pins, then the newer
 * rule, then the larger id — the sort `design` applies to its candidates (`tasks/resolution.py`). Note
 * the order: a more specific rule with a lower priority loses to a less specific one with a higher.
 * Two screens sort and decide by this, so it lives here once.
 */
export function compareRules(left: Rule, right: Rule): number {
  return (
    right.priority - left.priority ||
    pinned(right) - pinned(left) ||
    Date.parse(right.created_at) - Date.parse(left.created_at) ||
    (right.id < left.id ? -1 : right.id > left.id ? 1 : 0)
  );
}

/**
 * Whether two rules are the same rule as far as the service's duplicate check is concerned: the same
 * company and the same four criteria. The service refuses a *second active* one when it is written,
 * but not when a retired one is switched back on — so a screen offering *Reinstate* has to ask.
 */
export function sameCriteria(left: Rule, right: Rule): boolean {
  return (
    left.company_id === right.company_id &&
    (left.voucher_type_id ?? null) === (right.voucher_type_id ?? null) &&
    (left.branch_id ?? null) === (right.branch_id ?? null) &&
    (left.currency_code ?? null) === (right.currency_code ?? null) &&
    (left.customer_tax_category ?? null) === (right.customer_tax_category ?? null)
  );
}

/** A template a document can resolve to: published, with a version. Anything else is skipped. */
export function isPublished(template: Template | undefined): boolean {
  return !!template && template.status === 'PUBLISHED' && !!template.current_version_id;
}

export type LayoutInUse = {
  /** The default rule that decides what an ordinary document prints on, or none: the standard layout. */
  winner: Rule | undefined;
  /** What would decide it were this company's own defaults retired — the organisation's, if it set one. */
  without: Rule | undefined;
  /** Some live rule is for a particular case (a currency, a tax category, a type, a branch). */
  special: boolean;
};

/**
 * What a voucher kind prints on, read off its rules the way the service resolves them.
 *
 * Only rules *in force on a published template* count: a retired rule routes nothing, and one on a
 * draft is skipped when a document resolves, so the next candidate applies. Of those, an ordinary
 * document — one that states none of the criteria a rule pins — can only match a **default** rule, and
 * the first by `compareRules` wins, whoever owns it: a default set for the whole organisation can
 * outrank this company's own. A voucher's page and the cards page both ask this, so they cannot
 * describe the same rules differently.
 */
export function layoutInUse(rules: Rule[], templates: ReadonlyMap<string, Template>, company: string): LayoutInUse {
  const live = rules.filter((rule) => rule.is_active && isPublished(templates.get(rule.template_id)));
  const defaults = live.filter(isDefaultRule).sort(compareRules);
  return {
    winner: defaults[0],
    without: defaults.find((rule) => rule.company_id !== company),
    special: live.some((rule) => !isDefaultRule(rule)),
  };
}

export type RuleDraft = {
  voucherKind: string;
  templateId: string;
  priority: string;
  currencyCode: string;
  customerTaxCategory: string;
  /** One voucher type of the kind; absent for every type. */
  voucherTypeId?: string;
};

export type RoutingWrites = {
  create: (draft: RuleDraft) => Promise<boolean>;
  setActive: (ruleId: string, isActive: boolean) => Promise<boolean>;
  setPriority: (ruleId: string, priority: number) => Promise<boolean>;
  pending: boolean;
  failure: string | null;
  /** The last write was refused as a duplicate of a rule already in force (409). */
  conflict: boolean;
  fields: Record<string, string> | null;
  clear: () => void;
};

export function useRoutingWrites(company: string): RoutingWrites {
  const command = useServiceCommand(designRequest, 'design service');
  const base = `/v1/companies/${company}/assignments`;

  const create = useCallback(
    async (draft: RuleDraft) => {
      const result = await command.execute<Wire['AssignmentItem']>(
        {
          path: base,
          method: 'POST',
          body: {
            voucher_kind: draft.voucherKind,
            template_id: draft.templateId,
            priority: Number(draft.priority) || 100,
            ...(draft.voucherTypeId ? { voucher_type_id: draft.voucherTypeId } : {}),
            // Omitted rather than sent empty: `null` and "absent" are the same rule to the
            // service, and `""` is a 422 on a field the person left alone.
            ...(draft.currencyCode ? { currency_code: draft.currencyCode.toUpperCase() } : {}),
            ...(draft.customerTaxCategory
              ? { customer_tax_category: draft.customerTaxCategory }
              : {}),
          },
        },
        (value) => {
          assertDesignRow(value as never, company);
        },
      );
      return result !== null;
    },
    [base, command, company],
  );

  const amend = useCallback(
    async (ruleId: string, body: Record<string, unknown>) => {
      const result = await command.execute<Wire['AssignmentItem']>(
        { path: `${base}/${ruleId}`, method: 'PATCH', body },
        (value) => {
          assertDesignRow(value as never, company, ruleId);
        },
      );
      return result !== null;
    },
    [base, command, company],
  );

  return useMemo(
    () => ({
      create,
      setActive: (ruleId, isActive) => amend(ruleId, { is_active: isActive }),
      setPriority: (ruleId, priority) => amend(ruleId, { priority }),
      pending: command.pending,
      failure: command.failure?.message ?? null,
      conflict: command.failure?.status === 409,
      fields: command.failure?.fields ?? null,
      clear: command.clear,
    }),
    [amend, command.clear, command.failure, command.pending, create],
  );
}

export type ResolvedRoute = Wire['ResolveTemplateResponse'];

export type RoutePreview = {
  run: (probe: { voucherKind: string; currencyCode: string; customerTaxCategory: string }) => Promise<void>;
  result: ResolvedRoute | null;
  pending: boolean;
  failure: string | null;
  reset: () => void;
};

/**
 * "What would a sales invoice in INR print on, right now?"
 *
 * The same `POST /resolve` the renderer will call, which is the point: a rule set that looks
 * right and resolves to something else is the failure this screen exists to prevent, and the
 * only honest way to check is to ask the thing that will be asked.
 *
 * `assignment_rule_id` being null is the answer worth surfacing — it means no rule matched and
 * the company's single published template was used instead, which is the difference between
 * *configured* and *defaulted*.
 */
export function useRoutePreview(company: string): RoutePreview {
  const command = useServiceCommand(designRequest, 'design service');
  const [result, setResult] = useState<ResolvedRoute | null>(null);

  const run = useCallback(
    async (probe: { voucherKind: string; currencyCode: string; customerTaxCategory: string }) => {
      const resolved = await command.execute<ResolvedRoute>(
        {
          path: `/v1/companies/${company}/resolve`,
          method: 'POST',
          body: {
            voucher_kind: probe.voucherKind,
            ...(probe.currencyCode ? { currency_code: probe.currencyCode.toUpperCase() } : {}),
            ...(probe.customerTaxCategory
              ? { customer_tax_category: probe.customerTaxCategory }
              : {}),
          },
        },
        (value) => {
          if (!value?.template_id || !value.version_id) {
            throw { status: 502, message: 'The resolved layout could not be verified.' };
          }
        },
      );
      setResult(resolved);
    },
    [command, company],
  );

  return useMemo(
    () => ({
      run,
      result,
      pending: command.pending,
      failure: command.failure?.message ?? null,
      reset: () => {
        setResult(null);
        command.clear();
      },
    }),
    [command, result, run],
  );
}
