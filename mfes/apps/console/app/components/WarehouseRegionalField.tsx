'use client';
import { useEffect, useState } from 'react';
import { SearchSelect, type SearchSelectOption } from '@janso/ui';
import { masterRequest } from '../lib/catalog-master-api';
import { requestFailure } from '../lib/service-call';

/** Reference choices discard stale results across company and country changes. */
export function WarehouseRegionalField({ company, type, value, country, onChange, ...props }: {
  company: string; type: 'country' | 'state' | 'timezone'; value: string | null; country: string | null;
  label: string; name: string; required?: boolean; disabled?: boolean; error?: string; hint?: string;
  onChange: (value: string | null) => void;
}) {
  const [options, setOptions] = useState<SearchSelectOption[]>([]), [loading, setLoading] = useState(false), [failure, setFailure] = useState(''), [revision, setRevision] = useState(0);
  const scope = company + ':' + type + ':' + (type === 'state' ? country ?? '' : '');
  useEffect(() => {
    const controller = new AbortController(); setOptions([]); setFailure('');
    if (props.disabled || type === 'state' && !country) { setLoading(false); return; }
    setLoading(true);
    const path = type === 'country' ? '/v1/reference/countries' : type === 'timezone' ? '/v1/reference/timezones' : `/v1/reference/countries/${country}/states`;
    masterRequest<{ code: string; name: string }[]>({ service: 'identity', path, signal: controller.signal })
      .then(rows => { if (!controller.signal.aborted) { setOptions(rows.map(row => ({ id: row.code, label: row.name, meta: row.code }))); setLoading(false); } })
      .catch(error => { if (!controller.signal.aborted) { setFailure(requestFailure(error, 'reference service').message); setLoading(false); } });
    return () => controller.abort();
  }, [scope, type, country, props.disabled, revision]);
  return <div className="janso-flow"><SearchSelect {...props} value={value} scopeKey={scope} options={options}
    selected={value ? options.find(option => option.id === value) ?? { id: value, label: value } : null}
    disabled={props.disabled || loading || !!failure || type === 'state' && !country} onChange={onChange}
    error={props.error ?? (failure || undefined)} hint={loading ? 'Loading choices...' : type === 'state' && !country ? 'Choose a country first.' : props.hint}
    placeholder={'Choose ' + props.label.toLowerCase()} />
    {failure ? <button type="button" className="janso-btn janso-btn--ghost" onClick={() => setRevision(number => number + 1)}>Retry {props.label.toLowerCase()} choices</button> : null}
  </div>;
}
