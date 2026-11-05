'use client';
import { useState } from 'react';
import {
  Badge,
  Button,
  Card,
  CardBody,
  Checkbox,
  Notice,
  SectionHeader,
  TextField,
} from '@janso/ui';
import type { components } from '@janso/api-client/catalog';
import { masterRequest } from '../lib/catalog-master-api';
import { useServiceCommand, useServiceRead } from '../lib/service-resource';
import type { ServiceRequest } from '../lib/service-call';
import {
  modeEvent,
  useProductMode,
  verifyProductMode,
  type ProductMode,
} from './ProductModeProvider';

const blockerLabels: Record<string, string> = {
  variant_structure: 'Some products still use variants.',
  multiple_or_nondefault_items: 'Some families contain more than one product.',
  family_without_default_item:
    'Some families need their default product completed.',
  variant_axes: 'Some products still have variant options.',
  variant_keys: 'Saved variant combinations must be resolved first.',
  explicit_variant_policy:
    'Product configuration still requires or enables variants.',
  pending_bulk_jobs:
    'Finish or cancel pending bulk jobs before changing to single products.',
};
export function ProductStructureSettings({
  company,
  canManage,
}: {
  company: string;
  canManage: boolean;
}) {
  const mode = useProductMode();
  const [choice, setChoice] = useState<boolean | null>(null),
    [reason, setReason] = useState('');
  const [preview, setPreview] = useState<
    components['schemas']['ProductModePreview'] | null
  >(null);
  const [message, setMessage] = useState('');
  const [reviewRequest, setReviewRequest] = useState<ServiceRequest | null>(
    null,
  );
  const command = useServiceCommand(masterRequest, 'product settings');
  const fields = useServiceRead<components['schemas']['FieldSet']>(
    mode && canManage
      ? `/v1/companies/${company}/entities/catalog.company_product_authoring_configuration/field-set?operation=update`
      : undefined,
    masterRequest,
    (value) => {
      if (
        value.company_id !== company ||
        value.entity_type !==
          'catalog.company_product_authoring_configuration' ||
        !Array.isArray(value.fields)
      )
        throw {
          status: 502,
          message: 'Product setting permissions could not be verified.',
        };
    },
  );
  if (!mode) return null;
  const writable =
    canManage &&
    ['product_family_sku_enabled', 'change_reason'].every((key) =>
      fields.data?.fields.some((field) => field.key === key && field.writable),
    );
  const changed =
    choice !== null && choice !== mode.data?.product_family_sku_enabled;
  const update = () => {
    if (!command.uncertain) {
      command.clear();
      setPreview(null);
      setReviewRequest(null);
      setMessage('');
    }
  };
  return (
    <Card>
      <CardBody>
        <div className="janso-flow">
          <SectionHeader
            title="Product structure"
            description="Choose how people create products in this company. This setting takes effect now."
          />
          {mode.loading ? (
            <p role="status">Loading product settings…</p>
          ) : mode.failure ? (
            <Notice tone="warning">
              {mode.failure.message}{' '}
              <Button variant="ghost" onClick={mode.refresh}>
                Retry
              </Button>
            </Notice>
          ) : (
            mode.data && (
              <>
                <Badge>
                  {mode.data.product_family_sku_enabled
                    ? 'Families and SKUs'
                    : 'Single products'}
                </Badge>
                <Checkbox
                  checked={choice ?? mode.data.product_family_sku_enabled}
                  disabled={!writable || command.pending || command.uncertain}
                  onChange={(event) => {
                    update();
                    setChoice(event.target.checked);
                  }}
                >
                  Use product families and SKUs
                </Checkbox>
                <p className="janso-fine">
                  Turn this on when you manage several variants of a product,
                  such as sizes or colours. Batches, warehouses and ordinary
                  product specifications remain available in either mode.
                </p>
                {canManage && fields.failure && (
                  <Notice tone="warning">{fields.failure.message}</Notice>
                )}
                {!canManage && (
                  <p className="janso-fine">
                    You have read-only access to this setting.
                  </p>
                )}
                {(changed || (command.uncertain && !!reviewRequest)) && (
                  <TextField
                    label="Reason for change"
                    value={reason}
                    required
                    maxLength={250}
                    disabled={command.pending || command.uncertain}
                    onChange={(event) => {
                      update();
                      setReason(event.target.value);
                    }}
                  />
                )}
                {(changed || (command.uncertain && !!reviewRequest)) &&
                  !preview && (
                    <Button
                      disabled={!writable || !reason.trim() || command.pending}
                      loading={command.pending}
                      onClick={() =>
                        void (async () => {
                          const request: ServiceRequest =
                            command.uncertain && reviewRequest
                              ? reviewRequest
                              : {
                                  path: `/v1/companies/${company}/product-configuration/authoring/preview`,
                                  method: 'POST',
                                  body: {
                                    expected_version: mode.data!.row_version,
                                    expected_generation:
                                      mode.data!.policy_generation,
                                    product_family_sku_enabled: choice,
                                    change_reason: reason.trim(),
                                  },
                                };
                          setReviewRequest(request);
                          const value = await command.execute<
                            components['schemas']['ProductModePreview']
                          >(request, (result) => {
                            verifyProductMode(result, company);
                            if (
                              !Array.isArray(result.blockers) ||
                              typeof result.preview_token !== 'string'
                            )
                              throw {
                                status: 502,
                                message:
                                  'The change review could not be verified.',
                              };
                          });
                          if (value) {
                            setPreview(value);
                            setReviewRequest(null);
                          }
                        })()
                      }
                    >
                      {command.uncertain
                        ? 'Retry same review'
                        : 'Review change'}
                    </Button>
                  )}
                {preview && (
                  <Notice tone={preview.blockers.length ? 'warning' : 'info'}>
                    {preview.blockers.length ? (
                      <ul>
                        {preview.blockers.map((key) => (
                          <li key={key}>
                            {blockerLabels[key] ??
                              'Some product settings need administrator review.'}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p>
                        Products will use{' '}
                        {preview.requested_enabled
                          ? 'families and SKUs'
                          : 'a single product form'}
                        . Existing product and stock records are preserved.
                      </p>
                    )}
                    {!preview.blockers.length && (
                      <Button
                        loading={command.pending}
                        onClick={() =>
                          void (async () => {
                            const saved = await command.execute<ProductMode>(
                              {
                                path: `/v1/companies/${company}/product-configuration/authoring`,
                                method: 'PATCH',
                                body: {
                                  expected_version: preview.row_version,
                                  expected_generation:
                                    preview.policy_generation,
                                  product_family_sku_enabled:
                                    preview.requested_enabled,
                                  change_reason: reason.trim(),
                                  preview_token: preview.preview_token,
                                },
                              },
                              (value) => verifyProductMode(value, company),
                            );
                            if (saved) {
                              setChoice(null);
                              setPreview(null);
                              setReason('');
                              setMessage('Product structure saved.');
                              window.dispatchEvent(new Event(modeEvent));
                            }
                          })()
                        }
                      >
                        {command.uncertain
                          ? 'Retry same change'
                          : 'Save product structure'}
                      </Button>
                    )}
                  </Notice>
                )}
              </>
            )
          )}
          {command.failure && (
            <Notice tone="danger">
              {command.failure.message}
              {!command.uncertain && (
                <Button
                  variant="ghost"
                  onClick={() => {
                    command.clear();
                    setPreview(null);
                    mode.refresh();
                  }}
                >
                  Refresh review
                </Button>
              )}
            </Notice>
          )}
          {message && <p role="status">{message}</p>}
        </div>
      </CardBody>
    </Card>
  );
}
