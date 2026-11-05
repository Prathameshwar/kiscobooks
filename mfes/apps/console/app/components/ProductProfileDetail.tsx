'use client';
import { useState } from 'react';
import {
  Button,
  Card,
  CardBody,
  ConfirmDialog,
  Menu,
  Notice,
  PageHeader,
  ReviewList,
} from '@janso/ui';
import type { MasterConfig, MasterRow } from '../lib/catalog-masters';
import { masterRequest, useMasterRecord } from '../lib/catalog-master-api';
import { useServiceCommand } from '../lib/service-resource';
import {
  profileBase,
  profileLink,
  profileReceipt,
  profileReturn,
  profileVisible,
  profileWritable,
} from '../lib/product-profiles';
import type {
  ProductProfileAccess,
  ProductProfileResource,
} from '../lib/product-profile-resources';
import {
  ProfileExplanation,
  ProfileFailure,
  ProfileNavigation,
} from './ProductProfileCommon';
import { ProductProfileHistory } from './ProductProfileHistory';
import { useAccessDraft } from './AccessCommon';
export function ProductProfileDetail({
  company,
  config,
  id,
  returnTo,
  canManage,
  access,
}: {
  company: string;
  config: MasterConfig;
  id: string;
  returnTo?: string;
  canManage: boolean;
  access: ProductProfileAccess;
}) {
  const noun =
    config.resource === 'manufacturing-routes'
      ? 'route'
      : config.resource === 'manufacturing-operations'
        ? 'operation'
        : 'profile';
  const root = '/masters/' + config.resource,
    back = profileReturn(returnTo, root),
    here = profileLink(root + '/' + id, back),
    record = useMasterRecord(company, config, id, false),
    row = record.row;
  const command = useServiceCommand(masterRequest, 'profile availability'),
    guard = useAccessDraft(command.uncertain, command.pending);
  const [action, setAction] = useState<'activate' | 'deactivate' | null>(null),
    [frozen, setFrozen] = useState<{
      action: 'activate' | 'deactivate';
      version: number;
    } | null>(null),
    [notice, setNotice] = useState(''),
    [reload, setReload] = useState(false);
  const version =
      Number.isSafeInteger(row?.row_version) &&
      Number(row?.row_version) > 0 &&
      profileVisible(record.fields, 'row_version'),
    canEdit =
      canManage &&
      version &&
      ['code', 'name'].some((key) => profileWritable(record.fields, [key])),
    canLifecycle =
      canManage &&
      !!row &&
      version &&
      typeof row.is_active === 'boolean' &&
      profileWritable(record.fields, ['is_active']);
  const reason = command.blocked
    ? command.pending
      ? 'An action is being saved.'
      : command.uncertain
        ? 'Retry the unconfirmed action first.'
        : 'Reload and review before another action.'
    : undefined;
  async function run(value: {
    action: 'activate' | 'deactivate';
    version: number;
  }) {
    if (!canLifecycle || command.pending) return;
    setFrozen(value);
    setNotice('');
    const current = await command.execute<MasterRow>(
      {
        path: profileBase(
          company,
          config.resource + '/' + id + '/' + value.action,
        ),
        method: 'POST',
        body: { expected_version: value.version },
      },
      (row) => {
        profileReceipt(row, company, id, value.version);
        if (typeof row.is_active !== 'boolean')
          throw {
            status: 502,
            message:
              'The availability result could not be verified. Retry the same action.',
          };
      },
    );
    setAction(null);
    if (current) {
      record.setRow(current);
      setFrozen(null);
      setNotice(
        current.is_active === (value.action === 'activate')
          ? (noun === 'route'
              ? 'Route '
              : noun === 'operation'
                ? 'Operation '
                : 'Profile ') +
              (current.is_active ? 'activated' : 'deactivated') +
              ' successfully.'
          : 'The action completed. Availability has since changed; review the current profile.',
      );
    }
  }
  return (
    <div className="janso-page">
      <ProfileNavigation
        resource={config.resource as ProductProfileResource}
        title={row?.name ?? config.title}
        back={back}
        access={access}
        onLeave={guard.leave}
      />
      <PageHeader
        title={row?.name ?? config.singular + ' details'}
        actions={
          row &&
          (canEdit || canLifecycle) && (
            <Menu
              label={
                noun === 'route'
                  ? 'Route actions'
                  : noun === 'operation'
                    ? 'Operation actions'
                    : 'Profile actions'
              }
              items={[
                ...(canEdit
                  ? [
                      {
                        id: 'edit',
                        label: 'Edit details',
                        href: profileLink(root + '/' + id + '/edit', here),
                        disabledReason: reason,
                      },
                    ]
                  : []),
                ...(canLifecycle
                  ? [
                      {
                        id: row.is_active ? 'deactivate' : 'activate',
                        label: row.is_active ? 'Deactivate' : 'Activate',
                        destructive: row.is_active === true,
                        disabledReason: reason,
                      },
                    ]
                  : []),
              ]}
              onSelect={(value) => {
                if (!command.blocked && value !== 'edit')
                  setAction(value as 'activate' | 'deactivate');
              }}
            />
          )
        }
      />
      <ProfileFailure failure={record.failure} retry={record.refresh} />
      <ProfileFailure failure={command.failure} write={command.uncertain} />
      {command.failure && !command.uncertain && (
        <Button variant="ghost" onClick={() => setReload(true)}>
          Reload and review
        </Button>
      )}
      {command.uncertain && frozen && (
        <Button disabled={command.pending} onClick={() => run(frozen)}>
          Retry same {frozen.action}
        </Button>
      )}
      {notice && <Notice tone="success">{notice}</Notice>}
      {record.loading ? (
        <p role="status">Loading {noun}...</p>
      ) : (
        row &&
        !record.failure && (
          <>
            <Card>
              <CardBody>
                <ReviewList
                  items={record.fields
                    .filter(
                      (field) =>
                        profileVisible(record.fields, field.key) &&
                        ['code', 'name', 'is_active', 'row_version'].includes(
                          field.key,
                        ) &&
                        field.key in row,
                    )
                    .map((field) => ({
                      label:
                        field.key === 'is_active'
                          ? 'Status'
                          : (field.control?.label ??
                            field.key.replaceAll('_', ' ')),
                      value:
                        field.key === 'is_active'
                          ? row.is_active
                            ? 'Active'
                            : 'Inactive'
                          : String(row[field.key]),
                    }))}
                />
                <ProfileExplanation
                  resource={config.resource as ProductProfileResource}
                />
              </CardBody>
            </Card>
            <ProductProfileHistory
              company={company}
              resource={config.resource as ProductProfileResource}
              parentId={id}
              here={here}
              active={row.is_active === true}
              canManage={canManage}
              blocked={command.blocked}
              onLeave={guard.leave}
            />
          </>
        )
      )}
      <ConfirmDialog
        open={!!action}
        title={
          (action === 'activate' ? 'Activate' : 'Deactivate') + ' ' + noun + '?'
        }
        confirmLabel={action === 'activate' ? 'Activate' : 'Deactivate'}
        busy={command.pending}
        onCancel={() => {
          if (!command.pending) setAction(null);
        }}
        onConfirm={() => {
          if (action && row) void run({ action, version: row.row_version! });
        }}
      >
        This changes availability for new use. Existing published references
        remain protected by the service.
      </ConfirmDialog>
      <ConfirmDialog
        open={reload}
        title="Reload and review?"
        confirmLabel="Reload"
        onCancel={() => setReload(false)}
        onConfirm={() => {
          setReload(false);
          command.clear();
          record.refresh();
        }}
      >
        Load the latest saved {noun} before another action.
      </ConfirmDialog>
      {guard.confirmation}
    </div>
  );
}
