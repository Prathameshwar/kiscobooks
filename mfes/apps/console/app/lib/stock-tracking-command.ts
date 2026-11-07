import { validMasterDate } from "./catalog-masters";
import { validateSerialIdentifiers, type SerialIdentifier } from './serial-identity';
import {
  trackingId,
  type TrackingKind,
  type TrackingSource,
} from "./stock-tracking-resources";
export type TrackingAction =
  | "prepare"
  | "correct"
  | "hold"
  | "release"
  | "retire"
  | "reactivate";
type Field = {
  key: string;
  required: boolean;
  visible: boolean;
  writable: boolean;
};
export function trackingBody(
  kind: TrackingKind,
  action: TrackingAction,
  fields: Field[],
  values: Record<string, unknown>,
  version?: number,
  source?: TrackingSource | null,
  previousDates?: {
    manufactured_on?: string | null;
    expires_on?: string | null;
  },
) {
  const body: Record<string, unknown> = {},
    errors: Record<string, string> = {};
  const keys =
    action === "prepare"
      ? kind === "batches"
        ? [
            "item_id",
            "code",
            "source_party_id",
            "manufactured_on",
            "expires_on",
            "mrp_amount",
            "mrp_currency",
            "mrp_unit_id",
            "reason",
          ]
        : ["item_id", "lot_id", "identifiers", "reason"]
      : action === "correct"
        ? ["manufactured_on", "expires_on", "reason", "expected_version"]
        : ["reason", "expected_version"];
  const candidate: Record<string, unknown> = {
    ...values,
    ...(action !== "prepare" ? { expected_version: version } : {}),
  };
  for (const key of keys) {
    const field = fields.find((field) => field.key === key),
      value = candidate[key];
    const required =
      key === "reason" ||
      key === "expected_version" ||
      (action === "prepare" &&
        ["item_id", kind === "batches" ? "code" : "identifiers"].includes(
          key,
        )) ||
      field?.required;
    if (!field?.visible || !field.writable) {
      if (required)
        errors[key] =
          "Field access is required for " + key.replaceAll("_", " ") + ".";
      continue;
    }
    if (
      required &&
      (value == null || value === "" || (Array.isArray(value) && !value.length))
    )
      errors[key] = field.key.replaceAll("_", " ") + " is required.";
    if (value != null && value !== "")
      body[key] = typeof value === "string" ? value.trim() : value;
    else if (action === "correct" && Object.hasOwn(values, key))
      body[key] = null;
  }
  if (
    typeof body.reason !== "string" ||
    body.reason.length < 3 ||
    body.reason.length > 500 ||
    /[\x00-\x1f]/.test(body.reason)
  )
    errors.reason = "Enter a printable reason of 3 to 500 characters.";
  for (const key of ["item_id", "source_party_id", "lot_id", "mrp_unit_id"])
    if (body[key] != null && !trackingId.test(String(body[key])))
      errors[key] = "Choose a valid reference.";
  if (
    action !== "prepare" &&
    (!Number.isSafeInteger(version) || !version || version < 1)
  )
    errors.expected_version =
      "Reload the record to obtain its current version.";
  for (const key of ["manufactured_on", "expires_on"])
    if (body[key] && !validMasterDate(body[key]))
      errors[key] = "Enter a valid business date.";
  const dates = { ...previousDates, ...body };
  if (
    dates.manufactured_on &&
    dates.expires_on &&
    String(dates.expires_on) < String(dates.manufactured_on)
  )
    errors.expires_on = "Expiry must not precede manufacture.";
  if (typeof body.code === "string" && body.code.length > 100)
    errors.code = "Batch code must be at most 100 characters.";
  const mrp = ["mrp_amount", "mrp_currency", "mrp_unit_id"].filter(
    (key) => body[key] != null,
  );
  if (mrp.length && mrp.length !== 3)
    errors.mrp_amount = "MRP requires an amount, currency and unit together.";
  if (
    body.mrp_amount &&
    (!/^(?:0|[1-9]\d{0,14})(?:\.\d{1,4})?$/.test(String(body.mrp_amount)) ||
      !/[1-9]/.test(String(body.mrp_amount)))
  )
    errors.mrp_amount =
      "Enter a positive exact amount with at most four decimal places.";
  if (body.mrp_currency && !/^[A-Z]{3}$/.test(String(body.mrp_currency)))
    errors.mrp_currency = "Choose a three-letter currency.";
  if (action === "prepare" && source) {
    if (kind === "batches" ? !source.lot_tracking : !source.serial_tracking)
      errors.item_id = "This product does not use " + kind + ".";
    if (kind === "batches") {
      if (source.manufacture_date_required && !body.manufactured_on)
        errors.manufactured_on = "The product requires a manufacture date.";
      if (source.expiry_required && !body.expires_on)
        errors.expires_on = "The product requires an expiry date.";
    } else {
      if (source.lot_tracking && !body.lot_id)
        errors.lot_id = "Choose the batch required by this product.";
      const identifiers = (body.identifiers ?? []) as {
        identifier_type: string;
        slot: number;
        value: string;
      }[];
      const validated = validateSerialIdentifiers(identifiers as SerialIdentifier[], source.requirements ?? []);
      Object.assign(errors, validated.errors);
      if (Object.keys(validated.errors).length) errors.identifiers = Object.values(validated.errors)[0]!;
    }
  }
  return { body, errors };
}
