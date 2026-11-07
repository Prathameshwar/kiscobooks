import { attributeValue, type NativeAttributeValue } from "@janso/ui";
type Guard = {
  item_id?: string;
  item_version?: number;
  family_version?: number;
  revision?: string;
  authoring_version?: number;
};
type Declaration = {
  definition_id: string;
  label: string;
  is_axis: boolean;
  is_required: boolean;
  position?: number;
  allowed_options?: { id: string }[];
};
/** Exact native payloads; false and zero are values, not empty fields. */
export function attributeCommand(
  guard: Guard,
  values: NativeAttributeValue[],
  fields: Declaration[],
  action: "values" | "configure" | "variant",
) {
  const attributes = values.map(attributeValue);
  if (action === "variant")
    for (const field of fields)
      if (
        (field.is_axis || field.is_required) &&
        !attributes.some((value) => value.definition_id === field.definition_id)
      )
        throw new Error(field.label + " is required for this variant.");
  if (action === "values")
    return { expected_version: guard.item_version, attributes };
  const declarations = fields.map((field, position) => ({
    definition_id: field.definition_id,
    is_axis: field.is_axis,
    is_required: field.is_required,
    position,
    options: (field.allowed_options ?? []).map((option) => option.id),
  }));
  if (guard.revision)
    return {
      revision: guard.revision,
      authoring_version: guard.authoring_version,
      attributes: declarations,
      values: attributes,
    };
  return action === "configure"
    ? {
        expected_version: guard.family_version,
        expected_default_item_version: guard.item_version,
        attributes: declarations,
        default_item_attributes: attributes,
      }
    : { expected_version: guard.family_version, attributes };
}
