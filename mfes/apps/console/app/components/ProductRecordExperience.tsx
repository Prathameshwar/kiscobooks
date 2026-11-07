"use client";
import { ErrorState, Notice, Button } from "@janso/ui";
import type { MasterConfig } from "../lib/catalog-masters";
import type { ClassificationAccess } from "../lib/product-classification-resources";
import { useProductMode } from "./ProductModeProvider";
import { ProductCatalogDetail } from "./ProductCatalogDetail";
import { ProductCatalogEditor } from "./ProductCatalogEditor";
import { SimpleProductRecord } from "./SimpleProductRecord";
import { useRef } from "react";

export function ProductRecordExperience(props: {
  company: string;
  config: MasterConfig;
  id: string;
  returnTo?: string;
  canManage: boolean;
  access: ClassificationAccess;
  editing?: boolean;
  completed?: boolean;
}) {
  const mode = useProductMode();
  const entry = useRef<boolean | null>(null);
  const entryVersion = useRef<number | null>(null);
  if (
    entry.current === null &&
    mode?.company === props.company &&
    mode.data &&
    !mode.loading &&
    !mode.failure
  )
    { entry.current = mode.data.product_family_sku_enabled; entryVersion.current = mode.data.row_version; }
  if (!mode || mode.company !== props.company)
    return (
      <ErrorState
        status={403}
        detail="Product setup could not be verified for this company."
      />
    );
  if (entry.current === null && mode.failure)
    return (
      <div className="janso-page">
        <Notice tone="warning">Product setup could not be verified.</Notice>
        <Button onClick={mode.refresh}>Retry product setup</Button>
      </div>
    );
  if (entry.current === null && (mode.loading || !mode.data))
    return (
      <p className="janso-page" role="status">
        Checking product setup…
      </p>
    );
  if (entry.current === false) {
    if (props.config.resource === "product-families")
      return (
        <ErrorState
          status={403}
          detail="Product Profiles are available when Advanced product mode is enabled."
        />
      );
    return <SimpleProductRecord {...props} />;
  }
  if (props.editing) return <ProductCatalogEditor {...props} blockedByMode={!!mode.failure || mode.loading || !mode.data || mode.data.product_family_sku_enabled !== entry.current || mode.data.row_version !== entryVersion.current} />;
  return <ProductCatalogDetail {...props} />;
}
