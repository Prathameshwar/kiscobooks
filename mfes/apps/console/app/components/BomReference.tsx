'use client';
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Notice,
  SearchSelect,
  TextField,
  type SearchSelectLoader,
  type SearchSelectOption,
} from '@janso/ui';
import { bomBase, bomId } from '../lib/boms';
import { masterRequest } from '../lib/catalog-master-api';
import type { ServicePage } from '../lib/service-resource';
import { requestFailure } from '../lib/service-call';

type Option = {
  id: string;
  parent_id?: string;
  code: string;
  name: string;
  revision?: number;
  value?: string;
  label?: string;
  source?: string;
};
export function BomReference({
  company,
  source,
  value,
  onChange,
  disabled,
  label,
  error,
  item,
  date,
  canRead = true,
  bom,
}: {
  company: string;
  source: 'goods' | 'units' | 'routes' | 'revisions';
  value: string | null;
  onChange: (value: string | null) => void;
  disabled: boolean;
  label: string;
  error?: string;
  item?: string;
  date?: string;
  canRead?: boolean;
  bom?: string;
}) {
  const scope =
    company + ':' + source + ':' + (item ?? '') + ':' + (date ?? '');
  const cache = useMemo(() => new Map<string, SearchSelectOption>(), [scope]);
  const [selected, setSelected] = useState<SearchSelectOption | null>(null),
    [problem, setProblem] = useState('');
  const option = useCallback(
    (row: Option): SearchSelectOption => {
      const id = row.id ?? row.value;
      if (
        !bomId(id) ||
        (source === 'units' && row.parent_id !== item) ||
        (source === 'revisions' && bom && row.parent_id !== bom)
      )
        throw {
          status: 502,
          message: 'The selected reference does not match this recipe.',
        };
      const result = {
        id,
        label: row.name ?? row.label ?? row.code,
        meta: row.code + (row.revision ? ' · Revision ' + row.revision : ''),
      };
      if (cache.size >= 200 && !cache.has(id))
        cache.delete(cache.keys().next().value!);
      cache.set(id, result);
      return result;
    },
    [source, item, bom, cache],
  );
  const load = useCallback<SearchSelectLoader>(
    async ({ q, cursor, signal }) => {
      const params = new URLSearchParams({ limit: '50' });
      if (cursor) params.set('cursor', cursor);
      if (source === 'revisions' && bom) params.set('bom_id', bom);
      if (source === 'units') {
        if (!bomId(item) || !date) return { items: [], nextCursor: null };
        params.set('item_id', item);
        params.set('as_of', date);
      } else if (q.trim().length >= 2) params.set('q', q.trim());
      const page = await masterRequest<ServicePage<Option>>({
        path: bomBase(company, '/options/' + source) + '?' + params,
        signal,
      });
      if (!Array.isArray(page.items) || !page.page)
        throw {
          status: 502,
          message: 'Reference choices could not be verified.',
        };
      const rows =
        bom && source === 'revisions'
          ? page.items.filter((row) => row.parent_id === bom)
          : page.items;
      const items = rows
        .map(option)
        .filter(
          (row) =>
            source !== 'units' ||
            !q.trim() ||
            (row.label + ' ' + row.meta)
              .toLowerCase()
              .includes(q.trim().toLowerCase()),
        );
      return {
        items,
        nextCursor: page.page.has_more ? page.page.next_cursor : null,
      };
    },
    [company, source, item, date, bom, option],
  );
  useEffect(() => {
    const controller = new AbortController();
    setSelected(value ? (cache.get(value) ?? null) : null);
    setProblem('');
    if (value && canRead)
      masterRequest<Option>({
        path: bomBase(company, '/options/references/' + source + '/' + value),
        signal: controller.signal,
      })
        .then((row) => {
          if (!controller.signal.aborted) {
            if (row.id !== value || row.source !== source)
              throw {
                status: 502,
                message: 'Stored reference could not be verified.',
              };
            setSelected(option(row));
          }
        })
        .catch((error) => {
          if (!controller.signal.aborted)
            setProblem(requestFailure(error, 'BOM reference').message);
        });
    return () => controller.abort();
  }, [company, source, value, canRead, option, cache]);
  if (!canRead)
    return (
      <TextField
        label={label}
        value={
          value ? 'Existing reference (read access unavailable)' : 'Not set'
        }
        disabled
        hint="Existing values are retained."
      />
    );
  return (
    <div className="janso-flow">
      <SearchSelect
        label={label}
        name={source + '-reference'}
        scopeKey={scope}
        value={value}
        selected={
          selected?.id === value
            ? selected
            : value
              ? (cache.get(value) ?? {
                  id: value,
                  label: problem
                    ? 'Stored reference unavailable'
                    : 'Loading reference…',
                  disabled: true,
                })
              : null
        }
        loadOptions={load}
        minQueryLength={source === 'units' ? 0 : 2}
        disabled={disabled || (source === 'units' && (!bomId(item) || !date))}
        error={error}
        clearable
        onChange={(next) => {
          setSelected(next ? (cache.get(next) ?? null) : null);
          onChange(next);
        }}
      />
      {problem && (
        <Notice tone="warning">
          {problem} The stored value is retained. Retry loading the recipe
          before changing this reference.
        </Notice>
      )}
    </div>
  );
}
