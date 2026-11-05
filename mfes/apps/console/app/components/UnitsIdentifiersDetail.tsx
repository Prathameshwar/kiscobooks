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
  SectionHeader,
} from '@janso/ui';
import { masterRequest, useMasterRecord } from '../lib/catalog-master-api';
import type { MasterConfig, MasterRow } from '../lib/catalog-masters';
import {
  identifierBase,
  identifierLink,
  identifierReceipt,
  identifierReturn,
  identifierVisible,
  identifierWritable,
} from '../lib/units-identifiers';
import { useServiceCommand } from '../lib/service-resource';
import { useAccessDraft } from './AccessCommon';
import {
  IdentifierFailure,
  IdentifierNavigation,
  IdentifierUnitLabel,
  type IdentifierAccess,
} from './UnitsIdentifiersCommon';
import { IdentifierProfileRequirements } from './IdentifierProfileRequirements';
import { UnitConversionCheck } from './UnitConversionCheck';

export function UnitsIdentifiersDetail({
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
  access: IdentifierAccess;
}) {
  const root = '/masters/' + config.resource,
    back = identifierReturn(returnTo, root),
    here = identifierLink(root + '/' + id, back),
    conversion = config.resource === 'unit-conversions',
    record = useMasterRecord(company, config, id, false),
    row = record.row,
    fields = record.fields;
  const command = useServiceCommand(masterRequest, 'units and identifiers'),
    [action, setAction] = useState<'activate' | 'deactivate' | null>(null),
    [frozen, setFrozen] = useState<{ action: string; version: number } | null>(
      null,
    ),
    [message, setMessage] = useState(''),
    [availabilityChanged, setAvailabilityChanged] = useState(false),
    [reload, setReload] = useState(false),
    guard = useAccessDraft(command.uncertain, command.pending);
  const editKeys = ['identifier-types', 'identifier-namespaces'].includes(
    config.resource,
  )
    ? ['name']
    : ['code', 'name'];
  const disabledReason = command.blocked
    ? command.pending
      ? 'The current action is being saved.'
      : command.uncertain
        ? 'Retry the unconfirmed action to recover its result.'
        : 'Reload and review before another action.'
    : undefined;
  const canEdit =
      !!row &&
      !conversion &&
      canManage &&
      identifierVisible(fields, 'row_version') &&
      editKeys.some((key) => identifierWritable(fields, [key])),
    canLifecycle =
      !!row &&
      !conversion &&
      canManage &&
      typeof row.is_active === 'boolean' &&
      Number.isSafeInteger(row.row_version) &&
      identifierVisible(fields, 'row_version') &&
      identifierWritable(fields, ['is_active']);
  async function run(value: { action: string; version: number }) {
    if (!canLifecycle || command.pending || !row) return;
    setFrozen(value);
    setMessage('');
    setAvailabilityChanged(false);
    const result = await command.execute<MasterRow>(
      {
        path:
          identifierBase(company, config.resource) +
          '/' +
          id +
          '/' +
          value.action,
        method: 'POST',
        body: { expected_version: value.version },
      },
      (result) => {
        identifierReceipt(result, company, false, id, value.version);
        if (typeof result.is_active !== 'boolean')
          throw {
            status: 502,
            message:
              'The lifecycle result could not be verified. Retry the same action.',
          };
      },
    );
    setAction(null);
    if (result) {
      record.setRow(result);
      setFrozen(null);
      const changed = result.is_active !== (value.action === 'activate');
      setAvailabilityChanged(changed);
      setMessage(
        changed
          ? 'The action completed. Availability has since changed; review the current definition before another action.'
          : config.singular +
              (result.is_active
                ? ' activated successfully.'
                : ' deactivated successfully.'),
      );
    }
  }
  return (
    <div className="janso-page">
      <IdentifierNavigation
        title={row?.name ?? config.title}
        back={back}
        access={access}
        onLeave={guard.leave}
      />
      <PageHeader
        title={
          row?.name ??
          (conversion
            ? 'Unit conversion details'
            : config.singular + ' details')
        }
        actions={
          row && (canEdit || canLifecycle) ? (
            <Menu
              label={config.singular + ' actions'}
              items={[
                ...(canEdit
                  ? [
                      {
                        id: 'edit',
                        label: 'Edit details',
                        href: identifierLink(root + '/' + id + '/edit', here),
                        disabledReason,
                      },
                    ]
                  : []),
                ...(canLifecycle
                  ? [
                      {
                        id: row.is_active ? 'deactivate' : 'activate',
                        label: row.is_active ? 'Deactivate' : 'Activate',
                        disabledReason,
                        destructive: row.is_active === true,
                      },
                    ]
                  : []),
              ]}
              onSelect={(value) => {
                if (command.blocked) return;
                if (value !== 'edit')
                  setAction(value as 'activate' | 'deactivate');
              }}
            />
          ) : undefined
        }
      />
      <IdentifierFailure failure={record.failure} retry={record.refresh} />
      <IdentifierFailure
        failure={command.failure}
        write
        retry={
          command.failure?.status === 409 ? () => setReload(true) : undefined
        }
      />
      {message && (
        <Notice tone={availabilityChanged ? 'warning' : 'success'}>
          {message}
        </Notice>
      )}
      {command.uncertain && frozen && (
        <Button onClick={() => void run(frozen)} loading={command.pending}>
          Retry same {frozen.action}
        </Button>
      )}
      {record.loading ? (
        <p role="status">Loading {config.singular}...</p>
      ) : row ? (
        <>
          <Card>
            <CardBody>
              <SectionHeader title="Definition" />
              {row.is_active === false && (
                <Notice tone="warning">
                  This definition is inactive. Existing records remain
                  available.
                </Notice>
              )}
              <ReviewList
                items={fields
                  .filter(
                    (field) =>
                      identifierVisible(fields, field.key) && field.key in row,
                  )
                  .map((field) => ({
                    label:
                      field.label !== field.key
                        ? field.label
                        : (field.control?.label ??
                          field.key.replaceAll('_', ' ')),
                    value: field.key.endsWith('_unit_id') ? (
                      access.units && typeof row[field.key] === 'string' ? (
                        <IdentifierUnitLabel
                          company={company}
                          id={row[field.key] as string}
                          here={here}
                          onLeave={guard.leave}
                        />
                      ) : (
                        'Protected'
                      )
                    ) : typeof row[field.key] === 'boolean' ? (
                      row[field.key] ? (
                        'Yes'
                      ) : (
                        'No'
                      )
                    ) : (
                      String(row[field.key] ?? 'Not set')
                    ),
                  }))}
              />
              {conversion ? (
                <Notice>
                  Conversions are immutable. Each source unit has one declared
                  canonical relation. Define a new unit when the meaning
                  changes.
                </Notice>
              ) : config.resource === 'identifier-profiles' ? (
                <Notice>
                  Requirements and normalization are fixed for this profile.
                  Create a replacement profile when the requirement changes.
                </Notice>
              ) : config.resource === 'pack-types' ? (
                <Notice>
                  Pack types label packaging. Quantities belong to each item's
                  unit definition.
                </Notice>
              ) : (
                <Notice>
                  Codes and barcode classification are fixed. Retirement
                  preserves references and is blocked while this definition is
                  referenced.
                </Notice>
              )}
              {canEdit && (
                <a
                  className="janso-link"
                  onClick={guard.leave}
                  href={identifierLink(root + '/' + id + '/edit', here)}
                >
                  Edit {config.singular}
                </a>
              )}
            </CardBody>
          </Card>
          {config.resource === 'identifier-profiles' && (
            <IdentifierProfileRequirements company={company} id={id} />
          )}
          {conversion &&
            access.units &&
            identifierVisible(fields, 'from_unit_id') &&
            identifierVisible(fields, 'canonical_unit_id') && (
              <UnitConversionCheck
                company={company}
                fromUnit={
                  typeof row.from_unit_id === 'string'
                    ? row.from_unit_id
                    : undefined
                }
              />
            )}
        </>
      ) : null}
      <ConfirmDialog
        open={!!action}
        title={
          (action === 'activate' ? 'Activate ' : 'Deactivate ') +
          config.singular +
          '?'
        }
        confirmLabel={action === 'activate' ? 'Activate' : 'Deactivate'}
        busy={command.pending}
        onCancel={() => {
          if (!command.pending) setAction(null);
        }}
        onConfirm={() =>
          action && row && void run({ action, version: row.row_version! })
        }
      >
        This action changes availability in the current company. Dependencies
        and the latest version are checked before it is saved.
      </ConfirmDialog>
      <ConfirmDialog
        open={reload}
        title="Reload current definition?"
        confirmLabel="Reload and review"
        onCancel={() => setReload(false)}
        onConfirm={() => {
          setReload(false);
          command.clear();
          setFrozen(null);
          record.refresh();
        }}
      >
        Reload the current definition and review its state before trying another
        action.
      </ConfirmDialog>
      {guard.confirmation}
    </div>
  );
}
