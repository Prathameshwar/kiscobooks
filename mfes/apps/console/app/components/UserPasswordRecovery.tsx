'use client';
import { useEffect, useRef, useState } from 'react';
import { Button, ConfirmDialog, Notice, TextField, formatDateTime, useDisplayConfig } from '@janso/ui';
import { accessCall } from '../lib/access-directory';
import { signInUrl } from '../lib/navigate';
import { acceptableRecoveryLink } from '../lib/recovery-link';
import { requestFailure } from '../lib/service-call';

type Receipt = { recovery_url?: string | null; expires_at?: string };

/** A link is good for ten minutes; anything much longer is not one this console asked for. */
const MAX_LIFETIME_MS = 11 * 60_000;

/** Back through sign-in with the password asked for again, returning to this very page. */
function signInAgainUrl(): string {
  const href = new URL(signInUrl(), window.location.href);
  href.searchParams.set('reauth', '1');
  href.searchParams.set('returnTo', window.location.pathname + window.location.search);
  return href.href;
}

/**
 * An administrator creating a one-time password-recovery link for another user.
 *
 * The link is a way into the account, so it is held in memory only: never stored, never retried
 * (a second link cancels the first, so a replay would silently invalidate the one just copied), and
 * shown only if it is exactly the shape the sign-in provider issues. It is handed over privately by
 * the administrator; nothing is emailed.
 */
export function UserPasswordRecovery({ userId, name, email }: { userId: string; name: string; email: string }) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState('');
  const [reasonError, setReasonError] = useState('');
  const [pending, setPending] = useState(false);
  const [failure, setFailure] = useState('');
  const [signInAgain, setSignInAgain] = useState(false);
  const [message, setMessage] = useState('');
  const [link, setLink] = useState<{ url: string; expiresAt: string } | null>(null);
  const busy = useRef(false);
  const mounted = useRef(true);
  const display = useDisplayConfig();

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  useEffect(() => {
    if (!link) return;
    const timer = window.setTimeout(
      () => {
        setLink(null);
        setMessage('The recovery link has expired. Create another link if it is still needed.');
      },
      Math.max(0, Date.parse(link.expiresAt) - Date.now()),
    );
    return () => window.clearTimeout(timer);
  }, [link]);

  async function create() {
    if (busy.current) return;
    const text = reason.trim();
    if (text.length < 3 || text.length > 500 || /[\x00-\x1f\x7f]/.test(text)) {
      setReasonError('Enter a reason with 3–500 characters and no control characters.');
      return;
    }
    busy.current = true;
    setPending(true);
    setFailure('');
    setSignInAgain(false);
    setMessage('');
    setLink(null);
    try {
      const receipt = await accessCall<Receipt>({ path: `/v1/users/${userId}/password-recovery`, method: 'POST', body: { reason: text } });
      const expires = Date.parse(receipt.expires_at ?? '');
      const url = new URL(receipt.recovery_url ?? '');
      if (!acceptableRecoveryLink(url) || !Number.isFinite(expires) || expires <= Date.now() || expires > Date.now() + MAX_LIFETIME_MS) {
        throw new Error('Unexpected recovery receipt');
      }
      if (mounted.current) {
        setLink({ url: url.href, expiresAt: receipt.expires_at as string });
        setOpen(false);
        setReason('');
        setMessage(`Recovery link created. Share it privately with ${email}.`);
      }
    } catch (error) {
      // The server's message is ours (and safe); anything else is a receipt we refuse to show.
      const failed = requestFailure(error, 'access service') as { message?: unknown; code?: unknown };
      if (mounted.current) {
        setFailure(typeof failed.message === 'string' && failed.message ? failed.message : 'The recovery link could not be created. Nothing was changed.');
        // A link is a way into someone's account, so the server wants the operator's own password again.
        setSignInAgain(failed.code === 'reauthentication_required');
      }
    } finally {
      busy.current = false;
      if (mounted.current) setPending(false);
    }
  }

  return (
    <div className="janso-flow">
      <Button
        type="button"
        variant="ghost"
        disabled={pending}
        onClick={() => {
          setOpen(true);
          setReason('');
          setReasonError('');
          setFailure('');
          setSignInAgain(false);
        }}
      >
        Create recovery link
      </Button>
      {message && <Notice tone="success">{message}</Notice>}
      {link && (
        <>
          <TextField
            label="Password recovery link"
            value={link.url}
            readOnly
            autoComplete="off"
            hint={`Expires at ${formatDateTime(link.expiresAt, display)}. Anyone with this link can set a new password; share it securely.`}
          />
          <div className="janso-form-actions">
            <Button
              type="button"
              variant="ghost"
              onClick={async () => {
                try {
                  await navigator.clipboard.writeText(link.url);
                  setMessage('Recovery link copied. Share it privately.');
                } catch {
                  setMessage('Select and copy the recovery link above.');
                }
              }}
            >
              Copy recovery link
            </Button>
            <Button
              type="button"
              variant="ghost"
              onClick={() => {
                setLink(null);
                setMessage('Recovery link hidden. It stays valid until it expires or is used.');
              }}
            >
              Hide recovery link
            </Button>
          </div>
        </>
      )}
      <ConfirmDialog
        open={open}
        title="Create a password recovery link?"
        confirmLabel="Create recovery link"
        busy={pending}
        onConfirm={create}
        onCancel={() => {
          if (!busy.current) {
            setOpen(false);
            setFailure('');
            setSignInAgain(false);
          }
        }}
      >
        <p>
          {name} ({email}) will be able to choose a new password with a one-time link that expires in 10 minutes. Creating a new
          link cancels any earlier one. Their current password keeps working until they use it.
        </p>
        <TextField
          label="Reason"
          required
          maxLength={500}
          value={reason}
          error={reasonError}
          disabled={pending}
          onChange={(event) => {
            setReason(event.target.value);
            setReasonError('');
          }}
        />
        {failure && (
          <Notice tone="danger">
            {failure}
            {signInAgain && (
              <>
                {' '}
                <a className="janso-link" href={signInAgainUrl()}>
                  Sign in again
                </a>
              </>
            )}
          </Notice>
        )}
      </ConfirmDialog>
    </div>
  );
}
