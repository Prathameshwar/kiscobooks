'use client';

import { useState } from 'react';
import {
  Button,
  Card,
  CardBody,
  ErrorState,
  FormActions,
  Notice,
  PageHeader,
  PageNavigation,
  Select,
  Skeleton,
  TextField,
  asErrorStatus,
} from '@janso/ui';
import { goTo } from '../lib/navigate';
import { VOUCHER_KINDS, kindLabel, kindSummary, profileLabel } from '../lib/voucher-kinds';
import {
  NAME_MAX,
  TYPES_ROOT,
  typeHref,
  useKindCapabilities,
  useVoucherType,
  useVoucherTypeWrites,
  validateCreate,
  type CreateDraft,
} from '../lib/voucher-types';

/**
 * Starting a voucher type: a name, a code, and which kind of voucher it is a version of.
 *
 * The entry rules are not asked for here. A new type starts on the service's defaults and its own
 * page is where they are set — one decision per screen, and the page that follows says so. With
 * `from`, the type is a copy of an existing one: its kind and profile are fixed (a copy of a Sales
 * type that became a Receipt would not be a copy), and its rules come across as they are — the
 * original's own policy is sent with the request, because left out the service would intersect the
 * original with the *defaults* and hand back a copy with approval, starting mode and narration reset.
 *
 * Validation runs on the first attempt to save, not on the first keystroke; once it has run, each
 * field is told what is wrong as it is edited. The service validates again and a refusal it makes
 * — a code already taken, say — lands beside the field it is about.
 */
export function VoucherTypeEditor({ company, from }: { company: string; from?: string }) {
  const writes = useVoucherTypeWrites(company);
  const capabilities = useKindCapabilities(company);
  const source = useVoucherType(company, from);
  const [draft, setDraft] = useState<CreateDraft>({ code: '', name: '', kind: '', profile: '' });
  const [touched, setTouched] = useState(false);
  const [leaving, setLeaving] = useState(false);

  const copying = !!from;
  const profiles = capabilities.kinds.find((entry) => entry.kind === (copying ? source.data?.kind : draft.kind))?.profiles ?? [];
  const effective: CreateDraft =
    copying && source.data
      ? {
          ...draft,
          kind: source.data.kind ?? '',
          profile: source.data.profile ?? '',
          derivedFromRevisionId: source.data.revision_id ?? undefined,
          policy: source.data.policy ?? undefined,
        }
      : draft;
  const errors = touched ? validateCreate(effective) : {};
  // Held between a success and the page changing, so a second click cannot send a second request.
  const locked = writes.pending || writes.uncertain || leaving;
  const codeTaken = writes.status === 409 ? 'This code may already be in use — codes are unique within a company.' : undefined;

  const set = (patch: Partial<CreateDraft>) => {
    writes.clear();
    setDraft((current) => ({ ...current, ...patch }));
  };

  function chooseKind(kind: string) {
    const supported = capabilities.kinds.find((entry) => entry.kind === kind)?.profiles ?? [];
    set({ kind, profile: supported.includes('STANDARD') ? 'STANDARD' : (supported[0] ?? '') });
  }

  async function submit(): Promise<void> {
    setTouched(true);
    if (Object.keys(validateCreate(effective)).length) return;
    if (copying && (!effective.derivedFromRevisionId || !effective.policy)) return;
    const created = await writes.create(effective);
    if (created) {
      setLeaving(true);
      goTo(`${typeHref(created.id)}?saved=${copying ? 'copied' : 'created'}`);
    }
  }

  const back = { href: TYPES_ROOT, label: 'voucher types' };
  const crumbs = [{ label: 'Masters', href: '/masters' }, { label: 'Voucher types', href: TYPES_ROOT }, { label: copying ? 'Duplicate' : 'New' }];

  if (capabilities.failure || (copying && source.failure)) {
    const failure = (capabilities.failure ?? source.failure)!;
    return (
      <div className="janso-page">
        <PageNavigation back={back} breadcrumbs={crumbs} />
        <ErrorState status={asErrorStatus(failure.status)} detail={failure.message} />
      </div>
    );
  }

  const retired = copying && source.data?.status !== undefined && source.data.status !== 'ACTIVE';

  return (
    <div className="janso-page">
      <PageNavigation back={back} breadcrumbs={crumbs} />
      <PageHeader
        title={copying ? 'Duplicate voucher type' : 'New voucher type'}
        lede={
          copying
            ? 'A copy keeps the kind, profile and entry rules of the original. Give it its own name and code.'
            : 'Name a version of a kind of voucher. Its entry rules start on the defaults and are set on its own page afterwards.'
        }
      />
      {capabilities.loading || (copying && source.loading) ? (
        <Skeleton lines={4} />
      ) : retired ? (
        <Notice tone="warning">
          {source.data?.name} is retired, so it cannot be copied. <a className="janso-link" href={TYPES_ROOT}>Back to voucher types</a>
        </Notice>
      ) : (
        <Card>
          <CardBody>
            <div className="janso-flow">
              {copying && source.data ? (
                <Notice>
                  Copying <strong>{source.data.name}</strong> ({source.data.code}), revision {source.data.current_revision}.
                </Notice>
              ) : null}
              {copying && source.data && (!source.data.revision_id || !source.data.policy) ? (
                <Notice tone="danger">The original’s current revision and rules could not be read, so it cannot be copied. Reload and try again.</Notice>
              ) : null}
              <div className="janso-form-grid">
                <TextField
                  label="Name"
                  hint="What people see when they choose a type."
                  value={draft.name}
                  maxLength={NAME_MAX}
                  disabled={locked}
                  error={errors.name ?? writes.fields?.name}
                  onChange={(event) => set({ name: event.target.value })}
                />
                <TextField
                  label="Code"
                  hint="Letters, digits, hyphen or underscore. Unique in the company; saved in capitals."
                  value={draft.code}
                  maxLength={40}
                  disabled={locked}
                  error={errors.code ?? writes.fields?.code ?? codeTaken}
                  onChange={(event) => set({ code: event.target.value })}
                />
                <Select
                  label="Kind"
                  value={copying ? (source.data?.kind ?? '') : draft.kind}
                  placeholder="Choose a kind"
                  options={VOUCHER_KINDS.map((entry) => ({ value: entry.value, label: kindLabel(entry.value) }))}
                  hint={effective.kind ? `${kindSummary(effective.kind)}.` : 'The kind of voucher this type is a version of.'}
                  disabled={locked || copying}
                  error={errors.kind ?? writes.fields?.kind}
                  onChange={chooseKind}
                />
                <Select
                  label="Profile"
                  value={effective.profile}
                  placeholder={effective.kind ? 'Choose a profile' : 'Choose a kind first'}
                  options={profiles.map((profile) => ({ value: profile, label: profileLabel(profile) }))}
                  disabled={locked || copying || profiles.length === 0}
                  error={errors.profile ?? writes.fields?.profile}
                  onChange={(profile) => set({ profile })}
                />
              </div>
              {writes.uncertain ? (
                <Notice tone="warning">
                  The result of the last attempt is not known. Try the same request again — it will not create a second type.
                </Notice>
              ) : writes.failure ? (
                <Notice tone="danger">{writes.failure}</Notice>
              ) : null}
            </div>
          </CardBody>
          <FormActions>
            <a className="janso-btn janso-btn--ghost" href={TYPES_ROOT}>
              Cancel
            </a>
            <Button loading={writes.pending} disabled={writes.pending || leaving} onClick={() => void submit()}>
              {writes.uncertain ? 'Try again' : copying ? 'Create copy' : 'Create voucher type'}
            </Button>
          </FormActions>
        </Card>
      )}
    </div>
  );
}
