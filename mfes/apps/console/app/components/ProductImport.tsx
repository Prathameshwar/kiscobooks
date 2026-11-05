'use client';
import { useRef } from 'react';
import { MasterImport } from './MasterImport';
import {
  productImportProfile,
  simpleProductImportProfile,
} from '../lib/master-import-profiles';
import { useServiceRead } from '../lib/service-resource';
import {
  assertImportJob,
  importBase,
  productImportRequest,
  type ImportJob,
} from '../lib/product-import';
import { ProductCatalogFailure } from './ProductCatalogCommon';
import { useProductMode } from './ProductModeProvider';
import { Button, Notice } from '@janso/ui';
import { businessToday, useDisplayConfig } from '@janso/ui';
import { productImportContext } from '../lib/product-import-context';

export function ProductImport(props: {
  company: string;
  canManage: boolean;
  returnTo?: string;
  initialJob?: string;
  initialHistory?: boolean;
}) {
  const mode = useProductMode();
  const display = useDisplayConfig();
  const initialMode = useRef<boolean | null>(null);
  const retained = useServiceRead<ImportJob>(
    props.initialJob
      ? importBase(props.company) + '/import-jobs/' + props.initialJob
      : undefined,
    productImportRequest,
    (value) => assertImportJob(value, props.initialJob, value.definition),
  );
  if (initialMode.current === null && mode?.data)
    initialMode.current = mode.data.product_family_sku_enabled;
  if (mode && !mode.data)
    return mode.loading ? (
      <p role="status">Loading product import settings…</p>
    ) : (
      <Notice tone="warning">
        {mode.failure?.message}
        <Button onClick={mode.refresh}>Retry</Button>
      </Notice>
    );
  const changed =
    !!mode &&
    (!!mode.failure ||
      initialMode.current !== mode.data?.product_family_sku_enabled);
  if (props.initialJob && !retained.data)
    return retained.loading ? (
      <p role="status">Loading import…</p>
    ) : (
      <ProductCatalogFailure
        failure={retained.failure}
        retry={retained.refresh}
      />
    );
  const simple = retained.data
    ? retained.data.definition === 'simple_products'
    : initialMode.current === false;
  const legacy =
    initialMode.current === false && retained.data?.definition === 'products';
  const profile = simple ? simpleProductImportProfile : productImportProfile;
  return (
    <>
      {changed && (
        <Notice tone="warning">
          Product structure changed or could not be verified. Your import is
          preserved. Reload this page to start an import with the current
          settings.
        </Notice>
      )}
      {legacy && (
        <Notice>
          This earlier import uses the draft product workflow. Its history and
          downloads remain available. Start a new import to create ready
          products.
        </Notice>
      )}
      <MasterImport
        {...props}
        canManage={props.canManage && !changed && !mode?.loading && !legacy}
        profile={{
          ...profile,
          updateOnlyResources: ['item'],
          templateContext: simple
            ? undefined
            : productImportContext(businessToday(display.timezone)),
        }}
      />
    </>
  );
}
