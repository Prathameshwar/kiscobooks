'use client';
import { useCallback, useEffect, useMemo } from 'react';
import type { components } from '@janso/api-client/design';
import { assertDesignRow, designRequest } from './design-api';
import { serviceCall, type RequestFailure, type ServiceRequest } from './service-call';
import { useServiceCommand, useServiceRead } from './service-resource';

type Wire = components['schemas'];

const assetsBase = (company: string) => `/v1/companies/${company}/assets`;

/** The service's own page ceiling; a template's brand assets do not grow past one page. */
const PAGE = 200;

/**
 * Brand assets already uploaded for the company, keyed for the canvas preview to resolve an
 * `assetId` to a real image without the schema ever carrying a token (`layout-model.ts`'s
 * `assetId` names an `invoice_template_asset`, nothing else).
 *
 * The download token (`AssetItem.download_token`) is minted on this read and expires in two
 * minutes (`design/api/routes.py::asset_download_codec`), so this list refreshes on an interval
 * rather than once — an editing session that outlives one token must not go on showing a broken
 * image for the rest of it.
 */
export type AssetList = {
  items: Wire['AssetItem'][];
  loading: boolean;
  failure: RequestFailure | null;
  refresh: () => void;
};

export function useDesignAssets(
  company: string | undefined,
  /**
   * Withdrawn assets too. The designer's print checks need them, to say "this picture has been
   * withdrawn" rather than nothing; a picker must not offer them, and filters on `is_active`.
   */
  options: { includeInactive?: boolean } = {},
): AssetList {
  const read = useServiceRead<{ items: Wire['AssetItem'][] }>(
    company ? `${assetsBase(company)}?limit=${PAGE}&include_inactive=${options.includeInactive ? 'true' : 'false'}` : undefined,
    designRequest,
    (value) => {
      if (!Array.isArray(value.items)) {
        throw { status: 502, message: 'The asset list could not be verified.' };
      }
      for (const item of value.items) assertDesignRow(item as never, company!);
    },
    'design service',
  );

  // Half the token's own lifetime: a canvas left open keeps a live image rather than one that
  // silently 401s the next time this company's assets are read.
  useEffect(() => {
    if (!company) return;
    const timer = setInterval(() => read.refresh(), 60_000);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `read.refresh` is stable per mount; re-arming per render would reset the interval every read.
  }, [company]);

  return { items: read.data?.items ?? [], loading: read.loading, failure: read.failure, refresh: read.refresh };
}

/** `assetId → the fields `DocumentLayer` needs to render it`, built once per asset list read. */
export type AssetSource = Record<string, { downloadToken: string; mimeType: string }>;

export function assetSourceOf(assets: readonly Wire['AssetItem'][]): AssetSource {
  const source: AssetSource = {};
  for (const asset of assets) {
    if (asset.is_active && asset.download_token) {
      source[asset.id] = { downloadToken: asset.download_token, mimeType: asset.mime_type };
    }
  }
  return source;
}

const designAssetUploadRequest = <T,>(request: ServiceRequest) =>
  serviceCall<T>('/api/design-asset-upload', { service: 'design', ...request }, 'design service');

export type AssetUploadInput = {
  file: File;
  assetName: string;
  assetType: Wire['AssetUpload']['asset_type'];
};

export type AssetWrites = {
  upload: (input: AssetUploadInput) => Promise<Wire['AssetDetail'] | null>;
  pending: boolean;
  failure: string | null;
  clear: () => void;
};

/** Reads a `File` the way the schema wants it: base64, with no `data:` prefix. */
function readFileAsBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = typeof reader.result === 'string' ? reader.result : '';
      const comma = result.indexOf(',');
      resolve(comma === -1 ? result : result.slice(comma + 1));
    };
    reader.onerror = () => reject(reader.error ?? new Error('Could not read the file.'));
    reader.readAsDataURL(file);
  });
}

export function useDesignAssetWrites(company: string | undefined): AssetWrites {
  const command = useServiceCommand(designAssetUploadRequest, 'design service');

  const upload = useCallback(
    async (input: AssetUploadInput) => {
      if (!company) return null;
      const content_base64 = await readFileAsBase64(input.file);
      return command.execute<Wire['AssetDetail']>(
        {
          path: assetsBase(company),
          method: 'POST',
          body: {
            asset_name: input.assetName,
            asset_type: input.assetType,
            file_name: input.file.name,
            mime_type: input.file.type,
            content_base64,
          },
        },
        (value) => {
          assertDesignRow(value as never, company);
        },
      );
    },
    [company, command],
  );

  return useMemo(
    () => ({ upload, pending: command.pending, failure: command.failure?.message ?? null, clear: command.clear }),
    [command.clear, command.failure, command.pending, upload],
  );
}
