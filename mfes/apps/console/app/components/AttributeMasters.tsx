'use client';
import { useCallback, useRef, useState } from 'react';
import { AttributeValueInput, attributeValue, Button, Card, CardBody, FormActions, SectionHeader, SearchSelect, Select, TextField, type NativeAttributeValue, type SearchSelectLoader } from '@janso/ui';
import { productFieldRequest as request } from '../lib/product-fields';
type NativeField = { key: string; label: string; visible: boolean; writable: boolean; required: boolean; order: number; source: string };
type Definition = {
  id: string;
  name: string;
  code: string;
  row_version: number;
  value_type: string;
  measurement_dimension: string | null;
  is_variant_capable: boolean;
  is_active: boolean;
};
type Master = Record<string, unknown> & { id?: string; row_version?: number };
export function AttributeMasters({ company }: { company: string }) {
  const base = '/v1/companies/' + company;
  const [definition, setDefinition] = useState<Definition | null>(null),
    [editor, setEditor] = useState<{
      kind: 'definition' | 'option';
      row: Master;
      original: Master;
      unit: { id: string; label: string } | null;
      fields: NativeField[];
    } | null>(null);
  const [busy, setBusy] = useState(false),
    [message, setMessage] = useState('');
  const retry = useRef<{ payload: string; key: string } | null>(null);
  async function action(run: () => Promise<void>) {
    setBusy(true);
    setMessage('');
    try {
      await run();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Unable to save attribute master');
    } finally {
      setBusy(false);
    }
  }
  const lookup = useCallback(
    (kind: 'definitions' | 'options'): SearchSelectLoader =>
      async ({ q, cursor, signal }) => {
        const page = await request<{
          items: { id: string; name: string; code: string }[];
          page: { next_cursor: string | null };
        }>(
          'catalog',
          'GET',
          base +
            '/attribute-' +
            kind +
            '?q=' +
            encodeURIComponent(q) +
            (kind === 'options' && definition ? '&definition_id=' + definition.id : '') +
            (cursor ? '&cursor=' + encodeURIComponent(cursor) : ''),
          undefined,
          undefined,
          signal,
        );
        return {
          items: page.items.map((row) => ({ id: row.id, label: row.name, meta: row.code })),
          nextCursor: page.page.next_cursor,
        };
      },
    [base, definition],
  );
  const units = useCallback<SearchSelectLoader>(
    async ({ q, cursor, signal }) => {
      const page = await request<{
        items: { id: string; name: string }[];
        page: { next_cursor: string | null };
      }>(
        'catalog',
        'GET',
        base +
          '/units?is_active=true&q=' +
          encodeURIComponent(q) +
          (definition?.measurement_dimension
            ? '&dimension=' + definition.measurement_dimension
            : '') +
          (cursor ? '&cursor=' + encodeURIComponent(cursor) : ''),
        undefined,
        undefined,
        signal,
      );
      return {
        items: page.items.map((row) => ({ id: row.id, label: row.name })),
        nextCursor: page.page.next_cursor,
      };
    },
    [base, definition],
  );
  async function edit(kind: 'definition' | 'option', id?: string) {
    const metadata = await request<{ fields: NativeField[] }>(
      'catalog',
      'GET',
      base +
        '/entities/catalog.attribute_' +
        kind +
        '/field-set?operation=' +
        (id ? 'update&object_id=' + id : 'create'),
    );
    const row = id
      ? await request<Master>('catalog', 'GET', base + '/attribute-' + kind + 's/' + id)
      : kind === 'definition'
        ? {
            code: '',
            name: '',
            value_type: 'TEXT',
            measurement_dimension: null,
            is_variant_capable: false,
          }
        : { code: '', name: '', definition_id: definition!.id, value_type: definition!.value_type };
    const unit =
      kind === 'option' &&
      typeof row.unit_id === 'string' &&
      metadata.fields.some((field) => field.key === 'unit_id' && field.visible)
        ? { id: row.unit_id, label: row.unit_id }
        : null;
    if (unit) {
      // Optional label enrichment must not prevent an otherwise authorized edit.
      const detail = await request<{ name?: string }>(
        'catalog',
        'GET',
        base + '/units/' + unit.id,
      ).catch(() => null);
      if (detail?.name) unit.label = detail.name;
    }
    setEditor({ kind, row, original: { ...row }, unit, fields: metadata.fields });
  }
  async function save(lifecycle?: 'activate' | 'deactivate') {
    if (!editor) return;
    const route =
      base +
      '/attribute-' +
      editor.kind +
      's' +
      (editor.row.id ? '/' + editor.row.id : '') +
      (lifecycle ? '/' + lifecycle : '');
    const method = lifecycle ? 'POST' : editor.row.id ? 'PATCH' : 'POST';
    const body: Record<string, unknown> = editor.row.id
      ? { expected_version: editor.row.row_version }
      : {};
    if (!lifecycle) {
      for (const field of editor.fields) {
        if (
          field.writable &&
          !['is_active', 'row_version'].includes(field.key) &&
          field.key in editor.row &&
          (!editor.row.id || editor.row[field.key] !== editor.original[field.key])
        )
          body[field.key] = editor.row[field.key];
      }
      if (editor.kind === 'option') {
        const value = Object.fromEntries(
          ['unit_id', 'value_text', 'value_integer', 'value_decimal', 'value_boolean', 'value_date']
            .filter((key) => editor.row[key] != null)
            .map((key) => [key, editor.row[key]]),
        );
        if (
          !editor.row.id ||
          Object.keys(body).some((key) => key.startsWith('value_') || key === 'unit_id')
        ) {
          attributeValue({
            definition_id: definition!.id,
            value_type: definition!.value_type,
            ...value,
          });
        }
        if (!editor.row.id) {
          body.definition_id = definition!.id;
          body.value_type = definition!.value_type;
        } else {
          delete body.definition_id;
          delete body.value_type;
        }
      }
    }
    const payload = JSON.stringify({ route, method, body });
    if (retry.current?.payload !== payload) retry.current = { payload, key: crypto.randomUUID() };
    const result = await request<Master>('catalog', method, route, body, retry.current!.key);
    retry.current = null;
    if (editor.kind === 'definition') setDefinition(result as Definition);
    setEditor(null);
    setMessage('Attribute ' + editor.kind + ' saved.');
  }
  const set = (key: string, value: unknown) =>
    setEditor((old) => (old ? { ...old, row: { ...old.row, [key]: value } } : null));
  return (
    <section aria-label="Attribute masters" className="janso-flow">
      <SectionHeader title="Attribute definitions and options" description="Define a specification once and reuse its options across product families." />
      {message && (
        <p role="status" aria-label="Master result">
          {message}
        </p>
      )}
      <SearchSelect
        label="Find attribute definition"
        scopeKey={company}
        value={definition?.id ?? null}
        selected={definition ? { id: definition.id, label: definition.name } : null}
        disabled={busy}
        loadOptions={lookup('definitions')}
        onChange={(id) => {
          setDefinition(null);
          setEditor(null);
          if (id)
            void action(async () =>
              setDefinition(
                await request<Definition>('catalog', 'GET', base + '/attribute-definitions/' + id),
              ),
            );
        }}
      />
      <Button disabled={busy} onClick={() => void action(() => edit('definition'))}>
        New attribute definition
      </Button>
      {definition && (
        <>
          <Button
            disabled={busy}
            onClick={() => void action(() => edit('definition', definition.id))}
          >
            Edit {definition.name}
          </Button>
          <SearchSelect
            label={'Find ' + definition.name + ' option'}
            scopeKey={JSON.stringify([company, definition.id])}
            value={null}
            disabled={busy}
            loadOptions={lookup('options')}
            onChange={(id) => {
              if (id) void action(() => edit('option', id));
            }}
          />
          <Button
            disabled={busy || !definition.is_active}
            onClick={() => void action(() => edit('option'))}
          >
            New {definition.name} option
          </Button>
        </>
      )}
      {editor && (
        <form
          aria-label={'Edit attribute ' + editor.kind}
          onSubmit={(event) => {
            event.preventDefault();
            void action(() => save());
          }}
        ><Card><CardBody><div className="janso-flow"><SectionHeader title={'Edit attribute ' + editor.kind} /><div className="janso-form-grid">
          {editor.fields
            .filter((f) => f.source === 'native' && f.visible)
            .sort((a, b) => a.order - b.order)
            .map((field) => {
              const common = {
                label: field.label,
                disabled: busy || !field.writable,
                required: field.required,
              };
              if (['code', 'name'].includes(field.key))
                return (
                  <TextField
                    key={field.key}
                    {...common}
                    value={String(editor.row[field.key] ?? '')}
                    onChange={(e) => set(field.key, e.target.value)}
                  />
                );
              if (editor.kind !== 'definition') return null;
              if (field.key === 'value_type')
                return (
                  <Select
                    key={field.key}
                    {...common}
                    value={String(editor.row.value_type)}
                    options={['TEXT', 'INTEGER', 'DECIMAL', 'BOOLEAN', 'DATE'].map((value) => ({
                      value,
                      label: value,
                    }))}
                    onChange={(value) => {
                      setEditor({
                        ...editor,
                        row: { ...editor.row, value_type: value, measurement_dimension: null },
                      });
                    }}
                  />
                );
              if (field.key === 'measurement_dimension')
                return (
                  <Select
                    key={field.key}
                    {...common}
                    disabled={
                      common.disabled ||
                      !['INTEGER', 'DECIMAL'].includes(String(editor.row.value_type))
                    }
                    value={String(editor.row.measurement_dimension ?? '')}
                    placeholder="No measurement unit"
                    options={['COUNT', 'MASS', 'VOLUME', 'LENGTH', 'AREA', 'TIME', 'JOB'].map(
                      (value) => ({ value, label: value }),
                    )}
                    onChange={(v) => set(field.key, v || null)}
                  />
                );
              if (field.key === 'is_variant_capable')
                return (
                  <Select
                    key={field.key}
                    {...common}
                    value={editor.row.is_variant_capable ? 'true' : 'false'}
                    options={[
                      { value: 'false', label: 'Specification only' },
                      { value: 'true', label: 'May distinguish variants' },
                    ]}
                    onChange={(v) => set(field.key, v === 'true')}
                  />
                );
              return null;
            })}
          {editor.kind === 'option' &&
            definition &&
            editor.fields.some(
              (f) => f.key === 'value_' + definition.value_type.toLowerCase() && f.visible,
            ) && (
              <AttributeValueInput
                field={{
                  definition_id: definition.id,
                  label: 'Option value',
                  value_type: definition.value_type,
                  measurement_dimension: definition.measurement_dimension,
                  unit_visible: editor.fields.some(
                    (field) => field.key === 'unit_id' && field.visible,
                  ),
                  unit_label: editor.unit?.label,
                  value: {
                    definition_id: definition.id,
                    value_type: definition.value_type,
                    unit_id: editor.unit?.id,
                  },
                  is_axis: false,
                  is_required: true,
                  writable: editor.fields
                    .filter(
                      (f) =>
                        f.key === 'unit_id' ||
                        f.key === 'value_' + definition.value_type.toLowerCase(),
                    )
                    .every((f) => f.writable),
                  allowed_options: [],
                }}
                value={
                  {
                    ...editor.row,
                    definition_id: definition.id,
                    value_type: definition.value_type,
                  } as NativeAttributeValue
                }
                disabled={busy}
                loadUnits={units}
                onChange={(value) =>
                  setEditor({
                    ...editor,
                    row: {
                      ...editor.row,
                      unit_id: null,
                      value_text: null,
                      value_integer: null,
                      value_decimal: null,
                      value_boolean: null,
                      value_date: null,
                      ...value,
                    },
                  })
                }
              />
            )}
          </div></div></CardBody><FormActions cancel={{ onCancel: () => setEditor(null), disabled: busy, label: 'Cancel master edit' }}>
          {editor.row.id && editor.fields.some((f) => f.key === 'is_active' && f.writable) && (
            <Button
              type="button"
              variant={editor.row.is_active ? 'danger' : 'ghost'}
              disabled={busy}
              onClick={() =>
                void action(() => save(editor.row.is_active ? 'deactivate' : 'activate'))
              }
            >
              {editor.row.is_active ? 'Deactivate' : 'Activate'} attribute {editor.kind}
            </Button>
          )}
          <Button type="submit" loading={busy}>
            Save attribute {editor.kind}
          </Button>
        </FormActions></Card></form>
      )}
    </section>
  );
}
