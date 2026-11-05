'use client';

import { useState } from 'react';
import { ConfirmDialog, EditorSelect } from '@janso/ui';
import type { components } from '@janso/api-client/vouchers';
import { useRoutingWrites, useTemplateRules, type RoutingRules } from '../../lib/design-routing';
import { useServiceRead } from '../../lib/service-resource';
import { kindLabel, kindSlug } from '../../lib/voucher-kinds';
import { assertTypeRow, offeredPurchaseTypes, typesPath, voucherTypeRequest } from '../../lib/voucher-types';

type Rule = RoutingRules['rules'][number];
type TypeRow = components['schemas']['ResourceItem'];

/** The kind a design can be assigned to from here: the one kind that prints from a design. */
const KIND = 'PURCHASE';
const PURCHASE_PRINT = `/documents/vouchers/${kindSlug(KIND)}`;

/**
 * A rule in plain words: "Purchase · all types", "Purchase · Goods bill", then anything else it is
 * conditional on. A type the reader cannot see is still a type, and is said to be one.
 */
export function usageLabel(rule: Rule, typeName: (id: string) => string | undefined): string {
  const type = rule.voucher_type_id ? (typeName(rule.voucher_type_id) ?? 'one voucher type') : 'all types';
  return [
    kindLabel(rule.voucher_kind),
    type,
    rule.branch_id ? 'one branch' : null,
    rule.currency_code ? `currency ${rule.currency_code}` : null,
    rule.customer_tax_category ? `tax category ${rule.customer_tax_category}` : null,
    rule.specific_version_id ? 'pinned to one version' : null,
  ]
    .filter(Boolean)
    .join(' · ');
}

/**
 * Where this design is used, and the control that uses it for a Purchase type (plan R4).
 *
 * It answers in the designer the question a person asks while drawing a layout — "what prints on
 * this?" — and lets them make it the layout for a Purchase type without leaving for the routing
 * page. Only rules **in force** are listed; a rule on a design that is not published yet is
 * skipped when a bill prints, so the panel says the standard layout still prints until it is.
 *
 * Authority is read piece by piece: without `design.assignment.read` the panel is not drawn at
 * all; without `manage` it lists and offers nothing; without `vouchers.read` the types cannot be
 * named or chosen, so only "all Purchase types" is offered. The service re-checks every write
 * against the actor's grants and the company.
 */
export function TemplateUsage({
  company,
  templateId,
  published,
  canRead,
  canManage,
  canReadTypes,
  onChanged,
}: {
  company: string;
  templateId: string;
  /** Whether the design has a live version: a rule on one that has none prints nothing yet. */
  published: boolean;
  /** `design.assignment.read`. */
  canRead: boolean;
  /** `design.assignment.manage`. */
  canManage: boolean;
  /** `vouchers.read`: naming and choosing Purchase types. */
  canReadTypes: boolean;
  /** Another view reads the same rules (the print checks), and is told when they change. */
  onChanged?: () => void;
}) {
  const routing = useTemplateRules(canRead ? company : undefined, templateId);
  const writes = useRoutingWrites(company);
  const types = useServiceRead<{ items: TypeRow[] }>(
    canRead && canReadTypes ? `${typesPath(company)}?kind=${KIND}&limit=200` : undefined,
    voucherTypeRequest,
    (value) => {
      if (!Array.isArray(value.items)) throw { status: 502, message: 'The Purchase types could not be verified.' };
      for (const row of value.items) {
        assertTypeRow(row, company);
        if (row.kind !== KIND) throw { status: 502, message: 'The Purchase types could not be verified.' };
      }
    },
    'voucher service',
  );
  const [assigning, setAssigning] = useState(false);
  const [choice, setChoice] = useState('');
  const [stopping, setStopping] = useState<Rule | null>(null);
  const [done, setDone] = useState<string | null>(null);

  if (!canRead) return null;

  const typeRows = types.data?.items ?? [];
  const typeName = (id: string) => {
    const row = typeRows.find((entry) => entry.id === id);
    return row ? (row.name ?? row.code ?? undefined) : undefined;
  };
  const offered = offeredPurchaseTypes(typeRows.filter((row) => row.status === 'ACTIVE'));
  const rules = routing.rules;
  const choiceLabel = choice ? `${kindLabel(KIND)} · ${typeName(choice) ?? 'one voucher type'}` : `${kindLabel(KIND)} · all types`;
  // Only this company's own rules are its to stop; an organisation-wide rule needs a tenant grant.
  const ownRule = (rule: Rule) => rule.company_id === company;

  async function assign(): Promise<void> {
    setDone(null);
    const label = choiceLabel;
    const ok = await writes.create({
      voucherKind: KIND,
      templateId,
      priority: '100',
      currencyCode: '',
      customerTaxCategory: '',
      ...(choice ? { voucherTypeId: choice } : {}),
    });
    if (!ok) return;
    setAssigning(false);
    setChoice('');
    setDone(`Now used for ${label}.`);
    routing.refresh();
    onChanged?.();
  }

  async function stop(): Promise<void> {
    if (!stopping) return;
    setDone(null);
    const label = usageLabel(stopping, typeName);
    if (!(await writes.setActive(stopping.id, false))) return;
    setStopping(null);
    setDone(`No longer used for ${label}.`);
    routing.refresh();
    onChanged?.();
  }

  const failure = writes.conflict
    ? `Another design is already used for ${choiceLabel}. Stop using that one first — on Purchase print — then use this design.`
    : writes.failure;

  return (
    <section className="janso-editor__group" aria-labelledby="designer-usage">
      <p className="janso-editor__group-label" id="designer-usage">
        Used for
      </p>
      {routing.loading ? (
        <p className="janso-editor__row-hint" role="status">
          Checking where this design is used…
        </p>
      ) : routing.failure ? (
        <div className="janso-editor__publish">
          <p className="janso-editor__row-hint" role="alert">
            {routing.failure.status === 403
              ? 'You do not have access to see where designs are used.'
              : `Where this design is used could not be read. ${routing.failure.message}`}
          </p>
          <button type="button" className="janso-editor__button" onClick={routing.refresh}>
            Try again
          </button>
        </div>
      ) : rules.length === 0 ? (
        <p className="janso-editor__row-hint" data-testid="usage-empty">
          Not used for any voucher yet — the standard layout prints.
        </p>
      ) : (
        <>
          <ul className="janso-editor__versions" aria-label="Vouchers that print on this design">
            {rules.map((rule) => {
              const label = usageLabel(rule, typeName);
              return (
                <li key={rule.id}>
                  <div className="janso-editor__version">
                    <span className="janso-editor__version-head">{label}</span>
                    {!ownRule(rule) ? (
                      <span className="janso-editor__version-meta">Set for your whole organisation</span>
                    ) : null}
                    {canManage && ownRule(rule) ? (
                      <button
                        type="button"
                        className="janso-editor__button"
                        disabled={writes.pending}
                        aria-label={`Stop using for ${label}`}
                        onClick={() => {
                          writes.clear();
                          setDone(null);
                          setStopping(rule);
                        }}
                      >
                        Stop using
                      </button>
                    ) : null}
                  </div>
                </li>
              );
            })}
          </ul>
          {routing.hasMore ? (
            <p className="janso-editor__row-hint">More rules use this design than are shown here.</p>
          ) : null}
          {!published ? (
            <p className="janso-editor__row-hint" data-testid="usage-unpublished">
              This design is not published yet, so these vouchers keep printing on the standard layout until it is.
            </p>
          ) : null}
        </>
      )}

      {done ? (
        <p className="janso-editor__row-hint" role="status">
          {done}
        </p>
      ) : null}

      {canManage && !routing.loading && !routing.failure ? (
        assigning ? (
          <div className="janso-editor__publish">
            <EditorSelect
              label="Purchase vouchers to use this design for"
              value={choice}
              options={[
                { value: '', label: 'All Purchase types' },
                ...offered.map((row) => ({ value: row.id, label: row.name ?? row.code ?? 'Unnamed type' })),
              ]}
              disabled={writes.pending}
              onChange={(value) => {
                writes.clear();
                setChoice(value);
              }}
            />
            {!canReadTypes ? (
              <p className="janso-editor__row-hint">Choosing one Purchase type needs access to read voucher types.</p>
            ) : types.loading ? (
              <p className="janso-editor__row-hint" role="status">
                Loading Purchase types…
              </p>
            ) : types.failure ? (
              <p className="janso-editor__row-hint">The Purchase types could not be read: {types.failure.message}</p>
            ) : null}
            {failure ? (
              <p className="janso-editor__row-hint" role="alert">
                {failure}
                {writes.conflict ? (
                  <>
                    {' '}
                    <a className="janso-link" href={PURCHASE_PRINT}>
                      Open Purchase print
                    </a>
                  </>
                ) : null}
              </p>
            ) : null}
            <button type="button" className="janso-editor__button" disabled={writes.pending} onClick={() => void assign()}>
              {writes.pending ? 'Saving…' : `Use for ${choiceLabel}`}
            </button>
            <button
              type="button"
              className="janso-editor__button"
              disabled={writes.pending}
              onClick={() => {
                writes.clear();
                setAssigning(false);
                setChoice('');
              }}
            >
              Cancel
            </button>
          </div>
        ) : (
          <button
            type="button"
            className="janso-editor__button"
            onClick={() => {
              writes.clear();
              setDone(null);
              setAssigning(true);
            }}
          >
            Use for a Purchase type…
          </button>
        )
      ) : null}

      <ConfirmDialog
        open={!!stopping}
        title={stopping ? `Stop using this design for ${usageLabel(stopping, typeName)}?` : 'Stop using this design?'}
        confirmLabel="Stop using"
        busy={writes.pending}
        error={stopping ? writes.failure : null}
        onCancel={() => {
          if (writes.pending) return;
          writes.clear();
          setStopping(null);
        }}
        onConfirm={() => void stop()}
      >
        <p>
          Those vouchers print on the standard layout again, or on another design chosen for them. The design and its
          versions are kept, and you can use it again later.
        </p>
      </ConfirmDialog>
    </section>
  );
}
