'use client';
import { useEffect, useRef, useState } from 'react';
import { Button, Notice, Select, TextField } from '@janso/ui';
import type { components } from '@janso/api-client/accounting';
import { trackingBase, trackingId, type TrackingSource } from '../lib/stock-tracking-resources';
import { trackingBody } from '../lib/stock-tracking-command';
import { trackingRequest } from '../lib/stock-tracking';
import { useServiceCommand, useServiceRead } from '../lib/service-resource';
import { trimSerialIdentifier, validateSerialIdentifiers } from '../lib/serial-identity';
import { readRegistrationQueue, serialQueueKey, type RegistrationBody, type RegistrationQueue, type RegistrationUnit, type Replacement } from '../lib/serial-registration';
import type { OpeningSerial } from '../lib/advanced-product-opening';
import { AdvancedOpeningSerials } from './AdvancedOpeningSerials';
import { AccessFailure } from './AccessCommon';
import { useTrackingRecoveryScope } from './TrackingRecoveryProvider';

/** Registration prepares identities only. Purchase/stock posting owns the receipt. */
export function SerialRegistration({ company, item, lot, replacement, recoveryScope, onRegistered, forReceipt = false }: {
  company: string; item: string; lot?: string; replacement?: Replacement; recoveryScope?: string;
  onRegistered?: (ids: string[]) => void;
  forReceipt?: boolean;
}) {
  const inheritedScope = useTrackingRecoveryScope(), scope = recoveryScope ?? inheritedScope;
  const storeKey = scope ? serialQueueKey(scope, company, item, lot, replacement) : '';
  const [restored] = useState(() => {
    try { return { queue: storeKey ? readRegistrationQueue(sessionStorage, storeKey, item, lot, replacement) : null, error: '' }; }
    catch (error) { return { queue: null, error: (error as Error).message }; }
  });
  const [queue, setQueue] = useState<RegistrationQueue | null>(restored.queue), queueNow = useRef(queue);
  const [rows, setRows] = useState<OpeningSerial[]>([]), [reason, setReason] = useState('');
  const [scan, setScan] = useState(''), [scanSlot, setScanSlot] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({}), [failure, setFailure] = useState(restored.error);
  const [working, setWorking] = useState(false), [editingQueue, setEditingQueue] = useState(false), busy = useRef(false);
  const base = trackingBase(company, 'serials');
  const source = useServiceRead<TrackingSource>(trackingBase(company) + '/context/' + item + '?resource=serials', trackingRequest, value => {
    if (value.company_id !== company || value.item_id !== item || !value.serial_tracking || !value.source_digest || !Array.isArray(value.requirements)) throw { status: 502, message: 'The product serial profile could not be verified.' };
  });
  const fields = useServiceRead<components['schemas']['FieldSet']>(base + '/field-set?action=prepare', trackingRequest, value => {
    if (value.resource !== 'stock-serials' || !Array.isArray(value.fields)) throw { status: 502, message: 'Serial field access could not be verified.' };
  });
  const command = useServiceCommand(trackingRequest, 'serial registration', scope ? { storageKey: storeKey + ':command', targetPath: base } : undefined);
  const rules = source.data?.requirements ?? [];
  const slots = rules.flatMap(rule => Array.from({ length: rule.max_count }, (_, index) => ({ value: `${rule.identifier_type}:${index + 1}`, label: `${rule.identifier_type} ${index + 1}` })));
  const completed = queue?.units.filter(unit => unit.id).length ?? 0;
  const locked = working || !!queue && !editingQueue || command.uncertain || !!restored.error;
  const canReadIdentifiers = fields.data?.fields.some(field => field.key === 'identifiers' && field.readable);
  const remember = (next: RegistrationQueue) => {
    if (!storeKey) throw Error('Refresh your signed-in session before registering serials.');
    sessionStorage.setItem(storeKey, JSON.stringify(next));
    queueNow.current = next; setQueue(next);
  };
  useEffect(() => {
    if (!command.failure || command.uncertain || ![409, 422].includes(command.failure.status)) return;
    const current = queueNow.current, index = current?.units.findIndex(unit => !unit.id) ?? -1;
    if (!current || index < 0 || current.units[index]?.rejected) return;
    try { remember({ units: current.units.map((unit, at) => at === index ? { ...unit, rejected: true } : unit) }); }
    catch { setFailure('The rejected unit could not be checkpointed. Retry its original registration after storage is restored.'); }
  }, [command.failure, command.uncertain]);
  const addScan = () => {
    if (locked || !trimSerialIdentifier(scan)) return;
    if (rows.length >= (replacement ? 1 : 200)) { setFailure('The queue is full. Complete it before adding more units.'); return; }
    const [type, slot] = (scanSlot || slots[0]?.value || '').split(':');
    if (type !== 'SERIAL' && type !== 'IMEI') return;
    setRows([...rows, { key: crypto.randomUUID(), identifiers: [{ identifier_type: type, slot: Number(slot), value: scan }] }]);
    setScan(''); setErrors({}); setFailure('');
  };
  async function register() {
    if (busy.current || restored.error || !scope || !fields.data || !source.data || fields.failure || source.failure) return;
    busy.current = true; setWorking(true); setFailure('');
    try {
      let next = queueNow.current;
      if (!next || editingQueue) {
        const problems: Record<string, string> = {}, seen = new Set<string>();
        const completedUnits = next?.units.filter(unit => unit.id) ?? [];
        for (const unit of completedUnits) validateSerialIdentifiers(unit.body.identifiers, rules, { seen, skuKey: item });
        const units = rows.map((row, index) => {
          const validated = validateSerialIdentifiers(row.identifiers, rules, { prefix: `serials.${index}.identifiers`, seen, skuKey: item, omitEmpty: true });
          Object.assign(problems, validated.errors);
          const result = trackingBody('serials', 'prepare', fields.data!.fields, { item_id: item, lot_id: lot, identifiers: validated.identifiers, reason }, undefined, source.data);
          for (const [key, message] of Object.entries(result.errors)) problems[key === 'identifiers' ? `serials.${index}.identifiers` : key] = message;
          if (replacement && (!fields.data!.fields.some(field => field.key === 'replaces_unit_id' && field.writable && field.visible)
            || !fields.data!.fields.some(field => field.key === 'expected_replaced_version' && field.writable && field.visible))) problems.replacement = 'Replacement field access is required.';
          return { key: row.key, body: { ...result.body, ...(replacement ? { replaces_unit_id: replacement.id, expected_replaced_version: replacement.row_version } : {}) } as RegistrationBody };
        });
        if (!units.length || units.length > (replacement ? 1 : 200)) problems.serials = 'Enter the units to register.';
        setErrors(problems); if (Object.keys(problems).length) return;
        next = { units: [...completedUnits, ...units] }; remember(next); setEditingQueue(false); // Persist all fixed unit keys before the first native write.
      }
      for (let index = 0; index < next.units.length; index++) {
        const unit: RegistrationUnit = next.units[index]!;
        if (unit.id) continue;
        if (command.uncertain && command.restoredRequest && JSON.stringify(command.restoredRequest.body) !== JSON.stringify(unit.body)) throw Error('The pending serial command differs from this queue. Review its native history before continuing.');
        const verify = (row: components['schemas']['SerialDetail']) => {
          if (!trackingId.test(row.id) || row.company_id !== company || row.item_id !== item || (row.lot_id ?? '') !== (lot ?? '') || row.id === replacement?.id) throw { status: 502, message: 'The registered serial could not be verified.' };
        };
        const saved: components['schemas']['SerialDetail'] | null = command.uncertain
          ? await command.retry<components['schemas']['SerialDetail']>(verify)
          : await command.execute<components['schemas']['SerialDetail']>({ path: base, method: 'POST', body: unit.body, key: unit.key }, verify);
        if (!saved) return;
        next = { units: next.units.map((value, at) => at === index ? { ...value, id: saved.id } : value) };
        remember(next); // A crash before this checkpoint replays that unit's original key.
      }
    } catch (error) { setFailure(error instanceof Error ? error.message : 'The serial queue could not be saved.'); }
    finally { busy.current = false; setWorking(false); }
  }
  async function useRegistered() {
    if (busy.current || !queue || !onRegistered || completed !== queue.units.length) return;
    busy.current = true; setWorking(true); setFailure('');
    try {
      if (forReceipt) for (const unit of queue.units) {
        const query = new URLSearchParams({ id: unit.id!, item_id: item, receipt_eligible: 'true', status: 'ACTIVE', is_held: 'false', limit: '1' });
        if (lot) query.set('lot_id', lot);
        const page = await trackingRequest<{ items: components['schemas']['SerialListItem'][] }>({ path: base + '?' + query });
        if (!Array.isArray(page.items) || page.items.length !== 1 || page.items[0]?.id !== unit.id || page.items[0].item_id !== item || (page.items[0].lot_id ?? '') !== (lot ?? '') || page.items[0].status !== 'ACTIVE' || page.items[0].is_held !== false) throw Error('A registered unit is no longer available for this receipt. Review its stock history and choose another serial.');
      }
      onRegistered(queue.units.map(unit => unit.id!));
    } catch (error) { setFailure(error instanceof Error ? error.message : 'Serial receipt availability could not be verified.'); }
    finally { busy.current = false; setWorking(false); }
  }
  return <section className="janso-flow" aria-label={replacement ? 'Replace unused serial' : 'Register serial units'}>
    <p>{replacement ? 'The original identifiers stay reserved. A successful replacement retires the original and links both histories.' : 'Scan one identifier per unit, then fill any additional required slots. Registration prepares units for a later receipt.'}</p>
    {!scope && <Notice tone="danger">Refresh your signed-in session before registering serials.</Notice>}
    <AccessFailure failure={source.failure ?? fields.failure} refresh={() => { source.refresh(); fields.refresh(); }} />
    {source.loading || fields.loading ? <p role="status">Loading serial requirements and field access…</p> : null}
    {(!queue || editingQueue) && source.data && fields.data && <>
      <div className="janso-form-grid">
        <Select label="Scanner identifier slot" value={scanSlot || slots[0]?.value || ''} options={slots} disabled={locked} onChange={setScanSlot} />
        <TextField label="Scan or enter identifier" value={scan} maxLength={240} disabled={locked} onChange={event => setScan(event.target.value)} onKeyDown={event => { if (event.key === 'Enter') { event.preventDefault(); addScan(); } }} />
        <Button type="button" variant="ghost" disabled={locked} onClick={addScan}>Add scanned unit</Button>
      </div>
      <AdvancedOpeningSerials title="Units to register" rows={rows} requirements={rules} maximum={replacement ? 1 : 200} errors={errors} disabled={locked || !fields.data.fields.some(field => field.key === 'identifiers' && field.visible && field.writable)} onChange={setRows} />
      <TextField label="Registration reason" value={reason} maxLength={500} required error={errors.reason} disabled={locked || !fields.data.fields.some(field => field.key === 'reason' && field.visible && field.writable)} onChange={event => setReason(event.target.value)} />
    </>}
    {queue && <><p role="status">{completed} of {queue.units.length} units registered.</p><ul>{queue.units.map((unit, index) => <li key={unit.key}>Unit {index + 1}: {unit.id ? <a className="janso-link" href={'/inventory/serials/' + unit.id}>View registered serial</a> : 'Awaiting registration'} — {canReadIdentifiers ? unit.body.identifiers.map(value => `${value.identifier_type} ${value.slot ?? 1}: ${value.value}`).join('; ') : 'Identifiers are protected.'}</li>)}</ul></>}
    <AccessFailure failure={command.failure} uncertain={command.uncertain} />
    {command.failure?.fields && <Notice tone="danger">{Object.values(command.failure.fields).join(' ')}</Notice>}
    {queue?.units.some(unit => unit.rejected) && canReadIdentifiers && !command.uncertain && !working && !editingQueue && <Button type="button" variant="ghost" onClick={() => { setRows(queue.units.filter(unit => !unit.id).map(unit => ({ key: crypto.randomUUID(), identifiers: unit.body.identifiers }))); setReason(queue.units.find(unit => !unit.id)?.body.reason ?? ''); command.clear(); setEditingQueue(true); }}>Correct remaining units</Button>}
    {failure && <Notice tone="danger">{failure}</Notice>}
    {Object.entries(errors).filter(([key]) => !key.startsWith('serials.') && key !== 'reason').map(([key, message]) => <Notice key={key} tone="danger">{message}</Notice>)}
    {!queue || completed < queue.units.length ? <Button type="button" loading={working} disabled={!scope || !!restored.error || source.loading || fields.loading || !!source.failure || !!fields.failure} onClick={() => void register()}>{queue && !editingQueue ? 'Retry remaining registrations' : replacement ? 'Create audited replacement' : `Register ${rows.length} units`}</Button> : <>
      {onRegistered && <Button type="button" loading={working} onClick={() => void useRegistered()}>Use registered units</Button>}
      {!replacement && <Button type="button" variant="ghost" onClick={() => { try { sessionStorage.removeItem(storeKey); command.clear(); queueNow.current = null; setQueue(null); setRows([]); setErrors({}); } catch { setFailure('Recovery storage is unavailable.'); } }}>Start another queue</Button>}
    </>}
  </section>;
}
