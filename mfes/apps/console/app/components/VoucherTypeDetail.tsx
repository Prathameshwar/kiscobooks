'use client';

import { useState } from 'react';
import {
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  ConfirmDialog,
  ErrorState,
  Notice,
  PageHeader,
  PageNavigation,
  ReviewList,
  Skeleton,
  asErrorStatus,
} from '@janso/ui';
import { goTo } from '../lib/navigate';
import { kindLabel, kindSummary, profileLabel } from '../lib/voucher-kinds';
import {
  ENTRY_MODES,
  PARTY_ROLES,
  SECTIONS,
  draftFromPolicy,
  otherControls,
  summarise,
} from '../lib/voucher-type-policy';
import { TYPES_ROOT, typeHref, useVoucherType, useVoucherTypeWrites } from '../lib/voucher-types';

const SAVED: Record<string, string> = {
  created: 'Voucher type created. Its entry rules start on the defaults — review them below and change what this type needs.',
  copied: 'Voucher type created as a copy. It has the original’s entry rules — review them below and change what this one needs.',
  revised: 'Entry rules saved as a new revision.',
  retired: 'Voucher type retired.',
};

/**
 * One voucher type: what it is, the entry rules in force, and the three things that can be done to
 * it — change the rules, copy it, retire it.
 *
 * Every action is offered only while it can succeed: the service refuses to revise or copy a
 * retired type, so a retired type shows its record and nothing to change. Retiring needs a typed
 * word because nothing reinstates a type — it stays on record for what used it and is no longer
 * offered for anything new.
 */
export function VoucherTypeDetail({
  company,
  id,
  canManage,
  saved,
}: {
  company: string;
  id: string;
  canManage: boolean;
  /** `?saved=` from the page that sent the reader here — created, revised or retired. */
  saved?: string;
}) {
  const read = useVoucherType(company, id);
  const writes = useVoucherTypeWrites(company);
  const [retiring, setRetiring] = useState(false);
  const [leaving, setLeaving] = useState(false);
  const type = read.data;
  const active = type?.status === 'ACTIVE';

  if (read.failure) {
    return (
      <div className="janso-page">
        <PageNavigation back={{ href: TYPES_ROOT, label: 'voucher types' }} />
        <ErrorState status={asErrorStatus(read.failure.status)} detail={read.failure.message} />
      </div>
    );
  }

  async function retire(): Promise<void> {
    if (!type) return;
    const done = await writes.retire(id, { expectedVersion: type.row_version });
    if (done) {
      setLeaving(true);
      goTo(`${typeHref(id)}?saved=retired`);
    }
  }

  const rules = draftFromPolicy(type?.policy ?? null);
  const others = otherControls(type?.policy ?? null);
  const approval = rules.approvalRequired ? (rules.selfApprovalAllowed ? 'Required; the person who raised it may approve it' : 'Required') : 'Not required';
  const required = [
    rules.narrationRequired ? 'Narration' : null,
    rules.lineDescriptionRequired ? 'Description on every line' : null,
    rules.supplierReferenceRequired ? 'Supplier reference' : null,
  ].filter((entry): entry is string => !!entry);

  return (
    <div className="janso-page">
      <PageNavigation
        back={{ href: TYPES_ROOT, label: 'voucher types' }}
        breadcrumbs={[{ label: 'Masters', href: '/masters' }, { label: 'Voucher types', href: TYPES_ROOT }, { label: type?.name ?? 'Voucher type' }]}
      />
      <PageHeader
        title={type?.name ?? 'Voucher type'}
        lede={type?.kind ? `${kindLabel(type.kind)} — ${kindSummary(type.kind).toLowerCase()}.` : undefined}
        actions={
          canManage && active ? (
            <>
              <a className="janso-btn janso-btn--primary" href={`${typeHref(id)}/edit`}>
                Edit rules
              </a>
              <a className="janso-btn janso-btn--ghost" href={`${TYPES_ROOT}/new?from=${id}`}>
                Duplicate
              </a>
              <Button variant="ghost" onClick={() => setRetiring(true)}>
                Retire
              </Button>
            </>
          ) : undefined
        }
      />
      {/* `hasOwn`, not a bare lookup: `?saved=__proto__` is an object, and `?saved=retired` on a live type is untrue. */}
      {saved && Object.hasOwn(SAVED, saved) && !(saved === 'retired' && active) ? <Notice tone="success">{SAVED[saved]}</Notice> : null}
      {type && !active ? (
        <Notice tone="warning">
          This voucher type is retired. It stays on record for the vouchers that used it, and is no longer offered for new ones.
        </Notice>
      ) : null}
      {type && active && !canManage ? (
        <Notice>Read-only access. The voucher type manage permission is required to change or retire a type.</Notice>
      ) : null}

      {read.loading || !type ? (
        <Skeleton lines={5} />
      ) : (
        <>
          <Card>
            <CardHeader title="Details" />
            <CardBody>
              <ReviewList
                items={[
                  { label: 'Code', value: type.code },
                  { label: 'Kind', value: type.kind ? kindLabel(type.kind) : '—' },
                  { label: 'Profile', value: type.profile ? profileLabel(type.profile) : '—' },
                  { label: 'Status', value: <Badge tone={active ? 'success' : 'neutral'}>{active ? 'Active' : 'Retired'}</Badge> },
                  { label: 'Revision', value: String(type.current_revision ?? 1) },
                  ...(type.derived_from_revision_id ? [{ label: 'Started from', value: 'A copy of another voucher type' }] : []),
                ]}
              />
            </CardBody>
          </Card>
          <Card>
            <CardHeader title="Entry rules" subtitle="What a voucher of this type has to follow." />
            <CardBody>
              <ReviewList
                items={[
                  { label: 'Entry modes', value: summarise(rules.allowedModes, ENTRY_MODES) },
                  { label: 'Starts in', value: ENTRY_MODES.find((mode) => mode.value === rules.defaultMode)?.label ?? '—' },
                  { label: 'Required sections', value: summarise(rules.requiredSections, SECTIONS, 'None') },
                  { label: 'Forbidden sections', value: summarise(rules.forbiddenSections, SECTIONS, 'None') },
                  { label: 'Most lines', value: rules.maxLines },
                  { label: 'Most parties', value: rules.maxParties },
                  { label: 'Days back', value: rules.backdateDays },
                  { label: 'Days ahead', value: rules.futureDays },
                  { label: 'Approval', value: approval },
                  { label: 'Required details', value: required.length ? required.join(', ') : 'None' },
                  { label: 'Party roles', value: summarise(rules.allowedPartyRoles, PARTY_ROLES) },
                  { label: 'Default narration', value: rules.defaultNarration || 'None' },
                ]}
              />
              {others.length ? (
                <Notice>
                  This type also carries {others.join(', ').toLowerCase()} controls. They are not edited here and are kept as they are when the rules above change.
                </Notice>
              ) : null}
            </CardBody>
          </Card>
        </>
      )}

      <ConfirmDialog
        open={retiring}
        title={`Retire ${type?.name ?? 'this voucher type'}?`}
        tone="danger"
        confirmLabel="Retire voucher type"
        confirmPhrase="retire"
        busy={writes.pending || leaving}
        error={
          writes.uncertain
            ? 'The result of the last attempt is not known. Confirm again to retry the same request — it will not retire anything twice.'
            : writes.failure && writes.status === 409
              ? `${writes.failure} Close this window to reload the type, then try again.`
              : writes.failure
        }
        onCancel={() => {
          if (writes.pending || leaving) return;
          // A conflict means this page is showing an old version: closing reloads it, so the next try is not stale too.
          if (writes.status === 409) read.refresh();
          writes.clear();
          setRetiring(false);
        }}
        onConfirm={() => void retire()}
      >
        <p>
          A retired voucher type stays on record for the vouchers that used it, but it cannot be revised or chosen for a new voucher, and it
          cannot be reinstated. Drafts still open on it cannot go further. To keep its rules, duplicate it first.
        </p>
      </ConfirmDialog>
    </div>
  );
}
