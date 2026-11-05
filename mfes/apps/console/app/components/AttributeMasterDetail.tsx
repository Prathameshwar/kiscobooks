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
import { useServiceCommand } from '../lib/service-resource';
import {
  attributeBase,
  attributeEditKeys,
  attributeLink,
  attributeReceipt,
  attributeReturn,
  attributeVisible,
  attributeWritable,
} from '../lib/attribute-masters';
import type { AttributeAccess } from '../lib/attribute-resources';
import { useAccessDraft } from './AccessCommon';
import {
  AttributeFailure,
  AttributeNavigation,
  AttributeReferenceLabel,
} from './AttributeMasterCommon';
import { AttributeSetHistory } from './AttributeSetHistory';
export function AttributeMasterDetail({
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
  access: AttributeAccess;
}) {
  const root = '/masters/' + config.resource,
    back = attributeReturn(returnTo, root),
    here = attributeLink(root + '/' + id, back),
    record = useMasterRecord(company, config, id, false),
    row = record.row,
    fields = record.fields;
  const command = useServiceCommand(masterRequest, 'attribute masters'),
    guard = useAccessDraft(command.uncertain, command.pending);
  const [action, setAction] = useState<'activate' | 'deactivate' | null>(null),
    [frozen, setFrozen] = useState<{ action: string; version: number } | null>(
      null,
    ),
    [message, setMessage] = useState(''),
    [changedAvailability, setChangedAvailability] = useState(false),
    [reload, setReload] = useState(false);
  const canEdit =
    !!row &&
    canManage &&
    attributeVisible(fields, 'row_version') &&
    attributeEditKeys(config.resource, row).some(
      (key) =>
        attributeWritable(fields, [key]) && (key !== 'unit_id' || access.units),
    );
  const canLifecycle =
    !!row &&
    canManage &&
    typeof row.is_active === 'boolean' &&
    Number.isSafeInteger(row.row_version) &&
    attributeVisible(fields, 'row_version') &&
    attributeWritable(fields, ['is_active']);
  const disabledReason = command.blocked
    ? command.pending
      ? 'An action is being saved.'
      : command.uncertain
        ? 'Retry the unconfirmed action first.'
        : 'Reload and review before another action.'
    : undefined;
  async function run(value: { action: string; version: number }) {
    if (!canLifecycle || command.pending) return;
    setFrozen(value);
    setMessage('');
    const result = await command.execute<MasterRow>(
      {
        path:
          attributeBase(company, config.resource) +
          '/' +
          id +
          '/' +
          value.action,
        method: 'POST',
        body: { expected_version: value.version },
      },
      (result) => {
        attributeReceipt(result, company, id, value.version);
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
      setChangedAvailability(changed);
      setMessage(
        changed
          ? 'The action completed. Availability has since changed; review the current record.'
          : config.singular +
              (result.is_active
                ? ' activated successfully.'
                : ' deactivated successfully.'),
      );
    }
  }
  return (
    <div className="janso-page">
      <AttributeNavigation
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
              label={config.singular + ' actions'}
              items={[
                ...(canEdit
                  ? [
                      {
                        id: 'edit',
                        label: 'Edit details',
                        href: attributeLink(root + '/' + id + '/edit', here),
                        disabledReason,
                      },
                    ]
                  : []),
                ...(canLifecycle
                  ? [
                      {
                        id: row.is_active ? 'deactivate' : 'activate',
                        label: row.is_active ? 'Deactivate' : 'Activate',
                        destructive: row.is_active === true,
                        disabledReason,
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
      <AttributeFailure failure={record.failure} retry={record.refresh} />
      <AttributeFailure
        failure={command.failure}
        write
        retry={
          command.failure?.status === 409 ? () => setReload(true) : undefined
        }
      />
      {message && (
        <Notice tone={changedAvailability ? 'warning' : 'success'}>
          {message}
        </Notice>
      )}
      {command.uncertain && frozen && (
        <Button loading={command.pending} onClick={() => void run(frozen)}>
          Retry same {frozen.action}
        </Button>
      )}
      {record.loading ? (
        <p role="status">Loading {config.singular}...</p>
      ) : (
        row && (
          <>
            <Card>
              <CardBody>
                <SectionHeader title="Details" />
                {!canManage && <Notice>Read-only access.</Notice>}
                {row.is_active === false && (
                  <Notice tone="warning">
                    This record is inactive. Existing references remain
                    available.
                  </Notice>
                )}
                <ReviewList
                  items={fields
                    .filter(
                      (field) =>
                        attributeVisible(fields, field.key) && field.key in row,
                    )
                    .map((field) => ({
                      label:
                        field.label !== field.key
                          ? field.label
                          : (field.control?.label ??
                            field.key.replaceAll('_', ' ')),
                      value:
                        typeof row[field.key] === 'boolean' ? (
                          row[field.key] ? (
                            'Yes'
                          ) : (
                            'No'
                          )
                        ) : field.key === 'definition_id' &&
                          typeof row.definition_id === 'string' &&
                          access['attribute-definitions'] ? (
                          <AttributeReferenceLabel
                            company={company}
                            resource="attribute-definitions"
                            id={row.definition_id}
                            returnTo={here}
                            onLeave={guard.leave}
                          />
                        ) : field.key === 'unit_id' &&
                          typeof row.unit_id === 'string' &&
                          access.units ? (
                          <AttributeReferenceLabel
                            company={company}
                            resource="units"
                            id={row.unit_id}
                            returnTo={here}
                            onLeave={guard.leave}
                          />
                        ) : (
                          String(row[field.key] ?? 'Not set')
                        ),
                    }))}
                />
                <Notice>
                  Referenced definitions and option values are protected.
                  Retirement keeps existing references and may be blocked by
                  active dependencies.
                </Notice>
                {config.resource === 'attribute-definitions' &&
                  access['attribute-options'] && (
                    <div className="janso-flow">
                      <a
                        className="janso-link"
                        href={attributeLink(
                          '/masters/attribute-options?definition_id=' + id,
                          here,
                        )}
                        onClick={guard.leave}
                      >
                        View options for this definition
                      </a>
                    </div>
                  )}
              </CardBody>
            </Card>
            {config.resource === 'attribute-sets' && (
              <AttributeSetHistory
                company={company}
                setId={id}
                here={here}
                active={row.is_active === true}
                canManage={canManage}
                access={access}
                blocked={command.blocked}
                onLeave={guard.leave}
              />
            )}
          </>
        )
      )}
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
        onConfirm={() => {
          if (action && row) void run({ action, version: row.row_version! });
        }}
      >
        This changes availability in the current company. Dependencies and the
        latest version are checked before saving.
      </ConfirmDialog>
      <ConfirmDialog
        open={reload}
        title="Reload current record?"
        confirmLabel="Reload and review"
        onCancel={() => setReload(false)}
        onConfirm={() => {
          setReload(false);
          command.clear();
          setFrozen(null);
          record.refresh();
        }}
      >
        Review the latest record before another action.
      </ConfirmDialog>
      {guard.confirmation}
    </div>
  );
}
