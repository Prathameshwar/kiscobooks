"use client";
import { useEffect, useRef, useState } from "react";
import {
  Button,
  Card,
  CardBody,
  FormActions,
  Notice,
  PageHeader,
  ReviewList,
  SectionHeader,
  ConfirmDialog,
  FieldGroup,
} from "@janso/ui";
import type { components } from "@janso/api-client/catalog";
import { masterRequest } from "../lib/catalog-master-api";
import {
  masterBody,
  type MasterField,
  type MasterConfig,
  type MasterRow,
} from "../lib/catalog-masters";
import {
  catalogId,
  catalogLink,
  catalogBack,
  nativeCatalogBody,
} from "../lib/product-classification";
import type { ClassificationAccess } from "../lib/product-classification-resources";
import { useServiceRead, useServiceCommand } from "../lib/service-resource";
import { verifySimpleFields, type SimpleFields } from "../lib/simple-products";
import {
  ProductCatalogField,
  ProductCatalogFailure,
  ProductCatalogNavigation,
} from "./ProductCatalogCommon";
import { ProductCatalogCustomFields } from "./ProductCatalogCustomFields";
import { useAccessDraft } from "./AccessCommon";
import { useProductMode } from "./ProductModeProvider";
import { ProductInventoryActions } from "./ProductInventoryActions";
import { ProductDetailHeader, ProductDetailView } from "./ProductDetailView";

type Product = components["schemas"]["SimpleProductDetail"];
const editKeys = [
  "code",
  "name",
  "sellable",
  "purchasable",
  "min_sale_quantity",
  "brand_id",
  "series_id",
  "model_code",
  "description",
];
export function verifySimpleRecord(
  value: Product,
  company: string,
  id: string,
) {
  if (
    value.company_id !== company ||
    value.id !== id ||
    !catalogId.test(value.id) ||
    !value.revision ||
    !Number.isSafeInteger(value.authoring_version)
  )
    throw {
      status: 502,
      message: "The product response did not match this company and record.",
    };
}
function customFields(fields: MasterField[], group: string) {
  return fields
    .filter(
      (field) =>
        field.source === "custom" &&
        (group === "shared_custom_fields"
          ? field.key.startsWith(group + ".")
          : !field.key.startsWith("shared_custom_fields.")),
    )
    .map((field) => ({
      ...field,
      key: field.key.replace(/^shared_custom_fields\./, ""),
    }));
}
export function simpleRecordPatch(
  config: MasterConfig,
  fields: MasterField[],
  values: Record<string, unknown>,
  previous: Product,
) {
  const changed = editKeys.filter(
    (key) =>
      JSON.stringify(values[key]) !==
      JSON.stringify(previous[key as keyof Product]),
  );
  const result = nativeCatalogBody(fields, changed, values);
  for (const group of ["custom_fields", "shared_custom_fields"] as const) {
    const custom = masterBody(
      { ...config, inputs: {} },
      customFields(fields, group),
      { ...values, custom_fields: values[group] },
      {
        ...previous,
        row_version: 1,
        custom_fields: previous[group],
      } as MasterRow,
    );
    if (custom.body.custom_fields)
      result.body[group] = custom.body.custom_fields;
    Object.assign(result.errors, custom.errors);
  }
  if (
    values.series_id &&
    !values.brand_id &&
    ("brand_id" in result.body || "series_id" in result.body)
  )
    result.errors.series_id = "Choose a brand before its series.";
  return {
    ...result,
    body: {
      ...result.body,
      revision: previous.revision,
      authoring_version: previous.authoring_version,
    },
  };
}

export function SimpleProductRecord({
  company,
  config,
  id,
  returnTo,
  access,
  canManage,
  editing = false,
  completed = false,
}: {
  company: string;
  config: MasterConfig;
  id: string;
  returnTo?: string;
  access: ClassificationAccess;
  canManage: boolean;
  editing?: boolean;
  completed?: boolean;
}) {
  const back = catalogBack(returnTo, "/masters/items"),
    detail = catalogLink("/masters/items/" + id, back);
  const metadata = useServiceRead<SimpleFields>(
    `/v1/companies/${company}/products/field-set?operation=update&object_id=${id}`,
    masterRequest,
    (value) => verifySimpleFields(value, company),
  );
  const record = useServiceRead<Product>(
    `/v1/companies/${company}/products/${id}`,
    masterRequest,
    (value) => verifySimpleRecord(value, company, id),
  );
  const command = useServiceCommand(masterRequest, "product edit"),
    mode = useProductMode(),
    form = useRef<HTMLFormElement>(null);
  const [values, setValues] = useState<Record<string, unknown>>({}),
    [dirty, setDirty] = useState(false),
    [saved, setSaved] = useState<Product | null>(null),
    [errors, setErrors] = useState<Record<string, string>>({}),
    [reload, setReload] = useState(false);
  const [initialized, setInitialized] = useState(false);
  const guard = useAccessDraft(dirty || command.uncertain, command.pending);
  useEffect(() => {
    if (record.data && !dirty && !command.uncertain) {
      setValues({ ...record.data });
      setInitialized(true);
    }
  }, [record.data]);
  const fields = metadata.data?.fields ?? [],
    row = saved ?? record.data,
    failure = metadata.failure ?? record.failure;
  const loading =
    metadata.loading || record.loading || (!initialized && !failure);
  const modeChanged =
    !!row &&
    (!mode?.data ||
      mode.data.product_family_sku_enabled ||
      mode.data.row_version !== row.authoring_version ||
      metadata.data?.authoring_version !== row.authoring_version);
  const blocked = command.blocked || modeChanged;
  const tradingKeys = ["sellable", "purchasable", "min_sale_quantity"];
  const nativeFields = fields.filter(
    (field) =>
      field.source === "native" &&
      field.control &&
      field.visible &&
      row &&
      field.key in row,
  );
  const showField = (field: MasterField) => (
    <ProductCatalogField
      key={field.key}
      company={company}
      field={field}
      values={editing ? values : row!}
      access={access}
      readView={!editing}
      disabled={
        blocked ||
        !canManage ||
        !!saved ||
        !editing ||
        !editKeys.includes(field.key) ||
        (field.key === "brand_id" &&
          values.series_id != null &&
          !fields.some((item) => item.key === "series_id" && item.writable))
      }
      error={errors[field.key]}
      onChange={(value) => change(field.key, value)}
    />
  );
  const title = editing
    ? "Edit product"
    : completed
      ? "Product saved"
      : (row?.name ?? "Product details");
  const refresh = () => {
    metadata.refresh();
    record.refresh();
  };
  const change = (key: string, value: unknown) => {
    if (blocked) return;
    command.clear();
    setErrors({});
    setDirty(true);
    setValues((current) => ({
      ...current,
      [key]: value,
      ...(key === "brand_id" &&
      current.brand_id !== value &&
      fields.some((field) => field.key === "series_id" && field.writable)
        ? { series_id: null }
        : {}),
    }));
  };
  async function save() {
    if (
      !row ||
      command.pending ||
      !canManage ||
      (modeChanged && !command.uncertain)
    )
      return;
    if (command.uncertain) {
      const recovered = await command.retry<Product>((value) =>
        verifySimpleRecord(value, company, id),
      );
      if (recovered) {
        setSaved(recovered);
        setDirty(false);
      }
      return;
    }
    const result = simpleRecordPatch(config, fields, values, row);
    setErrors(result.errors);
    if (Object.keys(result.errors).length) {
      requestAnimationFrame(() =>
        form.current
          ?.querySelector<HTMLElement>('[aria-invalid="true"]')
          ?.focus(),
      );
      return;
    }
    if (Object.keys(result.body).length === 2) {
      setDirty(false);
      return;
    }
    const updated = await command.execute<Product>(
      {
        path: `/v1/companies/${company}/products/${id}`,
        method: "PATCH",
        body: result.body,
      },
      (value) => verifySimpleRecord(value, company, id),
    );
    if (updated) {
      setSaved(updated);
      setDirty(false);
    }
  }
  useEffect(() => {
    if (command.failure?.fields) setErrors(command.failure.fields);
  }, [command.failure]);
  const Header = editing ? PageHeader : ProductDetailHeader;
  return (
    <div className="janso-page janso-product-management">
      <ProductCatalogNavigation
        resource="items"
        title={title}
        back={editing ? detail : back}
        access={access}
        onLeave={guard.leave}
        hideTabs
      />
      <Header
        fields={fields}
        row={row}
        completed={completed}
        title={title}
        lede={
          completed
            ? "Review the saved product and continue with its management."
            : "Product identity, trading details and specifications."
        }
        actions={
          !editing && row && !failure && !loading ? (
            <>
              {canManage && (
                <a
                  className="janso-btn janso-btn--ghost"
                  href={catalogLink("/masters/items/" + id + "/edit", detail)}
                >
                  Edit product
                </a>
              )}
              <ProductInventoryActions
                triggerLabel="Manage product"
                company={company}
                row={{
                  id: row.id,
                  company_id: row.company_id,
                  name: row.name ?? undefined,
                  code: row.code ?? undefined,
                  sku: row.code,
                  status: row.status,
                  base_unit_id: row.base_unit_id,
                }}
                family={false}
                access={access}
                items={[]}
                returnTo={detail}
              />
            </>
          ) : undefined
        }
      />
      <ProductCatalogFailure failure={failure} retry={refresh} />
      <ProductCatalogFailure
        failure={command.failure}
        write={command.uncertain}
      />
      {modeChanged && (
        <Notice tone="warning">
          Product setup changed. Reload and review before saving. An interrupted
          save can still be recovered.
        </Notice>
      )}
      {loading ? (
        <p role="status">Loading productâ€¦</p>
      ) : (
        !failure &&
        row && (
          <>
            {saved ? (
              <Notice tone="success">
                Changes saved.{" "}
                <a className="janso-link" href={detail}>
                  View product
                </a>
              </Notice>
            ) : (
              completed && (
                <Notice tone={row.status === "ACTIVE" ? "success" : "info"}>
                  {row.status === "ACTIVE"
                    ? "This product is active."
                    : "The product is saved. Review its draft and setup before use."}{" "}
                  Stock and tax effects are recorded through their own
                  workflows.
                </Notice>
              )
            )}
            {!editing ? <ProductDetailView company={company} fields={fields} row={row} access={access} returnTo={detail} /> : <form
              ref={form}
              noValidate
              aria-label={editing ? "Edit product" : "Product details"}
              onSubmit={(event) => {
                event.preventDefault();
                void save();
              }}
            >
              <Card>
                <CardBody>
                  <div className="janso-flow">
                    <SectionHeader title="Product details" />
                    <div className="janso-form-grid">
                      {nativeFields
                        .filter((field) => !tradingKeys.includes(field.key))
                        .map(showField)}
                    </div>
                    {nativeFields.some((field) =>
                      tradingKeys.includes(field.key),
                    ) && (
                      <FieldGroup title="Trading">
                        <div className="janso-form-grid">
                          {nativeFields
                            .filter((field) => tradingKeys.includes(field.key))
                            .map(showField)}
                        </div>
                      </FieldGroup>
                    )}
                    {!editing && (
                      <ReviewList
                        items={fields
                          .filter(
                            (field) =>
                              field.source === "native" &&
                              field.visible &&
                              !field.control &&
                              field.key in row &&
                              !["id", "company_id", "revision"].includes(
                                field.key,
                              ),
                          )
                          .map((field) => ({
                            label: field.label,
                            value: String(
                              row[field.key as keyof Product] ?? "Not set",
                            ),
                          }))}
                      />
                    )}
                    {(["shared_custom_fields", "custom_fields"] as const).map(
                      (group) =>
                        customFields(fields, group).length > 0 && (
                          <section
                            className="janso-flow"
                            key={group}
                            aria-label={
                              group === "shared_custom_fields"
                                ? "Shared product fields"
                                : "Product fields"
                            }
                          >
                            <SectionHeader
                              title={
                                group === "shared_custom_fields"
                                  ? "Shared product fields"
                                  : "Product fields"
                              }
                            />
                            <ProductCatalogCustomFields
                              company={company}
                              fields={customFields(fields, group)}
                              values={{
                                ...(editing ? values : row),
                                custom_fields: (editing ? values : row)[group],
                              }}
                              disabled={
                                !editing || !canManage || blocked || !!saved
                              }
                              errors={errors}
                              onChange={(value) => change(group, value)}
                            />
                          </section>
                        ),
                    )}
                    {Object.keys(errors).length > 0 && (
                      <Notice tone="danger">
                        <ul>
                          {[...new Set(Object.values(errors))].map((error) => (
                            <li key={error}>{error}</li>
                          ))}
                        </ul>
                      </Notice>
                    )}
                  </div>
                </CardBody>
                {editing && !saved && (
                  <FormActions cancel={{ href: detail, onClick: guard.leave }}>
                    <Button
                      type="submit"
                      loading={command.pending}
                      disabled={
                        !canManage ||
                        command.pending ||
                        (!command.uncertain &&
                          (command.blocked || !dirty || modeChanged))
                      }
                    >
                      {command.uncertain ? "Retry same save" : "Save changes"}
                    </Button>
                    <Button
                      variant="ghost"
                      disabled={command.pending || command.uncertain}
                      onClick={() => setReload(true)}
                    >
                      Reload record
                    </Button>
                  </FormActions>
                )}
              </Card>
            </form>}
            {!editing && (
              <div className="janso-form-actions">
                {completed && (
                  <a className="janso-btn janso-btn--primary" href={detail}>
                    View product
                  </a>
                )}
                <a className="janso-btn janso-btn--ghost" href={back}>
                  Return to products
                </a>
                {access.attributes && (
                  <a
                    className="janso-link"
                    href={"/products/attributes?item_id=" + id}
                  >
                    Manage attributes
                  </a>
                )}
              </div>
            )}
          </>
        )
      )}
      {guard.confirmation}
      <ConfirmDialog
        open={reload}
        title="Discard draft and reload?"
        confirmLabel="Discard and reload"
        onCancel={() => setReload(false)}
        onConfirm={() => {
          setDirty(false);
          setSaved(null);
          setReload(false);
          command.clear();
          refresh();
        }}
      >
        The latest product will replace your unsaved entries.
      </ConfirmDialog>
    </div>
  );
}
