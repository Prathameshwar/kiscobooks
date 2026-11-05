'use client';
import {
  Card,
  CardHeader,
  DataTable,
  FilterBar,
  Pager,
  Select,
  type Column,
} from '@janso/ui';
import { useState } from 'react';
import { masterRequest } from '../lib/catalog-master-api';
import type { MasterRow } from '../lib/catalog-masters';
import { useServiceList } from '../lib/service-resource';
import {
  identifierBase,
  identifierVisible,
  useIdentifierFields,
} from '../lib/units-identifiers';
import { IdentifierFailure } from './UnitsIdentifiersCommon';

export function IdentifierProfileRequirements({
  company,
  id,
}: {
  company: string;
  id: string;
}) {
  const metadata = useIdentifierFields(
      company,
      'catalog.identifier_profile_requirement',
    ),
    fields = metadata.data?.fields ?? [],
    [type, setType] = useState(''),
    [namespace, setNamespace] = useState('');
  const params = new URLSearchParams({ sort: '-id' });
  if (type && identifierVisible(fields, 'identifier_type'))
    params.set('identifier_type', type);
  if (namespace && identifierVisible(fields, 'namespace_rule'))
    params.set('namespace_rule', namespace);
  const list = useServiceList<MasterRow>(
    identifierBase(company, 'identifier-profiles/' + id + '/requirements'),
    params.toString(),
    masterRequest,
  );
  const columns: Column<MasterRow>[] = fields
    .filter(
      (field) =>
        identifierVisible(fields, field.key) &&
        !['profile_id', 'row_version'].includes(field.key),
    )
    .map((field) => ({
      key: field.key,
      header:
        field.label !== field.key
          ? field.label
          : (field.control?.label ?? field.key),
      type: 'custom',
      render: (row) =>
        field.key in row
          ? typeof row[field.key] === 'boolean'
            ? row[field.key]
              ? 'Required'
              : 'Not required'
            : (field.control?.choices?.find(
                (choice) => choice.value === row[field.key],
              )?.label ?? String(row[field.key]))
          : 'Protected',
    }));
  return (
    <section aria-label="Saved identifier requirements">
      <IdentifierFailure
        failure={metadata.failure ?? list.failure}
        retry={() => {
          metadata.refresh();
          list.first();
        }}
      />
      <Card>
        <CardHeader title="Identifier requirements" />
        <FilterBar
          applied={[
            ...(type ? [{ id: 'type', label: 'Type', value: type }] : []),
            ...(namespace
              ? [{ id: 'namespace', label: 'Namespace rule', value: namespace }]
              : []),
          ]}
          onRemove={(key) => (key === 'type' ? setType('') : setNamespace(''))}
          onClearAll={() => {
            setType('');
            setNamespace('');
          }}
        >
          {fields
            .filter(
              (field) =>
                ['identifier_type', 'namespace_rule'].includes(field.key) &&
                identifierVisible(fields, field.key),
            )
            .map((field) => (
              <Select
                key={field.key}
                label={
                  'Filter by ' +
                  (field.control?.label.toLowerCase() ?? field.key)
                }
                placeholder="All rules"
                value={field.key === 'identifier_type' ? type : namespace}
                options={field.control?.choices ?? []}
                onChange={
                  field.key === 'identifier_type' ? setType : setNamespace
                }
              />
            ))}
        </FilterBar>
        <DataTable
          caption="Saved identifier requirements"
          columns={
            columns.length
              ? columns
              : [
                  {
                    key: 'rule',
                    header: 'Rule',
                    type: 'custom',
                    render: () => 'Protected requirement',
                  },
                ]
          }
          rows={list.data?.items ?? []}
          rowId={(row) => row.id}
          rowLabel={() => 'Identifier requirement'}
          loading={metadata.loading || list.loading}
          filtered={!!type || !!namespace}
          emptyTitle="No identifier requirements available"
          emptyBody="Clear filters or check this profile's requirements and access."
          onClearFilters={() => {
            setType('');
            setNamespace('');
          }}
        />
        <Pager
          count={list.data?.items.length ?? 0}
          limit={list.limit}
          busy={list.loading}
          hasPrevious={list.hasPrevious}
          hasNext={!!list.data?.page.has_more}
          onPrevious={list.previous}
          onNext={list.next}
          onLimitChange={list.setLimit}
          noun="requirement"
        />
      </Card>
    </section>
  );
}
