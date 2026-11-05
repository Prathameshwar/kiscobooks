import type { components } from "@janso/api-client/catalog";
import { profileId } from "./product-profiles";
export type StackGroup = components["schemas"]["StackGroup"];
export type StackPermission = components["schemas"]["StackPermission"];
export type StackDraft = components["schemas"]["StackDraftDetail"];
export type StackPolicy = components["schemas"]["StackPolicyDetail"];
export type StackValues = {
  code: string;
  change_reason: string;
  maximum_applied: string;
  groups: StackGroup[];
  permissions: StackPermission[];
};
export const stackRoot = "/masters/promotion-stack-policies";
export const stackBase = (company: string) =>
  `/v1/companies/${company}/promotion-stack-policies`;
export const stackGroupFields = [
  "draft_id",
  "position",
  "stage",
  "selection",
  "changes_basket",
] as const;
export const stackPermissionFields = [
  "draft_id",
  "earlier_group_id",
  "later_group_id",
  "include_reward_units",
] as const;
export const stackHeaderFields = [
  "code",
  "change_reason",
  "maximum_applied",
] as const;
const stages = ["PRODUCT_SCHEME", "BASKET", "MANUAL"];
export function stackBody(values: StackValues) {
  const errors: Record<string, string> = {},
    positions = new Map<string, number>();
  if (!/^[A-Z0-9][A-Z0-9_.-]{0,29}$/.test(values.code))
    errors.code =
      "Use a policy code with up to 30 uppercase letters, digits, dots or hyphens.";
  if (
    !values.change_reason.trim() ||
    values.change_reason.length > 500 ||
    /[\x00-\x1f\x7f]/.test(values.change_reason)
  )
    errors.change_reason =
      "Enter a printable change reason with up to 500 characters.";
  if (!/^(?:[1-9]|10)$/.test(values.maximum_applied))
    errors.maximum_applied = "Enter a whole number from 1 to 10.";
  if (values.groups.length > 20 || values.permissions.length > 190)
    errors.groups =
      "This policy exceeds the supported group or permission count.";
  let previous = -1;
  values.groups.forEach((group, index) => {
    const stage = stages.indexOf(group.stage);
    if (
      !profileId.test(group.group_id) ||
      positions.has(group.group_id) ||
      stage < 0 ||
      stage < previous ||
      !["PRIORITY", "BEST_SINGLE", "CUSTOMER_CHOICE"].includes(
        group.selection,
      ) ||
      typeof group.changes_basket !== "boolean" ||
      (group.changes_basket && group.selection === "BEST_SINGLE")
    )
      errors.groups =
        "Keep unique groups in product, basket, manual order. Quantity-changing groups cannot use best single selection.";
    previous = stage;
    positions.set(group.group_id, index);
  });
  const seen = new Set<string>();
  values.permissions.forEach((pair) => {
    const first = positions.get(pair.earlier_group_id),
      second = positions.get(pair.later_group_id),
      key = pair.earlier_group_id + ":" + pair.later_group_id;
    if (
      first === undefined ||
      second === undefined ||
      first >= second ||
      seen.has(key) ||
      typeof pair.include_reward_units !== "boolean"
    )
      errors.permissions =
        "Each stacking permission must name one unique earlier-to-later group pair.";
    seen.add(key);
  });
  return {
    errors,
    body: {
      code: values.code,
      change_reason: values.change_reason.trim(),
      maximum_applied: Number(values.maximum_applied),
      groups: values.groups.map(
        ({ group_id, stage, selection, changes_basket }) => ({
          group_id,
          stage,
          selection,
          changes_basket,
        }),
      ),
      permissions: values.permissions.map(
        ({ earlier_group_id, later_group_id, include_reward_units }) => ({
          earlier_group_id,
          later_group_id,
          include_reward_units,
        }),
      ),
    },
  };
}
export function verifyStack(
  row: StackDraft | StackPolicy,
  company: string,
  id?: string,
) {
  if (
    row.company_id !== company ||
    !profileId.test(row.id) ||
    (id && row.id !== id) ||
    typeof row.complete !== "boolean" ||
    row.operational_ready !== false
  )
    throw {
      status: 502,
      message: "The stack definition could not be verified for this company.",
    };
  if (row.complete) {
    if (
      "policy_generation" in row
        ? !Number.isSafeInteger(row.row_version) ||
          Number(row.row_version) < 1 ||
          !["DRAFT", "PUBLISHED"].includes(String(row.status)) ||
          !Number.isSafeInteger(row.policy_generation)
        : !Number.isSafeInteger(row.version) ||
          Number(row.version) < 1 ||
          typeof row.source_sha256 !== "string" ||
          !/^[a-f0-9]{64}$/.test(row.source_sha256) ||
          typeof row.published_at !== "string" ||
          !Number.isFinite(Date.parse(row.published_at))
    )
      throw {
        status: 502,
        message:
          "The policy version could not be verified. Reload before continuing.",
      };
    if (
      !Array.isArray(row.groups) ||
      !Array.isArray(row.permissions) ||
      typeof row.code !== "string" ||
      !Number.isSafeInteger(row.maximum_applied)
    )
      throw {
        status: 502,
        message: "The complete stack definition is unavailable.",
      };
    const reviewed = stackBody({
      code: row.code,
      change_reason: "Review",
      maximum_applied: String(row.maximum_applied),
      groups: row.groups,
      permissions: row.permissions,
    });
    if (
      Object.keys(reviewed.errors).length ||
      ("group_count" in row &&
        (row.group_count !== row.groups.length ||
          row.permission_count !== row.permissions.length))
    )
      throw {
        status: 502,
        message:
          "Stack groups or permissions could not be verified. Existing values are retained.",
      };
  }
}
