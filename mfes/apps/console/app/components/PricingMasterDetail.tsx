'use client';
import { useState } from 'react';
import {
  Button,
  Card,
  CardBody,
  ConfirmDialog,
  CustomFields,
  Menu,
  Notice,
  PageHeader,
  ReviewList,
  SectionHeader,
} from '@janso/ui';
import { useMasterRecord } from '../lib/catalog-master-api';
import {
  masterCustomFields,
  type MasterConfig,
  type MasterRow,
} from '../lib/catalog-masters';
import {
  canEditPricing,
  pricingBase,
  pricingCommand,
  pricingLink,
  pricingPurposes,
  pricingReceipt,
  pricingReturn,
  pricingVisible,
  pricingWritable,
} from '../lib/pricing-masters';
import type { PricingAccess } from '../lib/pricing-resources';
import { useServiceCommand } from '../lib/service-resource';
import { useAccessDraft } from './AccessCommon';
import {
  PricingFailure,
  PricingLevelLabel,
  PricingMasterExplanation,
  PricingNavigation,
} from './PricingMasterCommon';
export function PricingMasterDetail({
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
  access: PricingAccess;
}) {
  const root = '/masters/' + config.resource,
    back = pricingReturn(returnTo, root),
    here = pricingLink(root + '/' + id, back),
    record = useMasterRecord(company, config, id, false),
    row = record.row,
    fields = record.fields,
    levels = config.resource === 'price-levels';
  const command = useServiceCommand(
      pricingCommand,
      'pricing lifecycle service',
    ),
    guard = useAccessDraft(command.uncertain, command.pending);
  const [action, setAction] = useState<'activate' | 'deactivate' | null>(null),
    [frozen, setFrozen] = useState<{
      action: string;
      version: number;
      name?: string;
    } | null>(null),
    [message, setMessage] = useState(''),
    [changedAvailability, setChangedAvailability] = useState(false),
    [reload, setReload] = useState(false);
  const canEdit = canManage && canEditPricing(config, fields, row, access),
    lifecycleResource = levels || config.resource === 'sales-channels';
  const canLifecycle =
    !!row &&
    canManage &&
    lifecycleResource &&
    typeof row.is_active === 'boolean' &&
    Number.isSafeInteger(row.row_version) &&
    pricingVisible(fields, 'row_version') &&
    pricingWritable(fields, ['is_active']) &&
    (!levels ||
      (typeof row.name === 'string' &&
        pricingVisible(fields, 'name') &&
        (row.is_active === false ||
          (pricingVisible(fields, 'ordinal') && row.ordinal !== 1))));
  const disabledReason = command.blocked
    ? command.pending
      ? 'An action is being saved.'
      : command.uncertain
        ? 'Retry the unconfirmed action first.'
        : 'Reload and review before another action.'
    : undefined;
  async function run(value: {
    action: string;
    version: number;
    name?: string;
  }) {
    if (!canLifecycle || command.pending) return;
    setFrozen(value);
    setMessage('');
    const result = await command.execute<MasterRow>(
      {
        path:
          pricingBase(company, config.resource) +
          '/' +
          id +
          (levels ? '' : '/' + value.action),
        method: levels ? 'PATCH' : 'POST',
        body: levels
          ? {
              expected_version: value.version,
              name: value.name,
              is_active: value.action === 'activate',
            }
          : { expected_version: value.version },
      },
      (current) => {
        pricingReceipt(current, company, id, value.version);
        if (typeof current.is_active !== 'boolean')
          throw {
            status: 502,
            message:
              'The availability result could not be verified. Retry the same action.',
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
      <PricingNavigation
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
                        href: pricingLink(root + '/' + id + '/edit', here),
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
      <PricingFailure failure={record.failure} retry={record.refresh} />
      <PricingFailure failure={command.failure} uncertain={command.uncertain} />
      {command.failure && !command.uncertain && (
        <Button type="button" variant="ghost" onClick={() => setReload(true)}>
          Reload and review
        </Button>
      )}
      {command.uncertain && frozen && (
        <Button
          type="button"
          loading={command.pending}
          onClick={() => run(frozen)}
        >
          Retry same {frozen.action}
        </Button>
      )}
      {message && (
        <Notice tone={changedAvailability ? 'warning' : 'success'}>
          {message}
        </Notice>
      )}
      {record.loading ? (
        <p role="status">Loading {config.singular}…</p>
      ) : (
        row && (
          <Card>
            <CardBody>
              <SectionHeader title="Details" />
              {!canManage && <Notice>Read-only access.</Notice>}
              {row.is_active === false && (
                <Notice tone="warning">
                  This record is inactive. Existing references remain available.
                </Notice>
              )}
              <ReviewList
                items={fields
                  .filter(
                    (field) =>
                      field.source === 'native' &&
                      pricingVisible(fields, field.key) &&
                      field.key in row,
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
                      ) : field.key === 'purpose' ? (
                        (pricingPurposes.find(
                          (purpose) => purpose.value === row.purpose,
                        )?.label ?? String(row.purpose))
                      ) : field.key === 'price_level_id' &&
                        typeof row.price_level_id === 'string' &&
                        access['price-levels'] ? (
                        <a
                          className="janso-link"
                          href={pricingLink(
                            '/masters/price-levels/' + row.price_level_id,
                            here,
                          )}
                          onClick={guard.leave}
                        >
                          <PricingLevelLabel
                            company={company}
                            id={row.price_level_id}
                          />
                        </a>
                      ) : (
                        String(row[field.key] ?? 'Not set')
                      ),
                  }))}
              />
              {config.resource === 'price-plans' && (
                <CustomFields
                  fields={masterCustomFields(fields)}
                  values={row.custom_fields ?? {}}
                  nativeValues={row}
                  disabled
                  currencies={
                    typeof row.currency === 'string' ? [row.currency] : []
                  }
                  onChange={() => undefined}
                />
              )}
              <PricingMasterExplanation resource={config.resource} />
              {levels && access['price-plans'] && (
                <a
                  className="janso-link"
                  href={pricingLink(
                    '/masters/price-plans?price_level_id=' + id,
                    here,
                  )}
                  onClick={guard.leave}
                >
                  View price plans for this level
                </a>
              )}
            </CardBody>
          </Card>
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
          if (action && row)
            void run({
              action,
              version: row.row_version!,
              ...(levels ? { name: row.name } : {}),
            });
        }}
      >
        This changes availability for new use. Referenced records remain
        protected by the service.
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
        Load the latest saved record before another action.
      </ConfirmDialog>
      {guard.confirmation}
    </div>
  );
}
