'use client';

import { useState } from 'react';
import { EditorSelect, FileUpload, InspectorRow, InspectorStack, type FileUploadItem } from '@janso/ui';
import type { components } from '@janso/api-client/design';
import { useDesignAssets, useDesignAssetWrites } from '../../lib/design-assets';

type AssetType = components['schemas']['AssetUpload']['asset_type'];

/** The upload's default kind by the element that is about to show it; the type is still typed data, never free text. */
const DEFAULT_ASSET_TYPE: Record<'IMAGE' | 'SIGNATURE', AssetType> = {
  IMAGE: 'LOGO',
  SIGNATURE: 'SIGNATURE',
};

/** `MAXIMUM_IMAGE_BYTES` (`design/schemas/assets.py`) — checked here only to save a round trip. */
const MAXIMUM_IMAGE_BYTES = 5 * 1024 * 1024;

type AssetPickerProps = {
  company: string;
  elementType: 'IMAGE' | 'SIGNATURE';
  value: string | undefined;
  onChange: (assetId: string | undefined) => void;
  disabled?: boolean;
};

/**
 * Picking or uploading the brand asset an `IMAGE` or `SIGNATURE` element shows (plan P4,
 * 2026-11-03).
 *
 * The list and the upload are two different requests on purpose, the same split as every other
 * write in this editor: choosing an existing logo must not wait on an upload round trip, and an
 * upload that fails must not clear what was already selected.
 */
export function AssetPicker({ company, elementType, value, onChange, disabled = false }: AssetPickerProps) {
  const assets = useDesignAssets(company);
  const writes = useDesignAssetWrites(company);
  /* The file currently uploading or that last failed — never the message, which `writes.failure`
   * already holds reactively. Reading `writes.failure` from inside the `async` handler below
   * would close over the render it started in, before the command's own state update landed. */
  const [pendingFile, setPendingFile] = useState<File | null>(null);

  async function tryUpload(file: File) {
    setPendingFile(file);
    writes.clear();
    const created = await writes.upload({
      file,
      assetName: file.name.replace(/\.[^.]+$/, '') || file.name,
      assetType: DEFAULT_ASSET_TYPE[elementType],
    });
    if (created) {
      setPendingFile(null);
      assets.refresh();
      onChange(created.id);
    }
  }

  const items: FileUploadItem[] = pendingFile
    ? [{
        id: 'asset-upload',
        name: pendingFile.name,
        size: pendingFile.size,
        status: writes.pending ? 'uploading' : 'failed',
        error: writes.failure ?? undefined,
      }]
    : [];

  return (
    <>
      <InspectorRow label="Asset" hint={assets.failure ? assets.failure.message : undefined}>
        <EditorSelect
          label="Choose a saved asset"
          value={value ?? ''}
          options={[
            { value: '', label: assets.loading ? 'Loading…' : 'None' },
            ...assets.items
              .filter((asset) => asset.is_active)
              .map((asset) => ({ value: asset.id, label: asset.asset_name })),
          ]}
          disabled={disabled}
          onChange={(assetId) => onChange(assetId || undefined)}
        />
      </InspectorRow>
      <InspectorStack label="Upload new">
        <FileUpload
          label="Upload an image"
          hideLabel
          items={items}
          accept="image/png,image/jpeg,image/webp"
          acceptLabel="PNG, JPEG or WebP"
          maxSizeBytes={MAXIMUM_IMAGE_BYTES}
          disabled={disabled || writes.pending}
          onSelect={(files) => {
            const file = files[0];
            if (file) void tryUpload(file);
          }}
          onRetry={() => pendingFile && void tryUpload(pendingFile)}
          onRemove={() => { setPendingFile(null); writes.clear(); }}
        />
      </InspectorStack>
    </>
  );
}
