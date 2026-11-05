'use client';
import {
  Button,
  Card,
  CardBody,
  CardHeader,
  Menu,
  Notice,
  SectionHeader,
  Select,
} from '@janso/ui';
import type { MasterField, MasterRow } from '../lib/catalog-masters';
import {
  bomBase,
  bomId,
  newBomLine,
  type BomAccess,
  type BomLine,
} from '../lib/boms';
import { masterRequest } from '../lib/catalog-master-api';
import { useServiceRead, type ServicePage } from '../lib/service-resource';
import { ProfileFailure, ProfileField } from './ProductProfileCommon';
import { BomReference } from './BomReference';

const noProfiles = {
  'inventory-templates': false,
  'warranty-policies': false,
  'return-policies': false,
  'handling-profiles': false,
  publish: false,
  identifiers: false,
};
export function BomLines({
  company,
  kind,
  rows,
  onChange,
  fields,
  disabled,
  errors,
  date,
  route,
  access,
}: {
  company: string;
  kind: 'components' | 'outputs';
  rows: BomLine[];
  onChange: (rows: BomLine[]) => void;
  fields: readonly MasterField[];
  disabled: boolean;
  errors: Record<string, string>;
  date: string;
  route: string | null;
  access: BomAccess;
}) {
  const components = kind === 'components',
    title = components ? 'Components' : 'Outputs';
  const source = useServiceRead<{
    id: string;
    source: string;
    parent_id: string;
    step_count: number;
  }>(
    components && route && access.routes
      ? bomBase(company, '/options/references/routes/' + route)
      : undefined,
    masterRequest,
    (row) => {
      if (
        row.id !== route ||
        row.source !== 'routes' ||
        !bomId(row.parent_id) ||
        !Number.isSafeInteger(row.step_count)
      )
        throw {
          status: 502,
          message: 'Route step source could not be verified.',
        };
    },
  );
  const steps = useServiceRead<ServicePage<MasterRow>>(
    source.data
      ? `/v1/companies/${company}/manufacturing-routes/${source.data.parent_id}/revisions/${route}/steps?limit=50&sort=sequence`
      : undefined,
    masterRequest,
    (page) => {
      if (
        !Array.isArray(page.items) ||
        page.page.has_more ||
        page.page.next_cursor ||
        page.items.length !== source.data?.step_count ||
        page.items.some(
          (row, index) =>
            !bomId(row.id) ||
            row.revision_id !== route ||
            row.sequence !== index + 1,
        )
      )
        throw {
          status: 502,
          message: 'The complete route step list is unavailable.',
        };
    },
  );
  const change = (index: number, key: string, value: unknown) =>
    onChange(
      rows.map((row, position) =>
        position === index
          ? {
              ...row,
              [key]: value,
              ...(key === 'item_id' ? { unit_revision_id: null } : {}),
            }
          : row,
      ),
    );
  const move = (index: number, direction: number) => {
    const next = [...rows];
    [next[index], next[index + direction]] = [
      next[index + direction]!,
      next[index]!,
    ];
    onChange(next.map((row, position) => ({ ...row, sequence: position + 1 })));
  };
  const visible = fields.filter(
    (field) =>
      field.visible &&
      !field.conditional_access &&
      field.control &&
      !['line_key', 'sequence', 'draft_id', 'revision_id'].includes(field.key),
  );
  return (
    <section className="janso-flow" aria-label={title}>
      <div className="janso-toolbar">
        <div className="janso-toolbar__side">
          <SectionHeader
            title={title}
            description={
              components
                ? 'Stock inputs are scaled per basis or fixed per explicitly counted run.'
                : 'Use one primary output. Each additional output must be a different SKU.'
            }
          />
        </div>
        <div className="janso-toolbar__side janso-toolbar__side--end">
          <Button
            type="button"
            variant="ghost"
            disabled={disabled || rows.length >= (components ? 1000 : 100)}
            onClick={() =>
              onChange([
                ...rows,
                {
                  ...newBomLine(kind, rows.length + 1),
                  ...(!components && rows.some((row) => row.role === 'PRIMARY')
                    ? { role: 'CO_PRODUCT' }
                    : {}),
                },
              ])
            }
          >
            Add {components ? 'component' : 'output'}
          </Button>
        </div>
      </div>
      {errors[kind] && <Notice tone="warning">{errors[kind]}</Notice>}
      {!rows.length && <Notice>No {title.toLowerCase()} added.</Notice>}
      {source.failure || steps.failure ? (
        <ProfileFailure
          failure={source.failure ?? steps.failure}
          retry={() => {
            source.refresh();
            steps.refresh();
          }}
        />
      ) : null}
      {rows.map((row, index) => (
        <section
          key={row.line_key}
          aria-label={`${components ? 'Component' : 'Output'} ${index + 1}`}
        >
          <Card nested>
            <CardHeader
              title={`${components ? 'Component' : 'Output'} ${index + 1}`}
              action={
                <Menu
                  label={`${title} line ${index + 1} actions`}
                  items={[
                    {
                      id: 'up',
                      label: 'Move up',
                      disabledReason: disabled
                        ? 'This recipe cannot be edited.'
                        : index === 0
                          ? 'This is the first line.'
                          : undefined,
                    },
                    {
                      id: 'down',
                      label: 'Move down',
                      disabledReason: disabled
                        ? 'This recipe cannot be edited.'
                        : index === rows.length - 1
                          ? 'This is the last line.'
                          : undefined,
                    },
                    {
                      id: 'remove',
                      label: 'Remove line',
                      destructive: true,
                      disabledReason: disabled
                        ? 'This recipe cannot be edited.'
                        : undefined,
                    },
                  ]}
                  onSelect={(action) =>
                    action === 'remove'
                      ? onChange(
                          rows
                            .filter((_, position) => position !== index)
                            .map((value, position) => ({
                              ...value,
                              sequence: position + 1,
                            })),
                        )
                      : move(index, action === 'up' ? -1 : 1)
                  }
                />
              }
            />
            <CardBody>
              <div className="janso-form-grid">
                {visible.map((field) => {
                  const label =
                      field.label !== field.key
                        ? field.label
                        : field.control!.label,
                    error = errors[`${kind}.${index}.${field.key}`],
                    locked =
                      disabled ||
                      !field.writable ||
                      !!field.control?.disabled_reason;
                  if (
                    field.key === 'item_id' ||
                    field.key === 'unit_revision_id'
                  )
                    return (
                      <BomReference
                        key={field.key}
                        company={company}
                        source={field.key === 'item_id' ? 'goods' : 'units'}
                        value={
                          typeof row[field.key] === 'string'
                            ? (row[field.key] as string)
                            : null
                        }
                        onChange={(value) => change(index, field.key, value)}
                        disabled={locked}
                        label={label}
                        error={error}
                        item={row.item_id}
                        date={date}
                        canRead={
                          field.key === 'item_id' ? access.goods : access.units
                        }
                      />
                    );
                  if (field.key === 'route_step_id')
                    return (
                      <Select
                        key={field.key}
                        label={label}
                        name={field.key}
                        value={String(row[field.key] ?? '')}
                        placeholder="No specific step"
                        options={[
                          ...(row.route_step_id &&
                          !steps.data?.items.some(
                            (step) => step.id === row.route_step_id,
                          )
                            ? [
                                {
                                  value: String(row.route_step_id),
                                  label: 'Stored route step',
                                  disabled: true,
                                },
                              ]
                            : []),
                          ...(steps.data?.items ?? []).map((step) => ({
                            value: step.id,
                            label: 'Step ' + step.sequence,
                          })),
                        ]}
                        disabled={locked || !route || !steps.data}
                        error={error}
                        onChange={(value) =>
                          change(index, field.key, value || null)
                        }
                      />
                    );
                  return (
                    <ProfileField
                      key={field.key}
                      company={company}
                      field={field}
                      value={row[field.key]}
                      disabled={locked}
                      error={error}
                      onChange={(value) => change(index, field.key, value)}
                      access={noProfiles}
                    />
                  );
                })}
              </div>
            </CardBody>
          </Card>
        </section>
      ))}
    </section>
  );
}
