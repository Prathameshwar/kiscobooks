'use client';

import { useState } from 'react';
import { Modal, Notice, Select, TextField } from '@janso/ui';
import { useTemplateWrites, type TemplateDraft } from '../../lib/design-commands';
import { goTo } from '../../lib/navigate';
import { VOUCHER_KINDS, kindLabel } from '../../lib/voucher-kinds';
import { LINE_PROFILES } from './layout-model';
import { standardPurchaseStarter } from './standard-purchase';

/**
 * Starting a template.
 *
 * Deliberately four fields and no canvas. A template is created **empty** — a valid draft that
 * prints nothing — and its first version is saved from the editor, because this form knows a
 * name, a code and what paper the thing prints on, and knows nothing whatsoever about layouts.
 *
 * One exception, decided 2026-11-04 (plan R4): opened for **Purchase** (*Customize layout* from
 * Voucher print), the design starts from a copy of the standard Purchase layout for the chosen
 * lines, saved as its first draft version, so customizing means changing what prints today rather
 * than rebuilding it. It is a starting point the person then edits, not a design this form chose.
 * On paper the standard layout does not fit (a roll, A5, landscape) it opens empty as before, and
 * the form says so. Other kinds have no standard canvas yet and keep opening empty.
 *
 * `code` is its own field rather than derived from the name, because the service embeds it in
 * document numbers and makes it unique per tenant: a silently-derived code that collides is a
 * 409 on a field the person never saw.
 *
 * A caller may ask to do something *with* the template before the designer opens (`onCreated`) —
 * Voucher print makes a new template the layout of its voucher in the same step. The form does not
 * know what that is. It only knows that the template now exists, so when the follow-up cannot be
 * done it keeps the template, says so, and offers to open it: submitting again would not retry the
 * follow-up, it would collide on the code.
 */

const PAPER = [
  { value: 'A4', label: 'A4 (210 × 297mm)' },
  { value: 'LETTER', label: 'Letter (215.9 × 279.4mm)' },
  { value: 'A5', label: 'A5 (148 × 210mm)' },
  { value: 'THERMAL_80MM', label: '80mm roll' },
  { value: 'THERMAL_58MM', label: '58mm roll' },
  { value: 'CUSTOM', label: 'Custom size' },
];

const CODE = /^[A-Za-z0-9][A-Za-z0-9_-]{0,49}$/;

const BLANK: TemplateDraft = { name: '', code: '', paperSize: 'A4', orientation: 'PORTRAIT' };

/** Kinds whose documents are money only: their lines are accounts, never products. */
const MONEY_KINDS = new Set(['RECEIPT', 'PAYMENT', 'CONTRA', 'JOURNAL']);
/** The lines a new design for `kind` starts with, before anyone chooses. */
export function defaultLineProfile(kind: string): string {
  return MONEY_KINDS.has(kind) ? 'ACCOUNTS' : 'ITEMS';
}

export function NewTemplateDialog({
  company,
  open,
  onClose,
  note,
  title = 'New template',
  onCreated,
  kind,
}: {
  company: string;
  /** The voucher kind the design is for, when the caller already knows it (Voucher print). */
  kind?: string;
  open: boolean;
  onClose: () => void;
  /** Where this was opened from, and what happens next — a sentence the form itself cannot know. */
  note?: string;
  /** The dialog's title and the person's word for what they are doing — "Customize layout", say. */
  title?: string;
  /**
   * Runs once the template exists, before the designer opens. Resolves to `null` when done, or to a
   * sentence saying what could not be done — the template is kept either way.
   */
  onCreated?: (template: { id: string }) => Promise<string | null>;
}) {
  const writes = useTemplateWrites(company);
  const fresh = (): TemplateDraft => (kind ? { ...BLANK, voucherKind: kind, lineProfile: defaultLineProfile(kind) } : BLANK);
  const [draft, setDraft] = useState<TemplateDraft>(fresh);
  const [touched, setTouched] = useState(false);
  // `finishing` covers the follow-up, which `writes.pending` does not: a second click in that gap
  // would create a second template.
  const [finishing, setFinishing] = useState(false);
  const [kept, setKept] = useState<{ id: string; message: string } | null>(null);

  const custom = draft.paperSize === 'CUSTOM';
  // Checked here as well as server-side, so the reader is told before a round trip rather
  // than after one. The service is still the one that decides.
  const codeError = touched && !CODE.test(draft.code.trim()) ? 'Letters, digits, hyphen and underscore; up to 50.' : undefined;
  const nameError = touched && !draft.name.trim() ? 'A name is required.' : undefined;
  const sizeError =
    touched && custom && !(Number(draft.widthMm) > 0 && Number(draft.heightMm) > 0)
      ? 'A custom size needs both a width and a height in millimetres.'
      : undefined;
  const ready = !nameError && !codeError && !sizeError && draft.name.trim() && CODE.test(draft.code.trim());
  // Only *Customize* for Purchase starts from the standard layout: the gallery's plain "New
  // template" keeps its empty page whichever kind is chosen.
  const standard = kind === 'PURCHASE';
  const starter = standard ? standardPurchaseStarter(draft.lineProfile, draft) : null;

  const set = (patch: Partial<TemplateDraft>) => setDraft((current) => ({ ...current, ...patch }));

  async function submit(): Promise<void> {
    setTouched(true);
    if (!ready) return;
    const created = await writes.create(draft, starter);
    if (!created) return;
    if (onCreated) {
      setFinishing(true);
      let problem: string | null;
      try {
        problem = await onCreated(created);
      } catch {
        problem = 'The next step could not be completed.';
      } finally {
        setFinishing(false);
      }
      if (problem) {
        setKept({ id: created.id, message: problem });
        return;
      }
    }
    // Straight into the editor: a created template is empty, and a gallery card for something
    // with nothing in it is a dead end.
    goTo('/invoice-designer/' + created.id);
  }

  function close(): void {
    // Only reachable between requests: Cancel is disabled while one is in flight, and the modal's `busy`
    // holds Escape, the scrim and the close button — a dialog that vanished mid-request would still
    // navigate away, or report a failure to a dialog nobody can see.
    writes.clear();
    // A template that was kept is already made, so the form that made it must not stay filled in for a
    // second try that could only collide on its code.
    if (kept) {
      setDraft(fresh());
      setTouched(false);
    }
    setKept(null);
    onClose();
  }

  return (
    <Modal
      open={open}
      title={title}
      size="sm"
      busy={writes.pending || finishing}
      onClose={close}
      footer={
        kept ? (
          <>
            <button type="button" className="janso-btn janso-btn--ghost" onClick={close}>
              Not now
            </button>
            <button
              type="button"
              className="janso-btn janso-btn--primary"
              onClick={() => goTo('/invoice-designer/' + kept.id)}
            >
              Open the template
            </button>
          </>
        ) : (
          <>
            <button
              type="button"
              className="janso-btn janso-btn--ghost"
              disabled={writes.pending || finishing}
              onClick={close}
            >
              Cancel
            </button>
            <button
              type="button"
              className="janso-btn janso-btn--primary"
              disabled={writes.pending || finishing}
              onClick={() => void submit()}
            >
              {writes.pending || finishing ? 'Creating…' : 'Create and open'}
            </button>
          </>
        )
      }
    >
      {kept ? (
        <Notice tone="warning">The template was created. {kept.message}</Notice>
      ) : (
        <div className="janso-flow">
          {note ? <Notice>{note}</Notice> : null}
          {standard ? (
            <p className="janso-meta" data-testid="template-starter">
              {starter
                ? 'It starts from a copy of the standard Purchase layout, saved as a draft. Nothing prints on it until you publish it.'
                : 'The standard Purchase layout is drawn for A4 or Letter portrait, so on this paper the design starts on an empty page.'}
            </p>
          ) : null}
          {writes.failure ? <Notice tone="danger">{writes.failure}</Notice> : null}

          <div className="janso-form-grid">
            <TextField
              label="Name"
              value={draft.name}
              maxLength={100}
              error={nameError ?? writes.fields?.name}
              onChange={(event) => set({ name: event.target.value })}
            />
            <TextField
              label="Code"
              hint="Printed into document numbers, and unique within the tenant."
              value={draft.code}
              maxLength={50}
              error={codeError ?? writes.fields?.code}
              onChange={(event) => set({ code: event.target.value })}
            />
            <Select
              label="Paper"
              value={draft.paperSize}
              options={PAPER}
              onChange={(paperSize) => set({ paperSize })}
            />
            <Select
              label="Orientation"
              value={draft.orientation}
              options={[
                { value: 'PORTRAIT', label: 'Portrait' },
                { value: 'LANDSCAPE', label: 'Landscape' },
              ]}
              onChange={(orientation) => set({ orientation })}
            />
            {kind ? (
              <TextField label="Prints" value={kindLabel(kind)} readOnly hint="The kind of voucher this design is for." />
            ) : (
              <Select
                label="Prints"
                hint="The kind of voucher this design is for. Any voucher keeps it open to every kind."
                value={draft.voucherKind ?? ''}
                options={[{ value: '', label: 'Any voucher' }, ...VOUCHER_KINDS.map((entry) => ({ value: entry.value, label: kindLabel(entry.value) }))]}
                onChange={(voucherKind) =>
                  set(voucherKind ? { voucherKind, lineProfile: defaultLineProfile(voucherKind) } : { voucherKind: '', lineProfile: '' })
                }
              />
            )}
            {draft.voucherKind ? (
              <Select
                label="Lines"
                hint="Which tables the design offers: a product table, an accounts and expenses table, or both."
                value={draft.lineProfile ?? defaultLineProfile(draft.voucherKind)}
                options={LINE_PROFILES}
                onChange={(lineProfile) => set({ lineProfile })}
              />
            ) : null}
            {custom ? (
              <>
                <TextField
                  label="Width (mm)"
                  value={draft.widthMm ?? ''}
                  inputMode="decimal"
                  error={sizeError}
                  onChange={(event) => set({ widthMm: event.target.value })}
                />
                <TextField
                  label="Height (mm)"
                  value={draft.heightMm ?? ''}
                  inputMode="decimal"
                  onChange={(event) => set({ heightMm: event.target.value })}
                />
              </>
            ) : null}
          </div>
        </div>
      )}
    </Modal>
  );
}
