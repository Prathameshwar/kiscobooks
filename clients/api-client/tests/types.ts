import type { components } from "../src/catalog.js";

type UnitInput = components["schemas"]["UnitCreate"];
const input: UnitInput = { code: "KG", name: "Kilogram", symbol: "kg", dimension: "MASS",
  decimal_places: 3, quantity_increment: "0.001" };
// @ts-expect-error Decimal wire inputs must be strings.
const badDecimal: UnitInput["quantity_increment"] = 0.001;
// @ts-expect-error Only declared dimensions are accepted.
const badDimension: UnitInput["dimension"] = "TEMPERATURE";
// @ts-expect-error Required native input fields cannot be omitted.
const missing: UnitInput = { code: "KG" };
const protectedOutput: components["schemas"]["UnitDetail"] = {
  id: "id", company_id: "company", created_at: "timestamp", updated_at: "timestamp",
};
void [input, badDecimal, badDimension, missing, protectedOutput];

type Ratio = components["schemas"]["UnitConversionInput"]["numerator"];
const largeRatio: Ratio = "9007199254740993";
// @ts-expect-error BIGINT ratio wire values must be strings.
const impreciseRatio: Ratio = 9007199254740993;
void [largeRatio, impreciseRatio];

type ProductRatio = components["schemas"]["UnitBindingInput"]["numerator"];
const productRatio: ProductRatio = "9007199254740993";
// @ts-expect-error Product ratios use the same exact string contract.
const impreciseProductRatio: ProductRatio = 9007199254740993;
type RevisionRatio = components["schemas"]["ItemUnitRevisionDetail"]["numerator"];
const revisionRatio: RevisionRatio = "9007199254740993";
// @ts-expect-error Revision responses must preserve all BIGINT digits.
const impreciseRevisionRatio: RevisionRatio = 9007199254740993;
void [productRatio, impreciseProductRatio, revisionRatio, impreciseRevisionRatio];
