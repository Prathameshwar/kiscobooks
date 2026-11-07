"use client";
import { useEffect, useRef, useState } from "react";
import {
  Button,
  ConfirmDialog,
  Card,
  CardBody,
  FieldGroup,
  FormActions,
  Notice,
  PageHeader,
  PageNavigation,
  Pager,
  ReviewList,
  Select,
  TextField,
  useFormatters,
  useDisplayConfig,
} from "@janso/ui";
import type { components } from "@janso/api-client/accounting";
import {
  trackingBase,
  trackingId,
  trackingTitle,
  type TrackingKind,
  type TrackingListRow,
  type TrackingSource,
} from "../lib/stock-tracking-resources";
import {
  trackingBody,
  type TrackingAction,
} from "../lib/stock-tracking-command";
import { trackingRequest } from "../lib/stock-tracking";
import {
  useServiceRead,
  useServiceList,
  useServiceCommand,
} from "../lib/service-resource";
import { AccessFailure, useAccessDraft } from "./AccessCommon";
import { TrackingReference } from "./StockTrackingCommon";
import { AdvancedProductChoice } from "./AdvancedProductChoice";
import { SerialRegistration } from './SerialRegistration';
type Detail =
  | components["schemas"]["BatchDetail"]
  | components["schemas"]["SerialDetail"];
type Fields = components["schemas"]["FieldSet"];
type Event = components["schemas"]["TrackingEventItem"];
type EventDetail = components["schemas"]["TrackingEventDetail"];
export type TrackingAccess = { manage: boolean; hold: boolean };
function verifyRecord(row: Detail, company: string, id?: string) {
  if (
    !trackingId.test(row.id) ||
    row.company_id !== company ||
    (id && row.id !== id)
  )
    throw {
      status: 502,
      message: "The tracking record did not match this company.",
    };
}
function verifyFields(value: Fields, kind: TrackingKind) {
  if (
    value.resource !==
      (kind === "batches" ? "stock-batches" : "stock-serials") ||
    !Array.isArray(value.fields)
  )
    throw {
      status: 502,
      message: "Tracking field access could not be verified.",
    };
}
export function StockTrackingPage({
  company,
  kind,
  id,
  page = "list",
  eventId,
  itemId,
  access,
  recoveryScope,
}: {
  company: string;
  kind: TrackingKind;
  id?: string;
  page?: "list" | "new" | "detail" | "edit" | "history" | 'register' | 'replace';
  eventId?: string;
  itemId?: string;
  access: TrackingAccess;
  recoveryScope?: string;
}) {
  const href = "/inventory/" + kind,
    singular = kind === "batches" ? "batch" : "serial",
    title =
      page === "list"
        ? kind === "batches"
          ? "Batches"
          : "Serials"
        : page === 'register' ? 'Register serial units'
        : page === 'replace' ? 'Replace unused serial'
        : page === "new"
          ? "Register " + singular
          : page === "edit"
            ? "Edit " + singular
            : page === "history"
              ? singular.charAt(0).toUpperCase() +
                singular.slice(1) +
                " history"
              : singular.charAt(0).toUpperCase() +
                singular.slice(1) +
                " details";
  return (
    <div className="janso-page janso-product-management">
      <PageNavigation
        back={{
          href: id && page !== "detail" ? href + "/" + id : href,
          label: kind,
        }}
        breadcrumbs={[
          { label: "Inventory", href: "/inventory" },
          { label: kind === "batches" ? "Batches" : "Serials", href },
          { label: title },
        ]}
      />
      <PageHeader
        title={title}
        lede="Physical tracking records, controlled changes and audit history."
        actions={
          page === "list" && access.manage ? (
            <div className="janso-form-actions"><a
              className="janso-btn janso-btn--primary"
              href={href + "/new" + (itemId ? "?item_id=" + itemId : "")}
            >
              Register {singular}
            </a>{kind === 'serials' && <a className="janso-btn janso-btn--secondary" href={href + '/register' + (itemId ? '?item_id=' + itemId : '')}>Register or scan units</a>}</div>
          ) : undefined
        }
      />
      {page === "list" ? (
        <TrackingDirectory company={company} kind={kind} itemId={itemId} />
      ) : page === 'register' ? (
        <TrackingRegistration company={company} itemId={itemId} recoveryScope={recoveryScope} />
      ) : page === "new" ? (
        <TrackingEditor
          company={company}
          kind={kind}
          itemId={itemId}
          access={access}
          recoveryScope={recoveryScope}
        />
      ) : page === "history" && id ? (
        <TrackingHistory
          company={company}
          kind={kind}
          id={id}
          eventId={eventId}
        />
      ) : id ? (
        <TrackingRecord
          company={company}
          kind={kind}
          id={id}
          editing={page === "edit"}
          replacing={page === 'replace'}
          access={access}
          recoveryScope={recoveryScope}
        />
      ) : null}
    </div>
  );
}
function TrackingDirectory({
  company,
  kind,
  itemId,
}: {
  company: string;
  kind: TrackingKind;
  itemId?: string;
}) {
  const [q, setQ] = useState(""),
    [status, setStatus] = useState(""),
    [held, setHeld] = useState("");
  const params = new URLSearchParams();
  if (itemId) params.set("item_id", itemId);
  if (q.trim().length >= 2) params.set("q", q.trim());
  if (status) params.set("status", status);
  if (held) params.set("is_held", held);
  const list = useServiceList<TrackingListRow>(
    trackingBase(company, kind),
    params.toString(),
    trackingRequest,
    (row) => {
      if (!trackingId.test(row.id))
        throw { status: 502, message: "Tracking list could not be verified." };
    },
  );
  const format = useFormatters();
  return (
    <div className="janso-flow">
      <Card>
        <CardBody>
          <div className="janso-form-grid">
            <TextField
              label="Search tracking records"
              value={q}
              hint="Enter at least two characters."
              onChange={(event) => setQ(event.target.value)}
            />
            <Select
              label="Status"
              value={status}
              placeholder="All statuses"
              options={[
                { value: "ACTIVE", label: "Active" },
                { value: "RETIRED", label: "Retired" },
              ]}
              onChange={setStatus}
            />
            <Select
              label="Hold status"
              value={held}
              placeholder="All records"
              options={[
                { value: "true", label: "On hold" },
                { value: "false", label: "Not held" },
              ]}
              onChange={setHeld}
            />
          </div>
          {itemId && (
            <p>
              Filtered to{" "}
              <a className="janso-link" href={"/masters/items/" + itemId}>
                this product / SKU
              </a>
              .{" "}
              <a className="janso-link" href={"/inventory/" + kind}>
                Clear product filter
              </a>
            </p>
          )}
        </CardBody>
      </Card>
      <AccessFailure failure={list.failure} refresh={list.refresh} />
      {list.loading ? (
        <p role="status">Loading tracking records...</p>
      ) : (
        list.data && (
          <Card>
            <CardBody>
              <div className="janso-flow">
                {!list.data.items.length ? (
                  <Notice tone="info">
                    No matching {kind}. Change the filters or register a
                    tracking record.
                  </Notice>
                ) : (
                  list.data.items.map((row) => (
                    <FieldGroup
                      key={row.id}
                      title={trackingTitle(row)}
                      headerEnd={
                        <a
                          className="janso-link"
                          href={"/inventory/" + kind + "/" + row.id}
                        >
                          View details
                        </a>
                      }
                    >
                      <ReviewList
                        items={[
                          { label: "Status", value: row.status ?? "Protected" },
                          {
                            label: "Hold",
                            value:
                              row.is_held === true
                                ? "On hold"
                                : row.is_held === false
                                  ? "Not held"
                                  : "Protected",
                          },
                          ...("expires_on" in row
                            ? [
                                {
                                  label: "Expiry",
                                  value: row.expires_on
                                    ? format.date(row.expires_on)
                                    : "Not set",
                                },
                              ]
                            : []),
                        ]}
                      />
                      <a
                        className="janso-link"
                        href={"/inventory/" + kind + "/" + row.id + "/history"}
                      >
                        View history
                      </a>
                    </FieldGroup>
                  ))
                )}
              </div>
            </CardBody>
            <Pager
              count={list.data.items.length}
              limit={list.limit}
              hasPrevious={list.hasPrevious}
              hasNext={list.data.page.has_more}
              onPrevious={list.previous}
              onNext={list.next}
              onLimitChange={list.setLimit}
              busy={list.loading}
              noun={kind === "batches" ? "batch" : "serial"}
            />
          </Card>
        )
      )}
    </div>
  );
}
function TrackingRecord({
  company,
  kind,
  id,
  editing,
  replacing = false,
  access,
  recoveryScope,
}: {
  company: string;
  kind: TrackingKind;
  id: string;
  editing: boolean;
  replacing?: boolean;
  access: TrackingAccess;
  recoveryScope?: string;
}) {
  const read = useServiceRead<Detail>(
      trackingBase(company, kind) + "/" + id,
      trackingRequest,
      (row) => verifyRecord(row, company, id),
    ),
    format = useFormatters();
  return (
    <div className="janso-flow">
      <AccessFailure failure={read.failure} refresh={read.refresh} />
      {read.loading ? (
        <p role="status">Loading tracking record...</p>
      ) : (
        read.data && (
          <>
            <Card>
              <CardBody>
                <div className="janso-flow">
                  <h2>{trackingTitle(read.data)}</h2>
                  <ReviewList
                    items={[
                      {
                        label: "Status",
                        value: read.data.status ?? "Protected",
                      },
                      {
                        label: "Hold",
                        value:
                          read.data.is_held === true
                            ? "On hold"
                            : read.data.is_held === false
                              ? "Not held"
                              : "Protected",
                      },
                      {
                        label: "Created",
                        value: format.dateTime(read.data.created_at),
                      },
                      ...("manufactured_on" in read.data
                        ? [
                            {
                              label: "Manufactured",
                              value: read.data.manufactured_on
                                ? format.date(read.data.manufactured_on)
                                : "Not set",
                            },
                            {
                              label: "Expiry",
                              value: read.data.expires_on
                                ? format.date(read.data.expires_on)
                                : "Not set",
                            },
                          ]
                        : []),
                      ...("mrp_amount" in read.data &&
                      read.data.mrp_amount &&
                      read.data.mrp_currency
                        ? [
                            {
                              label: "MRP",
                              value:
                                format.money(read.data.mrp_amount, {
                                  display: "none",
                                }) +
                                " " +
                                read.data.mrp_currency,
                            },
                          ]
                        : []),
                    ]}
                  />
                  {"identifiers" in read.data && read.data.identifiers && (
                    <ReviewList
                      items={read.data.identifiers.map((identifier) => ({
                        label:
                          identifier.identifier_type + " " + identifier.slot,
                        value: identifier.value,
                      }))}
                    />
                  )}
                  {read.data.item_id && (
                    <a
                      className="janso-link"
                      href={"/masters/items/" + read.data.item_id}
                    >
                      View product / SKU
                    </a>
                  )}
                  {"lot_id" in read.data && read.data.lot_id && (
                    <a
                      className="janso-link"
                      href={"/inventory/batches/" + read.data.lot_id}
                    >
                      View batch
                    </a>
                  )}
                  <Notice tone="info">
                    Registration alone does not create stock or value. Receipts
                    and stock postings determine availability.
                  </Notice>
                  <div className="janso-form-actions">
                    {kind === 'serials' && access.manage && read.data.status === 'ACTIVE' && read.data.is_held === false && !replacing && <a className="janso-btn janso-btn--secondary" href={'/inventory/serials/' + id + '/replace'}>Replace unused serial</a>}
                    {!editing && (access.manage || access.hold) && (
                      <a
                        className="janso-btn janso-btn--primary"
                        href={"/inventory/" + kind + "/" + id + "/edit"}
                      >
                        Edit {kind === "batches" ? "batch" : "serial"}
                      </a>
                    )}
                    <a
                      className="janso-link"
                      href={"/inventory/" + kind + "/" + id + "/history"}
                    >
                      View history
                    </a>
                  </div>
                </div>
              </CardBody>
            </Card>
            {editing && (
              <TrackingEditor
                key={id + ":" + read.data.row_version}
                company={company}
                kind={kind}
                row={read.data}
                access={access}
                recoveryScope={recoveryScope}
                refresh={read.refresh}
              />
            )}
            {replacing && kind === 'serials' && access.manage && read.data.item_id && read.data.row_version && 'identifiers' in read.data && read.data.identifiers && (
              <SerialRegistration key={id} company={company} item={read.data.item_id} lot={'lot_id' in read.data ? read.data.lot_id ?? undefined : undefined} recoveryScope={recoveryScope} replacement={{ id, item_id: read.data.item_id, lot_id: 'lot_id' in read.data ? read.data.lot_id : undefined, row_version: read.data.row_version }} />
            )}
          </>
        )
      )}
    </div>
  );
}
function TrackingRegistration({ company, itemId, recoveryScope }: { company: string; itemId?: string; recoveryScope?: string }) {
  const [item, setItem] = useState(itemId ?? ''), [lot, setLot] = useState('');
  const source = useServiceRead<TrackingSource>(trackingId.test(item) ? trackingBase(company) + '/context/' + item + '?resource=serials' : undefined, trackingRequest,
    value => { if (value.company_id !== company || value.item_id !== item || !Array.isArray(value.requirements)) throw { status: 502, message: 'The product tracking source could not be verified.' }; });
  const fields = useServiceRead<Fields>(trackingBase(company, 'serials') + '/field-set?action=prepare', trackingRequest, value => verifyFields(value, 'serials'));
  const writable = (key: string) => fields.data?.fields.some(field => field.key === key && field.visible && field.writable);
  return <Card><CardBody><div className="janso-flow">
    <AccessFailure failure={source.failure ?? fields.failure} refresh={() => { source.refresh(); fields.refresh(); }} />
    <TrackingReference company={company} resource="items" label="Product / SKU" value={item || null} disabled={!writable('item_id')} onChange={value => { setItem(value ?? ''); setLot(''); }} required />
    {source.data?.lot_tracking && <TrackingReference company={company} resource="batches" itemId={item} label="Batch" value={lot || null} disabled={!writable('lot_id')} required onChange={value => setLot(value ?? '')} />}
    {source.data?.serial_tracking && (!source.data.lot_tracking || lot) && <SerialRegistration key={item + ':' + lot} company={company} item={item} lot={lot || undefined} recoveryScope={recoveryScope} />}
    {source.data && !source.data.serial_tracking && <Notice tone="warning">This product does not enable serial tracking.</Notice>}
  </div></CardBody></Card>;
}
function TrackingEditor({
  company,
  kind,
  itemId,
  row,
  access,
  refresh,
  recoveryScope,
}: {
  company: string;
  kind: TrackingKind;
  itemId?: string;
  row?: Detail;
  access: TrackingAccess;
  refresh?: () => void;
  recoveryScope?: string;
}) {
  const [action, setAction] = useState<TrackingAction>(
      row
        ? kind === "batches" && access.manage
          ? "correct"
          : row.is_held === true
            ? "release"
            : "hold"
        : "prepare",
    ),
    [values, setValues] = useState<Record<string, unknown>>(
      row
        ? {
            ...("manufactured_on" in row
              ? {
                  manufactured_on: row.manufactured_on ?? "",
                  expires_on: row.expires_on ?? "",
                }
              : {}),
            reason: "",
          }
        : { item_id: itemId ?? "", reason: "" },
    ),
    [dirty, setDirty] = useState(false),
    [changedKeys, setChangedKeys] = useState<string[]>([]),
    [errors, setErrors] = useState<Record<string, string>>({}),
    [saved, setSaved] = useState<Detail | null>(null),
    [reload, setReload] = useState(false);
  const currency = useDisplayConfig().currency;
  const command = useServiceCommand(trackingRequest, "tracking change", recoveryScope ? {
      storageKey: `tracking-command:${recoveryScope}:${company}:${kind}:${row?.id ?? 'new'}`,
      targetPath: trackingBase(company, kind) + (row ? '/' + row.id : ''),
    } : undefined),
    guard = useAccessDraft(dirty || command.uncertain, command.pending),
    form = useRef<HTMLFormElement>(null),
    base = trackingBase(company, kind),
    product = String(values.item_id ?? "");
  useEffect(() => {
    const request = command.restoredRequest;
    if (!request) return;
    const suffix = request.path.split('/').at(-1);
    setAction(row ? request.method === 'PATCH' ? 'correct' : suffix as TrackingAction : 'prepare');
    setValues(request.body as Record<string, unknown>);
    setDirty(true);
  }, [command.restoredRequest]);
  const metadata = useServiceRead<Fields>(
    base + "/field-set?action=" + action,
    trackingRequest,
    (value) => verifyFields(value, kind),
  );
  const source = useServiceRead<TrackingSource>(
    !row && trackingId.test(product)
      ? trackingBase(company) + "/context/" + product + "?resource=" + kind
      : undefined,
    trackingRequest,
    (value) => {
      if (
        value.company_id !== company ||
        value.item_id !== product ||
        !value.source_digest ||
        !Array.isArray(value.requirements)
      )
        throw {
          status: 502,
          message: "The product tracking source could not be verified.",
        };
    },
  );
  const fields = metadata.data?.fields ?? [],
    canWrite =
      action === "hold" || action === "release" ? access.hold : access.manage,
    locked =
      command.blocked ||
      !!saved ||
      !canWrite ||
      metadata.loading ||
      !!metadata.failure;
  const writable = (key: string) =>
      fields.some(
        (field) => field.key === key && field.visible && field.writable,
      ),
    visible = (key: string) =>
      fields.some((field) => field.key === key && field.visible && (!command.restoredRequest || field.readable));
  const change = (key: string, value: unknown) => {
    if (locked) return;
    command.clear();
    setErrors({});
    setDirty(true);
    setChangedKeys((current) =>
      current.includes(key) ? current : [...current, key],
    );
    setValues((current) => ({
      ...current,
      [key]: value,
      ...(key === "mrp_amount"
        ? {
            mrp_currency: value ? currency : "",
            mrp_unit_id: value ? (source.data?.base_unit_id ?? "") : "",
          }
        : {}),
      ...(key === "item_id"
        ? {
            lot_id: "",
            identifiers: [],
            mrp_amount: "",
            mrp_currency: "",
            mrp_unit_id: "",
          }
        : {}),
    }));
  };
  async function save() {
    if (command.pending) return;
    const verify = (receipt: Detail) => verifyRecord(receipt, company, row?.id);
    if (command.uncertain) {
      const result = await command.retry<Detail>(verify);
      if (result) {
        setSaved(result);
        setDirty(false);
      }
      return;
    }
    if (locked || !canWrite || !metadata.data) return;
    if (!row && (!source.data || source.data.item_id !== product)) {
      setErrors({
        item_id: "Choose a product with verified tracking settings.",
      });
      return;
    }
    const result = trackingBody(
      kind,
      action,
      fields,
      row && action === "correct"
        ? Object.fromEntries(
            Object.entries(values).filter(
              ([key]) => key === "reason" || changedKeys.includes(key),
            ),
          )
        : values,
      row?.row_version ?? undefined,
      source.data,
      row && "manufactured_on" in row ? row : undefined,
    );
    setErrors(result.errors);
    if (Object.keys(result.errors).length) {
      requestAnimationFrame(() =>
        form.current
          ?.querySelector<HTMLElement>('[aria-invalid="true"]')
          ?.focus(),
      );
      return;
    }
    const updated = await command.execute<Detail>(
      {
        path: row
          ? base + "/" + row.id + (action === "correct" ? "" : "/" + action)
          : base,
        method: action === "correct" ? "PATCH" : "POST",
        body: result.body,
      },
      verify,
    );
    if (updated) {
      setSaved(updated);
      setDirty(false);
    }
  }
  useEffect(() => {
    if (command.failure?.fields) {
      setErrors(command.failure.fields);
      requestAnimationFrame(() =>
        form.current
          ?.querySelector<HTMLElement>('[aria-invalid="true"]')
          ?.focus(),
      );
    }
  }, [command.failure]);
  const text = (key: string, label: string, type = "text", hint?: string) =>
    visible(key) ? (
      <TextField
        key={key}
        label={label}
        type={type}
        inputMode={key === "mrp_amount" ? "decimal" : undefined}
        hint={hint}
        required={fields.some((field) => field.key === key && field.required)}
        disabled={
          locked ||
          !writable(key) ||
          (key === "mrp_amount" &&
            (!writable("mrp_currency") ||
              !writable("mrp_unit_id") ||
              !source.data?.base_unit_id))
        }
        value={String(values[key] ?? "")}
        error={errors[key]}
        maxLength={
          key === "reason"
            ? 500
            : key === "code"
              ? 100
              : key === "mrp_currency"
                ? 3
                : undefined
        }
        onChange={(event) => change(key, event.target.value)}
      />
    ) : null;
  const actions: { value: TrackingAction; label: string }[] = [];
  if (row) {
    if (kind === "batches" && access.manage)
      actions.push({ value: "correct", label: "Correct dates" });
    if (access.hold && typeof row.is_held === "boolean")
      actions.push({
        value: row.is_held ? "release" : "hold",
        label: row.is_held ? "Release hold" : "Place on hold",
      });
    if (access.manage && row.status)
      actions.push({
        value: row.status === "RETIRED" ? "reactivate" : "retire",
        label: row.status === "RETIRED" ? "Reactivate" : "Retire",
      });
  }
  return (
    <form
      ref={form}
      noValidate
      aria-label={row ? "Edit tracking record" : "Register tracking record"}
      onSubmit={(event) => {
        event.preventDefault();
        void save();
      }}
    >
      <Card>
        <CardBody>
          <div className="janso-flow">
            {kind === "serials" && row && (
              <Notice tone="info">
                Serial identifiers and batch assignment are immutable. Use the
                supported hold or lifecycle action below; each change requires a
                reason and is recorded in history.
              </Notice>
            )}
            {row && (
              <Select
                label="Change to make"
                value={action}
                options={actions}
                disabled={
                  command.pending || command.uncertain || dirty || !!saved
                }
                onChange={(value) => {
                  setAction(value as TrackingAction);
                  command.clear();
                  setErrors({});
                }}
              />
            )}
            <AccessFailure
              failure={metadata.failure}
              refresh={metadata.refresh}
            />
            <AccessFailure failure={source.failure} refresh={source.refresh} />
            {metadata.loading ? (
              <p role="status">Loading field access...</p>
            ) : (
              metadata.data && (
                <>
                  {saved ? (
                    <Notice tone="success">
                      {row ? "Change saved." : "Tracking record registered."}{" "}
                      <a
                        className="janso-link"
                        href={"/inventory/" + kind + "/" + saved.id}
                      >
                        View {kind === "batches" ? "batch" : "serial"}
                      </a>
                      {refresh && (
                        <Button type="button" variant="ghost" onClick={refresh}>
                          Reload record
                        </Button>
                      )}
                    </Notice>
                  ) : (
                    <>
                      {!row && visible("item_id") && (
                        <TrackingReference
                          company={company}
                          resource="items"
                          label="Product / SKU"
                          value={product || null}
                          onChange={(value) => change("item_id", value ?? "")}
                          required
                          disabled={locked || !writable("item_id")}
                          error={errors.item_id}
                        />
                      )}
                      {source.loading && (
                        <p role="status">
                          Checking published tracking settings...
                        </p>
                      )}
                      <div className="janso-form-grid">
                        {!row &&
                          kind === "batches" &&
                          text("code", "Batch code")}
                        {kind === "batches" &&
                          ["prepare", "correct"].includes(action) && (
                            <>
                              {text(
                                "manufactured_on",
                                "Manufacture date",
                                "date",
                              )}
                              {text("expires_on", "Expiry date", "date")}
                            </>
                          )}
                        {!row &&
                          kind === "batches" &&
                          visible("source_party_id") && (
                            <TrackingReference
                              company={company}
                              resource="parties"
                              label="Supplier (optional)"
                              value={
                                String(values.source_party_id ?? "") || null
                              }
                              disabled={locked || !writable("source_party_id")}
                              error={errors.source_party_id}
                              onChange={(value) =>
                                change("source_party_id", value)
                              }
                            />
                          )}
                        {!row &&
                          kind === "serials" &&
                          source.data?.lot_tracking &&
                          visible("lot_id") && (
                            <TrackingReference
                              company={company}
                              resource="batches"
                              label="Batch"
                              itemId={product}
                              value={String(values.lot_id ?? "") || null}
                              required
                              disabled={locked || !writable("lot_id")}
                              error={errors.lot_id}
                              onChange={(value) => change("lot_id", value)}
                            />
                          )}
                      </div>
                      {!row && kind === "batches" && visible("mrp_amount") && (
                        <FieldGroup
                          title="MRP (optional)"
                          hint="MRP is recorded in the company currency per verified product base unit."
                        >
                          <div className="janso-form-grid">
                            {text("mrp_amount", "MRP amount")}
                            <TextField
                              label="MRP currency"
                              value={currency}
                              readOnly
                            />
                            {visible("mrp_unit_id") && (
                              <AdvancedProductChoice
                                company={company}
                                resource="units"
                                label="MRP unit"
                                selected="Product base unit"
                                value={source.data?.base_unit_id ?? ""}
                                disabled
                                error={errors.mrp_unit_id}
                                onChange={(id) => change("mrp_unit_id", id)}
                              />
                            )}
                          </div>
                        </FieldGroup>
                      )}
                      {!row &&
                        kind === "serials" &&
                        source.data &&
                        visible("identifiers") && (
                          <FieldGroup
                            title="Physical identifiers"
                            hint="Enter identifiers for one physical unit. The published profile determines the required types and slots."
                          >
                            <div className="janso-form-grid">
                              {(source.data.requirements ?? []).flatMap(
                                (rule) =>
                                  Array.from(
                                    { length: rule.max_count },
                                    (_, index) => {
                                      const slot = index + 1,
                                        identifiers = (values.identifiers ??
                                          []) as {
                                          identifier_type: "SERIAL" | "IMEI";
                                          slot: number;
                                          value: string;
                                        }[],
                                        current = identifiers.find(
                                          (value) =>
                                            value.identifier_type ===
                                              rule.identifier_type &&
                                            value.slot === slot,
                                        );
                                      return (
                                        <TextField
                                          key={rule.identifier_type + slot}
                                          label={
                                            rule.identifier_type + " " + slot
                                          }
                                          required={rule.min_count === rule.max_count}
                                          value={current?.value ?? ""}
                                          disabled={
                                            locked || !writable("identifiers")
                                          }
                                          maxLength={
                                            rule.identifier_type === "IMEI"
                                              ? 15
                                              : 240
                                          }
                                          error={errors.identifiers}
                                          onChange={(event) =>
                                            change("identifiers", [
                                              ...identifiers.filter(
                                                (value) => value !== current,
                                              ),
                                              ...(event.target.value
                                                ? [
                                                    {
                                                      identifier_type:
                                                        rule.identifier_type,
                                                      slot,
                                                      value: event.target.value,
                                                    },
                                                  ]
                                                : []),
                                            ])
                                          }
                                        />
                                      );
                                    },
                                  ),
                              )}
                            </div>
                          </FieldGroup>
                        )}
                      {text(
                        "reason",
                        "Reason",
                        "text",
                        "Explain the registration or change for the audit history.",
                      )}
                      {Object.keys(errors).length > 0 && (
                        <Notice tone="danger">
                          <ul>
                            {[...new Set(Object.values(errors))].map(
                              (error) => (
                                <li key={error}>{error}</li>
                              ),
                            )}
                          </ul>
                        </Notice>
                      )}
                    </>
                  )}
                </>
              )
            )}
            <AccessFailure
              failure={command.failure}
              uncertain={command.uncertain}
            />
            {command.failure && !command.uncertain && command.blocked && (
              <Button
                type="button"
                variant="ghost"
                onClick={() => setReload(true)}
              >
                Reload and review
              </Button>
            )}
            {command.failure?.fields && (
              <Notice tone="danger">
                {Object.values(command.failure.fields).join(" ")}
              </Notice>
            )}
          </div>
        </CardBody>
        {!saved && (
          <FormActions
            cancel={{
              href: "/inventory/" + kind + (row ? "/" + row.id : ""),
              onClick: guard.leave,
            }}
          >
            <Button
              type="submit"
              loading={command.pending}
              disabled={
                command.pending ||
                (!command.uncertain &&
                  (locked ||
                    !dirty ||
                    (!row && (!source.data || source.loading))))
              }
            >
              {command.uncertain
                ? "Retry same save"
                : row
                  ? "Save change"
                  : "Register " + (kind === "batches" ? "batch" : "serial")}
            </Button>
          </FormActions>
        )}
      </Card>
      {guard.confirmation}
      <ConfirmDialog
        open={reload}
        title="Discard draft and reload?"
        confirmLabel="Discard and reload"
        onCancel={() => setReload(false)}
        onConfirm={() => {
          setReload(false);
          setDirty(false);
          command.clear();
          metadata.refresh();
          source.refresh();
          refresh?.();
        }}
      >
        The latest record and field settings will replace this draft.
      </ConfirmDialog>
    </form>
  );
}
function TrackingHistory({
  company,
  kind,
  id,
  eventId,
}: {
  company: string;
  kind: TrackingKind;
  id: string;
  eventId?: string;
}) {
  const base = trackingBase(company, kind) + "/" + id + "/history",
    format = useFormatters(),
    list = useServiceList<Event>(
      base,
      "",
      trackingRequest,
      (row) => {
        if (!trackingId.test(row.id))
          throw {
            status: 502,
            message: "Tracking history could not be verified.",
          };
      },
      !eventId,
    ),
    event = useServiceRead<EventDetail>(
      eventId ? base + "/" + eventId : undefined,
      trackingRequest,
      (row) => {
        if (row.id !== eventId || !Array.isArray(row.changes))
          throw {
            status: 502,
            message: "The history event did not match this record.",
          };
      },
    );
  return (
    <div className="janso-flow">
      <AccessFailure
        failure={list.failure ?? event.failure}
        refresh={() => {
          list.refresh();
          event.refresh();
        }}
      />
      {list.loading || event.loading ? (
        <p role="status">Loading tracking history...</p>
      ) : event.data ? (
        <Card>
          <CardBody>
            <div className="janso-flow">
              <h2>{event.data.action}</h2>
              <p>{format.dateTime(event.data.created_at)}</p>
              <p>{event.data.reason ?? "Reason is protected."}</p>
              <ReviewList
                items={event.data.changes.map((change) => ({
                  label: change.field.replaceAll("_", " "),
                  value:
                    String(change.before ?? "Not set") +
                    " → " +
                    String(change.after ?? "Not set"),
                }))}
              />
              <a
                className="janso-link"
                href={"/inventory/" + kind + "/" + id + "/history"}
              >
                Return to history
              </a>
            </div>
          </CardBody>
        </Card>
      ) : (
        list.data && (
          <Card>
            <CardBody>
              <div className="janso-flow">
                {!list.data.items.length ? (
                  <Notice tone="info">No visible history events.</Notice>
                ) : (
                  list.data.items.map((row) => (
                    <FieldGroup
                      key={row.id}
                      title={row.action}
                      headerEnd={
                        <a
                          className="janso-link"
                          href={
                            "/inventory/" +
                            kind +
                            "/" +
                            id +
                            "/history/" +
                            row.id
                          }
                        >
                          View event
                        </a>
                      }
                    >
                      <p>{row.reason ?? "Reason is protected."}</p>
                      <p>{format.dateTime(row.created_at)}</p>
                    </FieldGroup>
                  ))
                )}
              </div>
            </CardBody>
            <Pager
              count={list.data.items.length}
              limit={list.limit}
              hasPrevious={list.hasPrevious}
              hasNext={list.data.page.has_more}
              onPrevious={list.previous}
              onNext={list.next}
              onLimitChange={list.setLimit}
              busy={list.loading}
              noun="event"
            />
          </Card>
        )
      )}
    </div>
  );
}
