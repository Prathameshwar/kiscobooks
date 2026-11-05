'use client';
import { useEffect, useState } from 'react';
import {
  Button,
  Card,
  CardBody,
  CardHeader,
  FormActions,
  FormLayout,
  Notice,
  PageHeader,
  SectionHeader,
  TextField,
} from '@janso/ui';
import {
  AccessFocusErrors,
  useAccessDraft,
} from '../../components/AccessCommon';
import { PlatformError } from '../../lib/platform-api';
import {
  administratorLink,
  administratorPath,
  administratorReturn,
  administratorRoot,
  platformAccessReader,
  verifyAdministrator,
  verifyReceipt,
  type Administrator,
  type AdministratorReceipt,
  type AdministratorTenant,
} from '../../lib/platform-access';
import { useServiceCommand, useServiceRead } from '../../lib/service-resource';
import { useEditorDraft } from '../useEditorDraft';
import { PlatformAccessNavigation } from './PlatformAccessOverview';

const initial = { display_name: '', email: '', reason: '' };
export function PlatformAdministratorEditor({
  tenantId,
  userId,
  back,
}: {
  tenantId: string;
  userId?: string;
  back?: string;
}) {
  const directory = administratorReturn(back, tenantId),
    detailHref = userId
      ? administratorLink(administratorRoot + '/' + userId, tenantId, directory)
      : directory;
  const href = administratorLink(
    administratorRoot + '/' + (userId ? userId + '/edit' : 'new'),
    tenantId,
    directory,
  );
  const tenant = useServiceRead<AdministratorTenant>(
    '/v1/platform/access/tenants/' + tenantId,
    platformAccessReader,
    (value) => {
      if (value.id !== tenantId)
        throw {
          status: 502,
          message: 'The selected tenant could not be verified.',
        };
    },
    'platform access service',
  );
  const read = useServiceRead<Administrator>(
    userId ? administratorPath(tenantId, userId) : undefined,
    platformAccessReader,
    (value) => verifyAdministrator(value, tenantId, userId!),
    'platform access service',
  );
  const editor = useEditorDraft(
      tenantId + ':administrator:' + (userId ?? 'new'),
      initial,
    ),
    { draft } = editor;
  const command = useServiceCommand(
    platformAccessReader,
    'platform access service',
  );
  const [fields, setFields] = useState<Record<string, string>>({}),
    [saved, setSaved] = useState<AdministratorReceipt | null>(null),
    [copy, setCopy] = useState('');
  useEffect(() => {
    if (read.data)
      editor.populate({
        display_name: read.data.display_name,
        email: read.data.email,
        reason: '',
      });
  }, [read.data]);
  const guard = useAccessDraft(
    editor.touched.current || command.uncertain,
    command.pending,
  );
  const loading = tenant.loading || read.loading,
    blocked =
      loading ||
      !!tenant.failure ||
      !!read.failure ||
      tenant.data?.status === 'closed' ||
      (!!userId &&
        !['active', 'invited', 'suspended'].includes(
          read.data?.status ?? '',
        )) ||
      !!saved;
  function change(field: keyof typeof initial, value: string) {
    editor.change({ [field]: value });
    setFields((current) => ({ ...current, [field]: '' }));
  }
  async function save() {
    if (blocked || command.pending || !tenant.data || (userId && !read.data))
      return;
    const invalid: Record<string, string> = {};
    if (
      !draft.display_name.trim() ||
      draft.display_name.length > 100 ||
      /[\x00-\x1f\x7f]/.test(draft.display_name)
    )
      invalid.display_name =
        'Enter a name with 1–100 characters and no control characters.';
    if (
      !userId &&
      (draft.email.length > 320 ||
        !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(draft.email.trim()))
    )
      invalid.email = 'Enter a valid email address.';
    if (
      draft.reason.trim().length < 3 ||
      draft.reason.length > 500 ||
      /[\x00-\x1f\x7f]/.test(draft.reason)
    )
      invalid.reason =
        'Enter a reason with 3–500 characters and no control characters.';
    setFields(invalid);
    if (Object.keys(invalid).length) return;
    const body =
      userId && read.data
        ? {
            action: 'edit',
            display_name: draft.display_name.trim(),
            reason: draft.reason.trim(),
            expected_updated_at: read.data.updated_at,
            expected_assignment_updated_at: read.data.assignment_updated_at,
          }
        : {
            display_name: draft.display_name.trim(),
            email: draft.email.trim().toLowerCase(),
            reason: draft.reason.trim(),
          };
    const result = await command.execute<AdministratorReceipt>(
      {
        path: administratorPath(tenantId, userId) + (userId ? '/commands' : ''),
        method: 'POST',
        body,
      },
      (value) => verifyReceipt(value, tenantId, userId),
    );
    if (result) {
      setSaved(result);
      editor.saved();
    }
  }
  return (
    <div className="janso-page">
      <PlatformAccessNavigation
        tenantId={tenantId}
        title={userId ? 'Edit administrator' : 'Invite administrator'}
        back={detailHref}
        onLeave={guard.leave}
      />
      <PageHeader
        title={userId ? 'Edit administrator' : 'Invite administrator'}
        lede={
          tenant.data
            ? `${tenant.data.name} · Tenant administrator`
            : 'Loading selected tenant…'
        }
      />
      <PlatformError value={tenant.failure ?? read.failure} returnTo={href} />
      {(tenant.failure || read.failure) && (
        <Button
          onClick={() => {
            tenant.refresh();
            read.refresh();
          }}
        >
          Retry loading
        </Button>
      )}
      {loading && <p role="status">Loading administrator form…</p>}
      {editor.restored && (
        <Notice tone="info">
          Your draft was restored. Review it before saving.
        </Notice>
      )}
      {tenant.data?.status === 'closed' && (
        <Notice tone="info">
          This tenant is closed. Administrator access cannot be changed.
        </Notice>
      )}
      {saved && (
        <Notice tone="success">
          {userId
            ? 'Administrator updated.'
            : 'Administrator invited. The invitation must be accepted using verified sign-in.'}{' '}
          <a
            className="janso-link"
            href={administratorLink(
              administratorRoot + '/' + saved.administrator_id,
              tenantId,
              directory,
            )}
          >
            View administrator
          </a>
        </Notice>
      )}
      {tenant.data &&
        !loading &&
        !tenant.failure &&
        !read.failure &&
        (!userId || read.data) && (
          <FormLayout aside={<><SectionHeader title="Administrator access" /><p className="janso-fine">The fixed Tenant Administrator role applies across this tenant. Company business permissions are assigned separately.</p><p className="janso-fine">The sign-in email stays fixed when editing an existing administrator. Access changes are audited.</p></>}>
              <form
                aria-label="Tenant administrator editor"
                noValidate
                onSubmit={(event) => {
                  event.preventDefault();
                  void save();
                }}
              >
                <Card><CardBody><div className="janso-flow"><SectionHeader title="Administrator details" description="Review the profile and record the reason for this change." /><div className="janso-form-grid">
                  <TextField
                    name="display_name"
                    label="Administrator name"
                    required
                    maxLength={100}
                    value={draft.display_name}
                    error={
                      fields.display_name ||
                      command.failure?.fields?.display_name
                    }
                    disabled={blocked || command.pending || command.uncertain}
                    onChange={(event) =>
                      change('display_name', event.target.value)
                    }
                  />
                  <TextField
                    name="email"
                    label="Email address"
                    type="email"
                    required
                    value={draft.email}
                    maxLength={320}
                    error={fields.email || command.failure?.fields?.email}
                    readOnly={!!userId}
                    disabled={
                      !userId &&
                      (blocked || command.pending || command.uncertain)
                    }
                    onChange={(event) => change('email', event.target.value)}
                    hint={
                      userId
                        ? 'Email identifies the verified sign-in account and is read-only here.'
                        : 'Use the administrator’s own email. An existing user email cannot be promoted through this invitation.'
                    }
                  />
                  <TextField
                    label="Assigned role"
                    value="Tenant administrator"
                    readOnly
                    hint="Tenant-wide organisation, company and access administration. Review its permissions using the links above."
                  />
                  <TextField
                    name="reason"
                    label="Reason"
                    required
                    minLength={3}
                    maxLength={500}
                    value={draft.reason}
                    error={fields.reason || command.failure?.fields?.reason}
                    disabled={blocked || command.pending || command.uncertain}
                    onChange={(event) => change('reason', event.target.value)}
                  />
                </div>
                <AccessFocusErrors fields={fields} />
                <PlatformError
                  value={command.failure}
                  returnTo={href}
                  onNavigate={() => editor.preserve()}
                />
                {command.uncertain && (
                  <Notice tone="warning">
                    The result could not be confirmed. Your values are retained.
                    Retry the same request to confirm the result.
                  </Notice>
                )}
                {command.failure?.status === 409 && (
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={() => {
                      command.clear();
                      read.refresh();
                      tenant.refresh();
                    }}
                  >
                    Refresh and review
                  </Button>
                )}
                </div></CardBody><FormActions
                  cancel={{
                    href: detailHref,
                    label: saved ? 'Back to administrator' : 'Cancel',
                    onClick: guard.leave,
                  }}
                >
                  <Button
                    type="submit"
                    disabled={blocked || command.pending}
                    loading={command.pending}
                  >
                    {command.uncertain
                      ? 'Retry same request'
                      : userId
                        ? 'Save administrator'
                        : 'Send invitation'}
                  </Button>
                </FormActions></Card>
              </form>
          </FormLayout>
        )}
      {saved?.invitation_url && (
        <Card>
          <CardHeader
            title="Administrator invitation"
            subtitle="Share privately with this administrator. The link expires after three days and requires verified sign-in."
          />
          <TextField
            label="Invitation link"
            readOnly
            value={saved.invitation_url}
          />
          <Button
            variant="ghost"
            onClick={async () => {
              try {
                await navigator.clipboard.writeText(saved.invitation_url!);
                setCopy('Invitation link copied.');
              } catch {
                setCopy('Select and copy the invitation link above.');
              }
            }}
          >
            Copy invitation link
          </Button>
          {copy && <p role="status">{copy}</p>}
        </Card>
      )}
      {guard.confirmation}
    </div>
  );
}
