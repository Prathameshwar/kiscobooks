'use client';

import {
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
  useRef,
  useState,
} from 'react';
import { PX_PER_MM, formatMm } from '../lib/paper';
import { HANDLES, type Handle } from '../lib/transform';

/** A rectangle on the page, in absolute paper millimetres. */
export type TargetRect = {
  readonly xMm: number;
  readonly yMm: number;
  readonly widthMm: number;
  readonly heightMm: number;
};

export type SelectionTarget = {
  readonly id: string;
  /** A zone reads as a region of the page; an element is an object on it. */
  readonly kind: 'zone' | 'element';
  /** Shown on the hover chip and read out as the option's accessible name. */
  readonly label: string;
  readonly rect: TargetRect;
};

export type SelectionCommand =
  | 'next'
  | 'previous'
  | 'parent'
  | 'child'
  | 'first'
  | 'last'
  | 'clear';

/** A drag in progress, reported in paper millimetres. */
export type TransformGesture = {
  readonly id: string;
  /** `null` while moving; the handle being pulled while resizing. */
  readonly handle: Handle | null;
  /** Measured from where the pointer went down, not from the previous event. */
  readonly dxMm: number;
  readonly dyMm: number;
  /**
   * `start` is the first event that counts as a drag, `end` the last.
   *
   * The phase is explicit rather than inferred because the caller has to pin the rectangle
   * the gesture started from: guessing "this looks like a new drag" from the deltas leaves a
   * stale origin behind whenever a pointerup goes missing, and the element then jumps back
   * to where the *previous* drag began.
   */
  readonly phase: 'start' | 'move' | 'end';
};

/** Whether an action adds to the selection or replaces it. */
export type SelectionIntent = { readonly additive?: boolean };

/** A rubber band finished on bare paper, in absolute paper millimetres. */
export type MarqueeRect = {
  readonly xMm: number;
  readonly yMm: number;
  readonly widthMm: number;
  readonly heightMm: number;
};

type SelectionLayerProps = {
  targets: readonly SelectionTarget[];
  /**
   * The active target: what `aria-activedescendant` points at, what the handles attach to,
   * and what a drag is anchored on. One of `selectedIds`, normally the last one added.
   */
  selectedId: string | null;
  /** The whole selection. Defaults to just the active one. */
  selectedIds?: readonly string[];
  hoveredId: string | null;
  onSelect: (id: string | null, intent?: SelectionIntent) => void;
  onHover: (id: string | null) => void;
  /** Arrow keys, Home/End, Escape. The layer owns no model, so it only reports intent. */
  onKeyCommand?: (command: SelectionCommand, intent?: SelectionIntent) => void;
  /**
   * A rubber band dragged across bare paper. Reported once, on release, in paper
   * millimetres — the caller decides what "inside" means, because only it knows which
   * targets are elements and which are the zones behind them.
   */
  onMarquee?: (rect: MarqueeRect, intent?: SelectionIntent) => void;
  /**
   * A drag on the selection: the ring moves it, a handle resizes it. Deltas are in paper
   * millimetres; the caller decides what snapping and clamping mean, because only it knows
   * the zone the thing lives in.
   */
  onTransform?: (gesture: TransformGesture) => void;
  /** Double-click, or Enter on the selection — "work on the thing itself". */
  onActivate?: (id: string) => void;
  /** Needed to turn screen pixels into paper millimetres. */
  zoom?: number;
  /** Resize handles are drawn for an element, not for a zone the layout positions. */
  handlesFor?: 'element' | 'none';
  label?: string;
};

/**
 * The editing affordances, as a layer above the document.
 *
 * **Why a layer rather than handlers on the document.** The document renderer has to stay
 * print-pure: the server renderer must produce the same page from the same layout, and a
 * renderer that had to strip editor markup would eventually strip the wrong thing. So
 * nothing below this layer knows that editing exists.
 *
 * **Why a listbox.** A page carries up to 200 elements. Making each one a tab stop is a
 * keyboard trap with good intentions; making the layer one stop with arrow-key movement is
 * the pattern assistive technology already knows, and it leaves Tab free to move between
 * the rail, the canvas and the inspector.
 *
 * **Why the drag reports deltas rather than positions.** Snapping, bounds and the grid
 * belong to the layout model — this layer would have to be told the zone, the page and the
 * grid step to apply them, and then there would be two places that knew the rules.
 *
 * **Multi-selection is a set plus an active member**, which is what a listbox already is:
 * `aria-selected` marks every member, `aria-activedescendant` names the one the keyboard is
 * on. Handles are drawn only for a lone selection — resizing several at once is a different
 * feature (proportional scaling), and eight grips around a group that only moves would
 * promise it.
 *
 * Hover and keyboard focus render identically on purpose — they mean the same thing: this
 * is the thing you are about to act on.
 */
export function SelectionLayer({
  targets,
  selectedId,
  selectedIds,
  hoveredId,
  onSelect,
  onHover,
  onKeyCommand,
  onMarquee,
  onTransform,
  onActivate,
  zoom = 1,
  handlesFor = 'element',
  label = 'Page elements',
}: SelectionLayerProps) {
  const selected = targets.find((target) => target.id === selectedId) ?? null;
  const chosen = new Set(selectedIds ?? (selectedId ? [selectedId] : []));
  const layer = useRef<HTMLDivElement | null>(null);
  const [band, setBand] = useState<MarqueeRect | null>(null);
  const marquee = useRef<{ xMm: number; yMm: number; additive: boolean } | null>(null);
  /**
   * A finished marquee is followed by a click on bare paper, which otherwise reads as
   * "select nothing" and throws away what the band just caught. The band consumes that one
   * click.
   */
  const swept = useRef(false);
  /**
   * Screen pixels to paper millimetres, to a hundredth — finer than anything a printer
   * can place and finer than the layout model's own 0.1mm, so nothing is lost, while the
   * reported delta stays a measurement instead of `4.999999999999998`.
   */
  const toMm = (px: number) => Math.round((px / (PX_PER_MM * zoom)) * 100) / 100;
  const drag = useRef<{
    id: string;
    handle: Handle | null;
    startX: number;
    startY: number;
    moved: boolean;
  } | null>(null);

  function onKeyDown(event: ReactKeyboardEvent<HTMLDivElement>) {
    if ((event.key === 'Enter' || event.key === 'F2') && selectedId && onActivate) {
      event.preventDefault();
      onActivate(selectedId);
      return;
    }
    const commands: Record<string, SelectionCommand> = {
      ArrowDown: 'next',
      ArrowRight: 'child',
      ArrowUp: 'previous',
      ArrowLeft: 'parent',
      Home: 'first',
      End: 'last',
      Escape: 'clear',
    };
    const command = commands[event.key];
    if (!command || !onKeyCommand) return;
    // Alt is the transform modifier: the shell nudges the element instead of moving the
    // selection, so the layer must not also consume the key.
    if (event.altKey) return;
    // The arrows must not scroll the canvas out from under the selection they just moved.
    event.preventDefault();
    // Shift extends, the same as it does in a list of files. Escape never extends: it
    // means "nothing", and "add nothing to the selection" is not a thing anyone wants.
    onKeyCommand(command, {
      additive: event.shiftKey && command !== 'clear',
    });
  }

  /** The pointer's position on the paper, from the layer's own box. */
  function paperAt(event: ReactPointerEvent<HTMLElement>): { xMm: number; yMm: number } | null {
    const box = layer.current?.getBoundingClientRect();
    if (!box) return null;
    return { xMm: toMm(event.clientX - box.left), yMm: toMm(event.clientY - box.top) };
  }

  function startMarquee(event: ReactPointerEvent<HTMLDivElement>) {
    if (!onMarquee || event.button !== 0) return;
    // Only bare paper: a pointerdown on a target is that target's, and a marquee starting
    // under the pointer would fight every drag.
    if (event.target !== event.currentTarget) return;
    const at = paperAt(event);
    if (!at) return;
    event.currentTarget.setPointerCapture?.(event.pointerId);
    marquee.current = { ...at, additive: event.shiftKey || event.ctrlKey || event.metaKey };
  }

  function moveMarquee(event: ReactPointerEvent<HTMLDivElement>) {
    const start = marquee.current;
    if (!start) return;
    const at = paperAt(event);
    if (!at) return;
    setBand({
      xMm: Math.min(start.xMm, at.xMm),
      yMm: Math.min(start.yMm, at.yMm),
      widthMm: Math.abs(at.xMm - start.xMm),
      heightMm: Math.abs(at.yMm - start.yMm),
    });
  }

  /**
   * `commit` separates a release from a cancellation. A cancelled gesture reports nothing —
   * the pointer was taken away, not lifted — and that also keeps `swept` honest: a cancel
   * is followed by no click, so a flag set there would eat the next real one.
   */
  function endMarquee(event: ReactPointerEvent<HTMLDivElement>, commit: boolean) {
    const start = marquee.current;
    marquee.current = null;
    const rect = band;
    setBand(null);
    // Both halves optional, and both guarded: releasing a pointer that was never captured
    // throws, and jsdom implements neither.
    if (event.currentTarget.hasPointerCapture?.(event.pointerId)) {
      event.currentTarget.releasePointerCapture?.(event.pointerId);
    }
    if (!commit || !start || !rect || !onMarquee) return;
    // A band of nothing is a click on bare paper, which the click handler already reads as
    // "select nothing".
    if (rect.widthMm < 1 && rect.heightMm < 1) return;
    swept.current = true;
    onMarquee(rect, { additive: start.additive });
  }

  function startDrag(
    event: ReactPointerEvent<HTMLElement>,
    id: string,
    handle: Handle | null,
  ) {
    if (!onTransform) return;
    // Primary button only: a right-click during a drag would otherwise strand the gesture.
    if (event.button !== 0) return;
    event.preventDefault();
    event.stopPropagation();
    // Capture keeps the drag with this node when the pointer outruns it. Optional because
    // jsdom does not implement pointer capture, and a drag must still be testable.
    event.currentTarget.setPointerCapture?.(event.pointerId);
    drag.current = { id, handle, startX: event.clientX, startY: event.clientY, moved: false };
  }

  function onPointerMove(event: ReactPointerEvent<HTMLElement>) {
    const gesture = drag.current;
    if (!gesture || !onTransform) return;
    const dxMm = toMm(event.clientX - gesture.startX);
    const dyMm = toMm(event.clientY - gesture.startY);
    // A click is a pointerdown and a pointerup with a pixel of jitter between them; only
    // report a transform once the pointer has travelled far enough to mean one.
    if (!gesture.moved && Math.abs(dxMm) < 0.3 && Math.abs(dyMm) < 0.3) return;
    const phase = gesture.moved ? 'move' : 'start';
    gesture.moved = true;
    onTransform({ id: gesture.id, handle: gesture.handle, dxMm, dyMm, phase });
  }

  function endDrag(event: ReactPointerEvent<HTMLElement>) {
    const gesture = drag.current;
    drag.current = null;
    // Both halves optional, and both guarded: releasing a pointer that was never captured
    // throws, and jsdom implements neither.
    if (event.currentTarget.hasPointerCapture?.(event.pointerId)) {
      event.currentTarget.releasePointerCapture?.(event.pointerId);
    }
    if (gesture?.moved && onTransform) {
      onTransform({ id: gesture.id, handle: gesture.handle, dxMm: 0, dyMm: 0, phase: 'end' });
    }
  }

  return (
    <div
      ref={layer}
      className="janso-canvas__select"
      role="listbox"
      aria-label={label}
      /* A caller that handles a band handles a set — there is nothing else a rubber band
       * could mean — so the one prop answers both questions. */
      aria-multiselectable={onMarquee ? true : undefined}
      aria-activedescendant={selected ? `target-${selected.id}` : undefined}
      tabIndex={0}
      onKeyDown={onKeyDown}
      onPointerLeave={() => onHover(null)}
      onPointerDown={onMarquee ? startMarquee : undefined}
      onPointerMove={onMarquee ? moveMarquee : undefined}
      onPointerUp={onMarquee ? (event) => endMarquee(event, true) : undefined}
      onPointerCancel={onMarquee ? (event) => endMarquee(event, false) : undefined}
      /* Bare paper is not a target, so a click that reaches the layer means "nothing":
       * every target stops its own click, so this only fires on the gaps between them —
       * except the one that ends a marquee, which the band has already answered. */
      onClick={() => {
        if (swept.current) {
          swept.current = false;
          return;
        }
        onSelect(null);
      }}
      data-testid="selection-layer"
    >
      {band ? (
        <div
          className="janso-canvas__marquee"
          aria-hidden="true"
          data-testid="marquee"
          style={{
            left: `${band.xMm}mm`,
            top: `${band.yMm}mm`,
            width: `${band.widthMm}mm`,
            height: `${band.heightMm}mm`,
          }}
        />
      ) : null}

      {targets.map((target) => {
        const picked = chosen.has(target.id);
        const state = picked ? 'selected' : target.id === hoveredId ? 'hovered' : 'idle';
        /* Only an object is dragged. A zone is placed by the layout — offering a grab
         * cursor on one would promise a move that nothing downstream can apply. */
        const draggable = picked && target.kind === 'element' && Boolean(onTransform);
        return (
          <div
            key={target.id}
            id={`target-${target.id}`}
            className="janso-canvas__target"
            role="option"
            aria-selected={picked}
            aria-label={target.label}
            data-kind={target.kind}
            data-state={state}
            /* The active member of the selection, drawn a shade stronger: with four rings
             * on the page, which one the keyboard will act on has to be visible. */
            data-active={target.id === selectedId || undefined}
            data-target={target.id}
            data-draggable={draggable || undefined}
            style={{
              left: `${target.rect.xMm}mm`,
              top: `${target.rect.yMm}mm`,
              width: `${target.rect.widthMm}mm`,
              height: `${target.rect.heightMm}mm`,
            }}
            onPointerEnter={() => onHover(target.id)}
            /* Leaving a target inside the layer never reaches the container's own
             * pointerleave, so without this the outline would stay behind on bare paper. */
            onPointerLeave={() => onHover(null)}
            onPointerDown={draggable ? (event) => startDrag(event, target.id, null) : undefined}
            onPointerMove={draggable ? onPointerMove : undefined}
            onPointerUp={draggable ? endDrag : undefined}
            onPointerCancel={draggable ? endDrag : undefined}
            onDoubleClick={
              onActivate
                ? (event) => {
                    event.stopPropagation();
                    onActivate(target.id);
                  }
                : undefined
            }
            onClick={(event) => {
              // A zone sits under its elements; clicking an element must not also select
              // the zone behind it.
              event.stopPropagation();
              // Shift and ctrl/cmd both add, because both are muscle memory depending on
              // which application taught you, and neither means anything else here.
              onSelect(target.id, {
                additive: event.shiftKey || event.ctrlKey || event.metaKey,
              });
            }}
          >
            {state !== 'idle' ? <span className="janso-canvas__label">{target.label}</span> : null}

            {state === 'selected' ? (
              <>
                {/* One badge, not four: with several selected, the sizes differ and the
                 * group's own box is what the inspector states. */}
                {chosen.size === 1 ? (
                  <span className="janso-canvas__badge" data-testid="selection-size">
                    {formatMm(target.rect.widthMm)} × {formatMm(target.rect.heightMm)} mm
                  </span>
                ) : null}
                {/* Handles are a pointer affordance for a drag that can actually happen: a
                 * shipped, read-only template draws none, because eight grips that do
                 * nothing when pulled are worse than no grips at all. Nor does a group —
                 * scaling several elements together is a different feature, and grips that
                 * only moved would promise it. */}
                {draggable && handlesFor === 'element' && chosen.size === 1
                  ? HANDLES.map((at) => (
                      // Pointer affordances: the keyboard equivalent is alt+arrow to move
                      // and alt+ctrl+arrow to resize, which the shell owns, so eight
                      // focusable dots would duplicate a control that already exists.
                      <span
                        key={at}
                        className="janso-canvas__handle"
                        data-at={at}
                        data-handle={at}
                        aria-hidden="true"
                        onPointerDown={
                          onTransform ? (event) => startDrag(event, target.id, at) : undefined
                        }
                        onPointerMove={onTransform ? onPointerMove : undefined}
                        onPointerUp={onTransform ? endDrag : undefined}
                        onPointerCancel={onTransform ? endDrag : undefined}
                      />
                    ))
                  : null}
              </>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
