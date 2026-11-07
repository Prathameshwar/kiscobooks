"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  AttributeValueInput,
  attributeValue,
  Button,
  ConfirmDialog,
  Card,
  CardBody,
  Checkbox,
  FieldGroup,
  FormActions,
  Notice,
  PageHeader,
  PageNavigation,
  SearchSelect,
  TextField,
  type NativeAttributeField,
  type NativeAttributeValue,
  type SearchSelectLoader,
} from "@janso/ui";
import type { components } from "@janso/api-client/catalog";
import { masterRequest } from "../lib/catalog-master-api";
import { useServiceRead, useServiceCommand } from "../lib/service-resource";
import {
  catalogId,
  useCatalogFields,
  classificationBody,
} from "../lib/product-classification";
import { masterConfig } from "../lib/catalog-masters";
import { ProductCatalogCustomFields } from "./ProductCatalogCustomFields";
import { ProductCatalogField } from "./ProductCatalogCommon";
import type { ClassificationAccess } from "../lib/product-classification-resources";
import { attributeCommand } from "../lib/product-attribute-command";
import { useProductMode } from "./ProductModeProvider";
import { AccessFailure, useAccessDraft } from "./AccessCommon";
import { AdvancedProductChoice } from "./AdvancedProductChoice";
type Form = components["schemas"]["ProductAttributeForm"] & {
  revision?: string;
  authoring_version?: number;
};
type SimpleForm = components["schemas"]["SimpleProductAttributeForm"];
type AttributeField = Form["fields"][number];
export function ProductAttributeAuthoring({
  company,
  itemId,
  familyId,
  canManage,
  canCreate,
}: {
  company: string;
  itemId?: string;
  familyId?: string;
  canManage: boolean;
  canCreate: boolean;
}) {
  const mode = useProductMode(),
    advanced = mode?.data?.product_family_sku_enabled;
  const [selected, setSelected] = useState(itemId ?? ""),
    [resolved, setResolved] = useState(""),
    [selectionLocked, setSelectionLocked] = useState(false);
  const loadProducts = useCallback<SearchSelectLoader>(
    async ({ q, cursor, signal }) => {
      if (typeof advanced !== "boolean")
        throw new Error("Product mode is unavailable.");
      const params = new URLSearchParams({ limit: "50" });
      if (q.trim().length >= 2) params.set("q", q.trim());
      if (cursor) params.set("cursor", cursor);
      const page = await masterRequest<{
        items: {
          id: string;
          name?: string | null;
          sku?: string | null;
          code?: string | null;
        }[];
        page: { has_more: boolean; next_cursor?: string | null };
      }>({
        path: `/v1/companies/${company}/${advanced ? "items" : "products"}?${params}`,
        signal,
      });
      if (
        !Array.isArray(page.items) ||
        page.items.some((row) => !catalogId.test(row.id))
      )
        throw new Error("Product options could not be verified.");
      return {
        items: page.items.map((row) => ({
          id: row.id,
          label: row.name ?? row.sku ?? row.code ?? "Protected product",
        })),
        nextCursor: page.page.has_more ? (page.page.next_cursor ?? null) : null,
      };
    },
    [company, advanced],
  );
  const first = useServiceRead<{ items: { id: string; family_id?: string }[] }>(
    familyId && advanced === true
      ? `/v1/companies/${company}/items?family_id=${familyId}&limit=1`
      : undefined,
    masterRequest,
    (value) => {
      if (
        !Array.isArray(value.items) ||
        value.items.some(
          (row) => !catalogId.test(row.id) || row.family_id !== familyId,
        )
      )
        throw {
          status: 502,
          message: "Profile products could not be verified.",
        };
    },
  );
  useEffect(() => {
    if (first.data?.items[0]) setResolved(first.data.items[0].id);
  }, [first.data]);
  const current = familyId ? resolved : selected;
  const source = advanced === true ? "items" : "products";
  const read = useServiceRead<Form | SimpleForm>(
    typeof advanced === "boolean" && current
      ? `/v1/companies/${company}/${source}/${current}/attribute-form`
      : undefined,
    masterRequest,
    (value) => {
      if (
        advanced
          ? !("item_id" in value) ||
            value.item_id !== current ||
            (familyId && value.family_id !== familyId)
          : !("id" in value) || value.id !== current || !value.revision
      )
        throw {
          status: 502,
          message: "The attribute form did not match this product.",
        };
    },
  );
  useEffect(() => {
    if (
      familyId &&
      read.data &&
      "default_item_id" in read.data &&
      read.data.default_item_id !== resolved
    )
      setResolved(read.data.default_item_id);
  }, [familyId, read.data, resolved]);
  return (
    <div className="janso-page janso-product-management">
      <PageNavigation
        back={{
          href: familyId
            ? "/masters/product-families/" + familyId
            : itemId
              ? "/masters/items/" + itemId
              : "/inventory/attributes",
          label: "product attributes",
        }}
      />
      <PageHeader
        title="Attributes and variants"
        lede="Maintain typed specifications and the choices that distinguish product variants."
      />
      <AccessFailure failure={mode?.failure ?? null} refresh={mode?.refresh} />
      {familyId && advanced === false ? (
        <Notice tone="warning">
          Product Profiles require Advanced product mode.
        </Notice>
      ) : (
        <>
          {!familyId && (
            <Card>
              <CardBody>
                <SearchSelect
                  label="Product / SKU"
                  value={selected || null}
                  selected={
                    selected
                      ? {
                          id: selected,
                          label: read.data
                            ? "item_name" in read.data
                              ? read.data.item_name
                              : read.data.name
                            : "Selected product",
                        }
                      : undefined
                  }
                  loadOptions={loadProducts}
                  scopeKey={company + ":" + advanced}
                  disabled={typeof advanced !== "boolean" || selectionLocked}
                  onChange={(id) => setSelected(id ?? "")}
                />
              </CardBody>
            </Card>
          )}
          <AccessFailure
            failure={first.failure ?? read.failure}
            refresh={() => {
              first.refresh();
              read.refresh();
            }}
          />
          {first.loading || read.loading || mode?.loading ? (
            <p role="status">Loading attributes...</p>
          ) : (
            read.data &&
            ("item_id" in read.data
              ? read.data.item_id === current
              : read.data.id === current) && (
              <AttributeEditor
                key={current + ":" + String(advanced)}
                company={company}
                product={current}
                data={read.data}
                advanced={advanced === true}
                canManage={canManage}
                canCreate={canCreate}
                refresh={read.refresh}
                onDraft={setSelectionLocked}
              />
            )
          )}
          {!current && !familyId && (
            <Notice tone="info">
              Choose a product to review its attributes. Definitions and options
              can be maintained below.
            </Notice>
          )}
          {familyId && first.data && !first.data.items.length && (
            <Notice tone="warning">
              This Profile has no readable SKU. Open its details to review setup
              and access.
            </Notice>
          )}
        </>
      )}
      <nav className="janso-form-actions" aria-label="Attribute masters">
        <a className="janso-link" href="/masters/attribute-definitions">
          Definitions
        </a>
        <a className="janso-link" href="/masters/attribute-options">
          Options
        </a>
        <a className="janso-link" href="/masters/attribute-sets">
          Sets / templates
        </a>
      </nav>
    </div>
  );
}
function AttributeEditor({
  company,
  product,
  data,
  advanced,
  canManage,
  canCreate,
  refresh,
  onDraft,
}: {
  company: string;
  product: string;
  data: Form | SimpleForm;
  advanced: boolean;
  canManage: boolean;
  canCreate: boolean;
  refresh: () => void;
  onDraft: (value: boolean) => void;
}) {
  const native = "item_id" in data ? data : null;
  const [fields, setFields] = useState(data.fields),
    [values, setValues] = useState<NativeAttributeValue[]>(
      data.fields.flatMap((field) => (field.value ? [field.value] : [])),
    );
  const [action, setAction] = useState<"values" | "configure" | "variant">(
      advanced ? "values" : "configure",
    ),
    [dirty, setDirty] = useState(false),
    [error, setError] = useState(""),
    [saved, setSaved] = useState(false),
    [reload, setReload] = useState(false),
    [sku, setSku] = useState(""),
    [name, setName] = useState(""),
    [option, setOption] = useState<Record<string, string>>({}),
    [variantValues, setVariantValues] = useState<Record<string, unknown>>({
      sellable: true,
      purchasable: true,
      min_sale_quantity: null,
      custom_fields: {},
    });
  const variantFields = useCatalogFields(
    company,
    "catalog.item",
    "create",
    undefined,
    action === "variant",
  );
  const command = useServiceCommand(masterRequest, "product attributes"),
    guard = useAccessDraft(dirty || command.uncertain, command.pending),
    form = useRef<HTMLFormElement>(null),
    mode = useProductMode();
  const modeChanged =
    mode?.data?.product_family_sku_enabled !== advanced ||
    (!advanced &&
      mode.data?.row_version !==
        ("authoring_version" in data ? data.authoring_version : undefined));
  const locked =
    command.pending ||
    command.uncertain ||
    saved ||
    modeChanged ||
    !canManage ||
    command.blocked ||
    (action === "variant" &&
      (variantFields.loading || !!variantFields.failure)) ||
    (action === "configure" && !data.can_configure);
  useEffect(() => {
    onDraft(dirty || command.pending || command.uncertain);
    return () => onDraft(false);
  }, [dirty, command.pending, command.uncertain, onDraft]);
  const loadDefinitions = useCallback<SearchSelectLoader>(
    async ({ q, cursor, signal }) => {
      const params = new URLSearchParams({ limit: "50", is_active: "true" });
      if (q.trim().length >= 2) params.set("q", q.trim());
      if (cursor) params.set("cursor", cursor);
      const page = await masterRequest<{
        items: { id: string; name?: string; code?: string }[];
        page: { has_more: boolean; next_cursor?: string | null };
      }>({
        path: `/v1/companies/${company}/attribute-definitions?${params}`,
        signal,
      });
      return {
        items: page.items
          .filter(
            (row) => !fields.some((field) => field.definition_id === row.id),
          )
          .map((row) => ({
            id: row.id,
            label: row.name ?? row.code ?? "Attribute",
          })),
        nextCursor: page.page.has_more ? (page.page.next_cursor ?? null) : null,
      };
    },
    [company, fields],
  );
  const loader =
    (
      field: AttributeField,
      resource: "attribute_options" | "units",
    ): SearchSelectLoader =>
    async ({ q, cursor, signal }) => {
      const params = new URLSearchParams({ limit: "50" });
      if (q.trim().length >= 2) params.set("q", q.trim());
      if (cursor) params.set("cursor", cursor);
      if (resource === "attribute_options")
        params.set("parent_id", field.definition_id);
      const page = await masterRequest<{
        items: { id: string; name?: string; label?: string }[];
        page: { has_more: boolean; next_cursor?: string | null };
      }>({
        path: `/v1/companies/${company}/option-sources/catalog.${resource}?${params}`,
        signal,
      });
      return {
        items: page.items.map((row) => ({
          id: row.id,
          label: row.label ?? row.name ?? "Choice",
        })),
        nextCursor: page.page.has_more ? (page.page.next_cursor ?? null) : null,
      };
    };
  const change = () => {
    setDirty(true);
    setError("");
    command.clear();
  };
  async function addDefinition(id: string | null) {
    if (!id || locked || fields.length >= 128) return;
    try {
      const row = await masterRequest<
        components["schemas"]["AttributeDefinitionDetail"]
      >({ path: `/v1/companies/${company}/attribute-definitions/${id}` });
      if (
        row.company_id !== company ||
        row.id !== id ||
        !row.name ||
        !row.value_type ||
        row.is_active !== true
      )
        throw new Error("The selected attribute is unavailable.");
      setFields((current) =>
        current.some((field) => field.definition_id === id)
          ? current
          : [
              ...current,
              {
                definition_id: id,
                label: row.name!,
                value_type: row.value_type!,
                measurement_dimension: row.measurement_dimension ?? null,
                is_variant_capable: row.is_variant_capable === true,
                is_active: true,
                is_axis: false,
                is_required: false,
                position: current.length,
                allowed_options: [],
                value: null,
                option_label: null,
                unit_label: null,
                writable: native ? native.item_status === "DRAFT" : "status" in data && data.status === "DRAFT",
                variant_writable: native?.can_create_variant === true,
              },
            ],
      );
      change();
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Could not load this attribute. Try again.",
      );
    }
  }
  async function save() {
    if (command.pending || !canManage || (locked && !command.uncertain)) return;
    const verify = (
      receipt:
        | components["schemas"]["AuthoringResult"]
        | components["schemas"]["SimpleProductDetail"],
    ) => {
      if (
        advanced
          ? !("family_id" in receipt) ||
            receipt.family_id !== native?.family_id ||
            !Number.isSafeInteger(receipt.family_version) ||
            !receipt.item_id ||
            (action !== "variant" && receipt.item_id !== product)
          : !("id" in receipt) ||
            receipt.id !== product ||
            receipt.company_id !== company ||
            !receipt.revision
      )
        throw {
          status: 502,
          message: "The saved attribute result could not be verified.",
        };
    };
    if (command.uncertain) {
      if (await command.retry(verify)) {
        setSaved(true);
        setDirty(false);
      }
      return;
    }
    try {
      values.forEach(attributeValue);
      const body = attributeCommand(
        native ?? ("revision" in data ? data : {}),
        values,
        fields,
        action,
      );
      let path =
        `/v1/companies/${company}/` +
        (advanced
          ? action === "values"
            ? `items/${product}/attributes`
            : `product-families/${native!.family_id}/${action === "variant" ? "variants" : "attributes"}`
          : `products/${product}/attributes`);
      if (action === "variant") {
        if (!canCreate || !native?.can_create_variant)
          throw new Error("Variant creation is unavailable for this Profile.");
        if (
          !/^[A-Z0-9][A-Z0-9_.-]{0,29}$/.test(sku) ||
          !name.trim() ||
          name.trim().length > 100
        )
          throw new Error(
            "Enter a SKU of up to 30 uppercase letters/numbers and a name of up to 100 characters.",
          );
        const item = classificationBody(
          masterConfig("items")!,
          variantFields.data?.fields ?? [],
          {
            ...variantValues,
            sku,
            name: name.trim(),
            base_unit_id: data.base_unit_id,
          },
        );
        if (Object.keys(item.errors).length)
          throw new Error(Object.values(item.errors).join(" "));
        Object.assign(body, { item: item.body });
      }
      if (
        action === "configure" &&
        native &&
        native.default_item_id !== product
      )
        throw new Error(
          "Open the default SKU before configuring Profile attributes.",
        );
      if (
        await command.execute(
          { path, method: action === "variant" ? "POST" : "PUT", body },
          verify,
        )
      ) {
        setSaved(true);
        setDirty(false);
      }
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Review the attribute entries.",
      );
      requestAnimationFrame(() =>
        form.current
          ?.querySelector<HTMLElement>("input:not([disabled])")
          ?.focus(),
      );
    }
  }
  return (
    <form
      ref={form}
      noValidate
      aria-label="Product attribute authoring"
      onSubmit={(event) => {
        event.preventDefault();
        void save();
      }}
    >
      <Card>
        <CardBody>
          <div className="janso-flow">
            <h2>
              {native?.item_name ?? ("name" in data ? data.name : "Product")}
            </h2>
            {modeChanged && (
              <Notice tone="warning">
                Product mode changed. Reload and review before saving. An
                interrupted save can still be recovered.
              </Notice>
            )}
            {advanced && (
              <div className="janso-form-actions">
                <Button
                  type="button"
                  variant="ghost"
                  disabled={locked || dirty}
                  onClick={() => {
                    setAction("values");
                    setValues(
                      data.fields.flatMap((field) =>
                        field.value ? [field.value] : [],
                      ),
                    );
                  }}
                >
                  SKU specifications
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  disabled={
                    locked ||
                    dirty ||
                    !data.can_configure ||
                    native?.default_item_id !== product
                  }
                  onClick={() => {
                    setAction("configure");
                    setValues(
                      data.fields.flatMap((field) =>
                        field.value ? [field.value] : [],
                      ),
                    );
                  }}
                >
                  Configure Profile attributes
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  disabled={
                    locked || dirty || !canCreate || !native?.can_create_variant
                  }
                  onClick={() => {
                    setAction("variant");
                    setValues([]);
                  }}
                >
                  Add variant
                </Button>
                {native?.default_item_id !== product && (
                  <a
                    className="janso-link"
                    href={
                      "/products/attributes?item_id=" + native?.default_item_id
                    }
                    onClick={guard.leave}
                  >
                    Open default SKU
                  </a>
                )}
              </div>
            )}
            <Notice tone="info">
              {action === "variant"
                ? "The new SKU is saved as a draft. Choose its axis options and required specifications before activation."
                : action === "configure"
                  ? "Changes apply to the Product Profile and its default SKU. Required specifications are checked before activation."
                  : "Specifications are editable on draft SKUs. Active product identity and history remain protected."}
            </Notice>
            {saved ? (
              <Notice tone="success">
                {action === "variant" ? "Variant saved." : "Attributes saved."}{" "}
                <a
                  className="janso-link"
                  href={
                    native
                      ? "/masters/product-families/" + native.family_id
                      : "/masters/items/" + product
                  }
                >
                  View product
                </a>
                <Button type="button" variant="ghost" onClick={refresh}>
                  Reload attributes
                </Button>
              </Notice>
            ) : (
              <>
                {action === "variant" && (
                  <FieldGroup title="Variant identity">
                    <div className="janso-form-grid">
                      <TextField
                        label="SKU"
                        required
                        maxLength={30}
                        value={sku}
                        disabled={locked}
                        onChange={(event) => {
                          setSku(event.target.value);
                          change();
                        }}
                      />
                      <TextField
                        label="Variant name"
                        required
                        maxLength={100}
                        value={name}
                        disabled={locked}
                        onChange={(event) => {
                          setName(event.target.value);
                          change();
                        }}
                      />
                    </div>
                    <p>Base unit: {data.base_unit_label}</p>
                  </FieldGroup>
                )}
                {!fields.length && (
                  <p>
                    No attributes declared. Configure the Profile to add typed
                    specifications.
                  </p>
                )}
                {fields.map((field) => (
                  <section className="janso-flow" key={field.definition_id}>
                    {action === "configure" && (
                      <FieldGroup title={field.label + " declaration"}>
                        <div className="janso-form-grid">
                          <Checkbox
                            checked={field.is_required}
                            disabled={locked}
                            onChange={(event) => {
                              const checked = event.target.checked;
                              setFields((current) =>
                                current.map((row) =>
                                  row.definition_id === field.definition_id
                                    ? { ...row, is_required: checked }
                                    : row,
                                ),
                              );
                              change();
                            }}
                          >
                            Required before activation
                          </Checkbox>
                          <Checkbox
                            checked={field.is_axis}
                            disabled={
                              locked || !advanced || !field.is_variant_capable
                            }
                            onChange={(event) => {
                              const checked = event.target.checked;
                              setFields((current) =>
                                current.map((row) =>
                                  row.definition_id === field.definition_id
                                    ? { ...row, is_axis: checked }
                                    : row,
                                ),
                              );
                              change();
                            }}
                          >
                            Variant axis
                          </Checkbox>
                        </div>
                        {(
                          <>
                            <AdvancedProductChoice
                              company={company}
                              resource="attribute_options"
                              parent={field.definition_id}
                              label={field.label + " allowed option"}
                              value={option[field.definition_id] ?? ""}
                              disabled={locked}
                              onChange={(id, label) => {
                                setOption((current) => ({
                                  ...current,
                                  [field.definition_id]: "",
                                }));
                                setFields((current) =>
                                  current.map((row) =>
                                    row.definition_id === field.definition_id &&
                                    id &&
                                    !row.allowed_options.some(
                                      (entry) => entry.id === id,
                                    )
                                      ? {
                                          ...row,
                                          allowed_options: [
                                            ...row.allowed_options,
                                            { id, label, is_active: true },
                                          ],
                                        }
                                      : row,
                                  ),
                                );
                                change();
                              }}
                            />
                            {field.allowed_options.map((entry) => (
                              <div
                                key={entry.id}
                                className="janso-form-actions"
                              >
                                <span>{entry.label}</span>
                                <Button
                                  type="button"
                                  variant="ghost"
                                  disabled={locked}
                                  onClick={() => {
                                    setFields((current) =>
                                      current.map((row) =>
                                        row.definition_id ===
                                        field.definition_id
                                          ? {
                                              ...row,
                                              allowed_options:
                                                row.allowed_options.filter(
                                                  (value) =>
                                                    value.id !== entry.id,
                                                ),
                                            }
                                          : row,
                                      ),
                                    );
                                    change();
                                  }}
                                >
                                  Remove {entry.label}
                                </Button>
                              </div>
                            ))}
                          </>
                        )}
                        <Button
                          type="button"
                          variant="ghost"
                          disabled={locked}
                          onClick={() => {
                            setFields((current) =>
                              current.filter(
                                (row) =>
                                  row.definition_id !== field.definition_id,
                              ),
                            );
                            setValues((current) =>
                              current.filter(
                                (row) =>
                                  row.definition_id !== field.definition_id,
                              ),
                            );
                            change();
                          }}
                        >
                          Remove attribute
                        </Button>
                      </FieldGroup>
                    )}
                    <AttributeValueInput
                      key={action + ":" + field.definition_id}
                      field={
                        {
                          ...field,
                          writable:
                            action === "configure"
                              ? data.can_configure && field.writable
                              : action === "variant"
                                ? field.variant_writable
                                : field.writable,
                        } as NativeAttributeField
                      }
                      value={
                        values.find(
                          (value) =>
                            value.definition_id === field.definition_id,
                        ) ?? null
                      }
                      disabled={locked}
                      loadOptions={loader(field, "attribute_options")}
                      loadUnits={loader(field, "units")}
                      onChange={(value) => {
                        setValues((current) => [
                          ...current.filter(
                            (row) => row.definition_id !== field.definition_id,
                          ),
                          ...(value ? [value] : []),
                        ]);
                        change();
                      }}
                    />
                  </section>
                ))}
                {action === "configure" && (
                  <SearchSelect
                    label="Add attribute definition"
                    value={null}
                    loadOptions={loadDefinitions}
                    scopeKey={company + ":" + fields.length}
                    disabled={locked || fields.length >= 128}
                    onChange={(id) => {
                      void addDefinition(id);
                    }}
                  />
                )}
              </>
            )}
            {action === "variant" && (
              <>
                <AccessFailure
                  failure={variantFields.failure}
                  refresh={variantFields.refresh}
                />
                <FieldGroup title="Variant trading and product fields">
                  <div className="janso-form-grid">
                    {(variantFields.data?.fields ?? [])
                      .filter(
                        (field) =>
                          [
                            "sellable",
                            "purchasable",
                            "min_sale_quantity",
                          ].includes(field.key) && field.visible,
                      )
                      .map((field) => (
                        <ProductCatalogField
                          key={field.key}
                          company={company}
                          field={field}
                          values={variantValues}
                          access={{} as ClassificationAccess}
                          disabled={locked}
                          onChange={(value) => {
                            setVariantValues((current) => ({
                              ...current,
                              [field.key]: value,
                            }));
                            change();
                          }}
                        />
                      ))}
                  </div>
                  <ProductCatalogCustomFields
                    company={company}
                    fields={variantFields.data?.fields ?? []}
                    values={variantValues}
                    creating
                    disabled={locked}
                    onChange={(custom_fields) => {
                      setVariantValues((current) => ({
                        ...current,
                        custom_fields,
                      }));
                      change();
                    }}
                  />
                </FieldGroup>
              </>
            )}
            {error && <Notice tone="danger">{error}</Notice>}
            <AccessFailure
              failure={command.failure}
              uncertain={command.uncertain}
            />
            {command.blocked && command.failure && !command.uncertain && (
              <Button
                type="button"
                variant="ghost"
                onClick={() => setReload(true)}
              >
                Reload and review
              </Button>
            )}
          </div>
        </CardBody>
        {!saved && (
          <FormActions
            cancel={{ href: "/masters/items/" + product, onClick: guard.leave }}
          >
            <Button
              type="submit"
              loading={command.pending}
              disabled={
                command.pending || (!command.uncertain && (locked || !dirty))
              }
            >
              {command.uncertain
                ? "Retry same save"
                : action === "variant"
                  ? "Save variant"
                  : "Save attributes"}
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
          refresh();
        }}
      >
        The latest product will replace this attribute draft.
      </ConfirmDialog>
    </form>
  );
}
