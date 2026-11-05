import type { MasterRow } from './catalog-masters';

/** In-place presentation callbacks; native forms still own validation and writes. */
export type EmbeddedMasterEditor = {
  initialValues?: Record<string, unknown>;
  onSaved: (row: MasterRow) => void;
  onCancel: () => void;
  onStateChange: (state: { dirty: boolean; busy: boolean }) => void;
};
