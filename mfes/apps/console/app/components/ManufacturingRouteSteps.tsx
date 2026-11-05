'use client';
import { useCallback, useMemo, useRef } from 'react';
import {
  Button,
  Card,
  CardBody,
  CardHeader,
  Notice,
  Menu,
  SearchSelect,
  SectionHeader,
  Select,
  TextField,
  type SearchSelectLoader,
} from '@janso/ui';
import { masterRequest } from '../lib/catalog-master-api';
import type { MasterField } from '../lib/catalog-masters';
import type { ServicePage } from '../lib/service-resource';
import { useServiceRead } from '../lib/service-resource';
import { profileBase, profileLink } from '../lib/product-profiles';
import {
  routeStepNumbers,
  verifyOperationReference,
  type OperationReference,
  type RouteStep,
} from '../lib/manufacturing-routes';

function OperationSelection({
  company,
  value,
  onChange,
  disabled,
  error,
  index,
  label = 'Operation revision',
  returnTo,
  onLeave,
}: {
  company: string;
  value: string;
  onChange: (value: string) => void;
  disabled: boolean;
  error?: string;
  index: number;
  label?: string;
  returnTo?: string;
  onLeave?: React.MouseEventHandler<HTMLAnchorElement>;
}) {
  const original = useServiceRead<OperationReference>(
    value
      ? profileBase(
          company,
          'manufacturing-routes/operation-references/' + value,
        )
      : undefined,
    masterRequest,
    (row) => verifyOperationReference(row, value),
    'operation revision',
  );
  const choices = useMemo(
    () => new Map<string, OperationReference>(),
    [company],
  );
  const load = useCallback<SearchSelectLoader>(
    async ({ q, cursor, signal }) => {
      const params = new URLSearchParams({ limit: '50' });
      if (q.trim().length >= 2) params.set('q', q.trim());
      if (cursor) params.set('cursor', cursor);
      const page = await masterRequest<ServicePage<OperationReference>>({
        path:
          profileBase(company, 'manufacturing-routes/operation-options') +
          '?' +
          params,
        signal,
      });
      if (!Array.isArray(page.items) || !page.page)
        throw {
          status: 502,
          message: 'Operation choices could not be verified.',
        };
      return {
        items: page.items.map((row) => {
          verifyOperationReference(row);
          choices.set(row.id, row);
          while (choices.size > 200) {
            const oldest = choices.keys().next().value;
            if (oldest) choices.delete(oldest);
            else break;
          }
          return {
            id: row.id,
            label: row.name + ' — revision ' + row.revision,
            meta: row.code,
            disabled: !row.is_active || row.status !== 'PUBLISHED',
          };
        }),
        nextCursor: page.page.has_more ? page.page.next_cursor : null,
      };
    },
    [company, choices],
  );
  const selected =
    original.data?.id === value ? original.data : (choices.get(value) ?? null);
  return (
    <div className="janso-flow">
      <SearchSelect
        label={label}
        name={'route-operation-' + index}
        scopeKey={company + ':route-operation'}
        value={value || null}
        selected={
          selected
            ? {
                id: selected.id,
                label: selected.name + ' — revision ' + selected.revision,
                meta: selected.code,
              }
            : value
              ? {
                  id: value,
                  label: original.failure
                    ? 'Operation revision unavailable'
                    : 'Loading operation revision...',
                  disabled: true,
                }
              : null
        }
        loadOptions={load}
        minQueryLength={0}
        disabled={disabled}
        error={error ?? original.failure?.message}
        onChange={(value) => onChange(value ?? '')}
      />
      {selected && (!selected.is_active || selected.status !== 'PUBLISHED') && (
        <Notice tone="warning">
          This operation revision is retained for history. New route
          publications require an active, published operation revision.
        </Notice>
      )}
      {original.failure && (
        <Button type="button" variant="ghost" onClick={original.refresh}>
          Retry operation reference
        </Button>
      )}
      {selected && returnTo && (
        <a
          className="janso-link janso-fine"
          href={profileLink(
            '/masters/manufacturing-operations/' +
              selected.operation_id +
              '/revisions/' +
              selected.id,
            returnTo,
          )}
          onClick={onLeave}
        >
          Open operation revision
        </a>
      )}
    </div>
  );
}

export function ManufacturingRouteSteps({
  company,
  steps,
  onChange,
  disabled,
  complete,
  canReadOperations,
  errors,
  fields = [],
  returnTo,
  onLeave,
}: {
  company: string;
  steps: RouteStep[];
  onChange: (steps: RouteStep[]) => void;
  disabled: boolean;
  complete: boolean;
  canReadOperations: boolean;
  errors: Record<string, string>;
  fields?: readonly MasterField[];
  returnTo?: string;
  onLeave?: React.MouseEventHandler<HTMLAnchorElement>;
}) {
  const nextKey = useRef(0);
  const labelFor = (key: string, fallback: string) => {
    const field = fields.find((field) => field.key === key);
    return field?.label && field.label !== key ? field.label : fallback;
  };
  const change = (index: number, key: keyof RouteStep, value: string) =>
    onChange(
      steps.map((step, position) =>
        position === index ? { ...step, [key]: value } : step,
      ),
    );
  const move = (index: number, direction: number) => {
    const next = [...steps];
    [next[index], next[index + direction]] = [
      next[index + direction]!,
      next[index]!,
    ];
    onChange(
      next.map((step, position) => ({ ...step, sequence: position + 1 })),
    );
  };
  return (
    <section className="janso-flow" aria-label="Route steps">
      <div className="janso-toolbar">
        <div className="janso-toolbar__side">
          <SectionHeader
            title="Route steps"
            description="Steps run in the order shown. Each step uses a specific published operation revision."
          />
        </div>
        <div className="janso-toolbar__side janso-toolbar__side--end">
          <Button
            type="button"
            variant="ghost"
            disabled={
              disabled || !complete || !canReadOperations || steps.length >= 50
            }
            onClick={() =>
              onChange([
                ...steps,
                {
                  _key: 'new-step-' + nextKey.current++,
                  sequence: steps.length + 1,
                  operation_revision_id: '',
                  setup_minutes: '0',
                  run_minutes: '0',
                  lead_time_minutes: '0',
                  quantity_basis: '1',
                  time_basis: 'PER_OUTPUT_UNIT',
                },
              ])
            }
          >
            Add step
          </Button>
        </div>
      </div>
      {[
        ...new Set(
          fields.map((field) => field.control?.disabled_reason).filter(Boolean),
        ),
      ].map((reason) => (
        <Notice key={reason}>{reason}</Notice>
      ))}
      {!complete ? (
        <Notice tone="warning">
          The complete step set is unavailable. Existing steps are retained;
          step replacement and publication are disabled.
        </Notice>
      ) : (
        <>
          {!steps.length && (
            <Notice>
              This draft has no steps. Add at least one step before publishing.
            </Notice>
          )}
          {!canReadOperations && (
            <Notice>
              Operation read access is required to choose and review references.
              Existing values are retained.
            </Notice>
          )}
          {steps.map((step, index) => (
            <section
              aria-label={'Route step ' + (index + 1)}
              key={step.id ?? step._key ?? index}
            >
              <Card nested>
                <CardHeader
                  title={'Step ' + (index + 1)}
                  action={
                    <Menu
                      label={'Step ' + (index + 1) + ' actions'}
                      items={[
                        {
                          id: 'up',
                          label: 'Move up',
                          disabledReason: disabled
                            ? 'This revision cannot be edited.'
                            : index === 0
                              ? 'This is the first step.'
                              : undefined,
                        },
                        {
                          id: 'down',
                          label: 'Move down',
                          disabledReason: disabled
                            ? 'This revision cannot be edited.'
                            : index === steps.length - 1
                              ? 'This is the last step.'
                              : undefined,
                        },
                        {
                          id: 'remove',
                          label: 'Remove step',
                          destructive: true,
                          disabledReason: disabled
                            ? 'This revision cannot be edited.'
                            : undefined,
                        },
                      ]}
                      onSelect={(action) => {
                        if (disabled) return;
                        if (action === 'up' && index > 0) move(index, -1);
                        if (action === 'down' && index < steps.length - 1)
                          move(index, 1);
                        if (action === 'remove')
                          onChange(
                            steps
                              .filter((_, position) => position !== index)
                              .map((row, position) => ({
                                ...row,
                                sequence: position + 1,
                              })),
                          );
                      }}
                    />
                  }
                />
                <CardBody>
                  <div className="janso-form-grid">
                    {canReadOperations ? (
                      <OperationSelection
                        company={company}
                        returnTo={returnTo}
                        onLeave={onLeave}
                        label={labelFor(
                          'operation_revision_id',
                          'Operation revision',
                        )}
                        value={step.operation_revision_id}
                        index={index}
                        onChange={(value) =>
                          change(index, 'operation_revision_id', value)
                        }
                        disabled={disabled}
                        error={
                          errors['steps.' + index + '.operation_revision_id']
                        }
                      />
                    ) : (
                      <TextField
                        label={labelFor(
                          'operation_revision_id',
                          'Operation revision',
                        )}
                        value={
                          step.operation_revision_id
                            ? 'Existing reference (read access unavailable)'
                            : 'Not set'
                        }
                        disabled
                      />
                    )}
                    <Select
                      label={labelFor('time_basis', 'Time basis')}
                      value={step.time_basis}
                      options={[
                        { value: 'PER_OUTPUT_UNIT', label: 'Per output unit' },
                        { value: 'PER_BATCH', label: 'Per batch' },
                      ]}
                      disabled={disabled}
                      error={errors['steps.' + index + '.time_basis']}
                      onChange={(value) => change(index, 'time_basis', value)}
                    />
                    {routeStepNumbers.map((key) => (
                      <TextField
                        key={key}
                        label={labelFor(
                          key,
                          key === 'quantity_basis'
                            ? step.time_basis === 'PER_BATCH'
                              ? 'Batch size'
                              : 'Output quantity basis'
                            : key === 'setup_minutes'
                              ? 'Setup time (minutes)'
                              : key === 'run_minutes'
                                ? 'Run time (minutes)'
                                : 'Lead time (minutes)',
                        )}
                        value={step[key]}
                        maxLength={
                          fields.find((field) => field.key === key)?.control
                            ?.max_length ?? 21
                        }
                        inputMode="decimal"
                        disabled={disabled}
                        error={errors['steps.' + index + '.' + key]}
                        onChange={(event) =>
                          change(index, key, event.target.value)
                        }
                      />
                    ))}
                  </div>
                </CardBody>
              </Card>
            </section>
          ))}
        </>
      )}
      {errors.steps && <Notice tone="danger">{errors.steps}</Notice>}
      <Notice>
        Time definitions are estimates. The BOM supplies the output unit when
        this route is adopted.
      </Notice>
    </section>
  );
}
