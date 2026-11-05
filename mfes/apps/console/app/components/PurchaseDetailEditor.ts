import type { Dispatch, ReactNode, SetStateAction } from 'react';
import type { PurchaseWorkspaceDraft, PurchaseWorkspacePolicy } from '../lib/purchase-workspace';
import type { PurchaseDetails } from '../lib/purchase-workspace-details';

export type PurchaseDetailEditorProps = {
  draft: PurchaseWorkspaceDraft; policy: PurchaseWorkspacePolicy;
  setDetails: Dispatch<SetStateAction<PurchaseDetails>>; disabled: boolean;
  error: (field: string) => string | undefined;
  number: (field: string, label: string, value: string, onChange: (value: string) => void,
    options?: { quantity?: boolean; unit?: string; hint?: string }) => ReactNode;
};
