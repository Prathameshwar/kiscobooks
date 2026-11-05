'use client';
import { useEffect, useState } from 'react';
import {
  Button,
  Card,
  CardBody,
  CardHeader,
  ConfirmDialog,
  Notice,
  PageHeader,
  ReviewList,
  TextField,
  formatDate,
  useDisplayConfig,
} from '@janso/ui';
import {
  AccessFocusErrors,
  useAccessDraft,
} from '../../components/AccessCommon';
import { PlatformHistory } from '../../components/PlatformHistory';
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
  type AdministratorCommand,
  type AdministratorReceipt,
} from '../../lib/platform-access';
import { useServiceCommand, useServiceRead } from '../../lib/service-resource';
import { PlatformAccessNavigation } from './PlatformAccessOverview';
import { AdministratorPasswordRecovery } from './AdministratorPasswordRecovery';

const labels = {
  suspend: 'Deactivate administrator access',
  restore: 'Activate administrator access',
  revoke: 'Revoke administrator role',
  resend_invitation: 'Resend invitation',
  edit: 'Edit administrator',
};
export function PlatformAdministratorDetail({
  tenantId,
  userId,
  canManage,
  back,
}: {
  tenantId: string;
  userId: string;
  canManage: boolean;
  back?: string;
}) {
  const directory = administratorReturn(back, tenantId),
    href = administratorLink(
      administratorRoot + '/' + userId,
      tenantId,
      directory,
    );
  const display = useDisplayConfig();
  const read = useServiceRead<Administrator>(
    administratorPath(tenantId, userId),
    platformAccessReader,
    (value) => verifyAdministrator(value, tenantId, userId),
    'platform access service',
  );
  const command = useServiceCommand(
    platformAccessReader,
    'platform access service',
  );
  const [action, setAction] = useState<AdministratorCommand['action'] | null>(
      null,
    ),
    [reason, setReason] = useState('');
  const [fields, setFields] = useState<Record<string, string>>({}),
    [message, setMessage] = useState(''),
    [invitation, setInvitation] = useState<string | null>(null),
    [copy, setCopy] = useState('');
  const [recoveryPending, setRecoveryPending] = useState(false);
  const guard = useAccessDraft(
      (!!action && !!reason) || command.uncertain,
      command.pending || recoveryPending,
    ),
    row = read.data;
  useEffect(() => {
    if (!row || !['#administrator-actions', '#password-recovery'].includes(window.location.hash)) return;
    const section = document.getElementById(window.location.hash.slice(1));
    section?.scrollIntoView?.({ block: 'start' });
    section?.querySelector<HTMLElement>('button:not(:disabled)')?.focus({ preventScroll: true });
  }, [row]);
  const canWrite =
    canManage &&
    !!row &&
    row.tenant.status !== 'closed' &&
    ['active', 'invited', 'suspended'].includes(row.status);
  function begin(next: AdministratorCommand['action']) {
    if (recoveryPending) return;
    command.clear();
    setReason('');
    setFields({});
    setAction(next);
    setMessage('');
  }
  async function save() {
    if (!row || !action || command.pending) return;
    if (
      reason.trim().length < 3 ||
      reason.length > 500 ||
      /[\x00-\x1f\x7f]/.test(reason)
    ) {
      setFields({
        reason:
          'Enter a reason with 3–500 characters and no control characters.',
      });
      return;
    }
    const body: AdministratorCommand = {
      action,
      reason: reason.trim(),
      expected_updated_at: row.updated_at,
      expected_assignment_updated_at: row.assignment_updated_at,
    };
    const result = await command.execute<AdministratorReceipt>(
      {
        path: administratorPath(tenantId, userId) + '/commands',
        method: 'POST',
        body,
      },
      (value) => verifyReceipt(value, tenantId, userId),
    );
    if (result) {
      setMessage(action === 'suspend' ? 'Administrator access deactivated. Existing records are retained.' : action === 'restore' ? result.status === 'invited' ? 'Administrator role restored. Invitation acceptance is still required.' : 'Administrator access activated.' : labels[action] + ' completed.');
      setInvitation(result.invitation_url ?? null);
      setAction(null);
      setReason('');
      read.refresh();
    }
  }
  return (
    <div className="janso-page">
      <PlatformAccessNavigation
        tenantId={tenantId}
        title={row?.display_name ?? 'Administrator details'}
        back={directory}
        onLeave={guard.leave}
      />
      <PageHeader
        title={row?.display_name ?? 'Administrator details'}
        lede={
          row
            ? `Tenant administrator for ${row.tenant.name}`
            : 'Review this tenant-administrator account and assignment.'
        }
        actions={
          canWrite ? (
            <a
              className="janso-btn janso-btn--primary"
              href={administratorLink(
                administratorRoot + '/' + userId + '/edit',
                tenantId,
                directory,
              )}
              onClick={guard.leave}
            >
              Edit administrator
            </a>
          ) : undefined
        }
      />
      <PlatformError value={read.failure} returnTo={href} />
      {read.failure && ![401, 403].includes(read.failure.status) && (
        <Button onClick={read.refresh}>Retry loading</Button>
      )}
      {read.loading && <p role="status">Loading administrator details…</p>}
      {message && <Notice tone="success">{message}</Notice>}
      {row && (
        <>
          <Card>
            <CardHeader
              title="Administrator account"
              subtitle="Changes are audited in the platform and selected tenant."
            />
            <CardBody>
              <div className="janso-flow">
                <ReviewList
                  items={[
                    { label: 'Tenant', value: row.tenant.name },
                    { label: 'Name', value: row.display_name },
                    { label: 'Email', value: row.email },
                    { label: 'Account status', value: row.status },
                    {
                      label: 'Role',
                      value: (
                        <a
                          className="janso-link"
                          href={administratorLink(
                            '/platform/access/role',
                            tenantId,
                            directory,
                          )}
                          onClick={guard.leave}
                        >
                          Tenant administrator
                        </a>
                      ),
                    },
                    {
                      label: 'Assignment',
                      value: row.assignment_active ? 'Granted' : 'Revoked',
                    },
                    { label: 'Scope', value: 'Tenant and all its companies' },
                    {
                      label: 'Valid from',
                      value: formatDate(row.valid_from, display),
                    },
                    {
                      label: 'Valid to',
                      value: row.valid_to
                        ? formatDate(row.valid_to, display)
                        : 'No expiry',
                    },
                  ]}
                />
                {row.last_active_administrator && (
                  <Notice tone="info">
                    This is the last active administrator. Invite and activate
                    another administrator before deactivating this account’s access or
                    revoking its role.
                  </Notice>
                )}
                {!row.assignment_active && (
                  <Notice tone="warning">
                    The tenant-administrator role is revoked. Other role
                    assignments, if any, remain governed by the tenant.
                  </Notice>
                )}
                {row.tenant.status !== 'active' && (
                  <Notice tone="info">
                    Tenant status: {row.tenant.status}. Account restoration does
                    not restore a suspended tenant.
                  </Notice>
                )}
              </div>
            </CardBody>
          </Card>
          {canWrite && (
            <div id="administrator-actions"><Card>
              <CardHeader
                title="Administrator actions"
                subtitle="A reason and recent sign-in are required for each change."
              />
              <div className="janso-page-navigation">
                {row.status === 'invited' && row.assignment_active && (
                  <Button
                    variant="ghost"
                    disabled={command.pending || command.uncertain || recoveryPending}
                    onClick={() => begin('resend_invitation')}
                  >
                    Resend invitation
                  </Button>
                )}
                {row.status === 'active' && (
                  <Button
                    variant="ghost"
                    disabled={
                      row.last_active_administrator ||
                      command.pending ||
                      recoveryPending ||
                      command.uncertain
                    }
                    onClick={() => begin('suspend')}
                  >
                    Deactivate administrator access
                  </Button>
                )}
                {(row.status === 'suspended' || !row.assignment_active) && (
                  <Button
                    variant="ghost"
                    disabled={command.pending || command.uncertain || recoveryPending}
                    onClick={() => begin('restore')}
                  >
                    Activate administrator access
                  </Button>
                )}
                {row.assignment_active && (
                  <Button
                    variant="danger"
                    disabled={
                      row.last_active_administrator ||
                      command.pending ||
                      recoveryPending ||
                      command.uncertain
                    }
                    onClick={() => begin('revoke')}
                  >
                    Revoke administrator role
                  </Button>
                )}
              </div>
            </Card></div>
          )}
          {canManage && <AdministratorPasswordRecovery key={row.id + row.updated_at + row.assignment_updated_at} administrator={row} returnTo={href} disabled={command.pending || command.uncertain} onBusyChange={setRecoveryPending} onReview={read.refresh} />}
          {invitation && (
            <Card>
              <CardHeader
                title="Administrator invitation"
                subtitle="Share privately. Acceptance requires the invited administrator’s verified sign-in."
              />
              <TextField label="Invitation link" value={invitation} readOnly />
              <Button
                variant="ghost"
                onClick={async () => {
                  try {
                    await navigator.clipboard.writeText(invitation);
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
          <PlatformHistory
            entityType="tenant"
            entityId={tenantId}
            revision={row.updated_at}
          />
        </>
      )}
      <ConfirmDialog
        open={!!action}
        title={action ? labels[action] + '?' : ''}
        confirmLabel={
          command.uncertain
            ? 'Retry same request'
            : action
              ? labels[action]
              : 'Confirm'
        }
        tone={
          action === 'revoke' || action === 'suspend' ? 'danger' : 'default'
        }
        busy={command.pending}
        onConfirm={save}
        onCancel={() => {
          if (!command.pending && !command.uncertain) {
            setAction(null);
            setReason('');
            command.clear();
          }
        }}
      >
        <p>
          {action === 'suspend'
            ? 'This account will lose sign-in access across the tenant. Its records and assignments are retained.'
            : action === 'revoke'
              ? 'Remove only the tenant-administrator assignment. Other roles are unchanged. A pending administrator invitation will be cancelled.'
              : action === 'restore'
                ? row?.status === 'invited' ? 'Restore the tenant-administrator assignment. Invitation acceptance is still required before this account can sign in.' : 'Restore this account and grant the fixed tenant-administrator role across the selected tenant.'
                : 'Issue a new invitation and cancel the previous pending link.'}
        </p>
        <TextField
          label="Reason"
          value={reason}
          required
          minLength={3}
          maxLength={500}
          error={fields.reason}
          disabled={command.pending || command.uncertain}
          onChange={(event) => {
            setReason(event.target.value);
            setFields({});
          }}
        />
        <AccessFocusErrors fields={fields} />
        <PlatformError value={command.failure} returnTo={href} />
        {command.uncertain && (
          <Notice tone="warning">
            The result could not be confirmed. Your request is retained; retry
            it to confirm the result.
          </Notice>
        )}
        {command.failure?.status === 409 && (
          <Button
            type="button"
            variant="ghost"
            onClick={() => {
              setAction(null);
              setReason('');
              command.clear();
              read.refresh();
            }}
          >
            Refresh and review
          </Button>
        )}
      </ConfirmDialog>
      {guard.confirmation}
    </div>
  );
}
