import { expect, it } from "vitest";
import { attributeCommand } from "../app/lib/product-attribute-command";
it("retains false and exact decimal attributes and native versions", () => {
  const value = {
    definition_id: "d",
    value_type: "BOOLEAN",
    value_boolean: false,
  };
  const result = attributeCommand(
    { item_id: "i", item_version: 4, family_version: 7 },
    [value],
    [],
    "values",
  );
  expect(result).toEqual({ expected_version: 4, attributes: [value] });
});
it("requires selected values for required variant axes", () => {
  expect(() =>
    attributeCommand(
      { item_id: "i", item_version: 4, family_version: 7 },
      [],
      [
        {
          definition_id: "d",
          label: "Color",
          is_axis: true,
          is_required: true,
        },
      ],
      "variant",
    ),
  ).toThrow("Color");
});
