/** Keyboard, pointer, and touch-accessible help text for Atlas design §11. */

import { useEffect, useId, useRef, useState } from 'react';

interface InfoTipProps {
  children: React.ReactNode;
  label: string;
}

export function InfoTip({ children, label }: InfoTipProps) {
  const id = useId();
  const container = useRef<HTMLSpanElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(false);
  const [pinned, setPinned] = useState(false);

  useEffect(() => {
    const closeFromOutside = (event: PointerEvent) => {
      if (!container.current?.contains(event.target as Node)) {
        setOpen(false);
        setPinned(false);
      }
    };
    const closeForPeer = (event: Event) => {
      if ((event as CustomEvent<string>).detail !== id) {
        setOpen(false);
        setPinned(false);
      }
    };
    document.addEventListener('pointerdown', closeFromOutside);
    document.addEventListener('atlas-info-open', closeForPeer);
    return () => {
      document.removeEventListener('pointerdown', closeFromOutside);
      document.removeEventListener('atlas-info-open', closeForPeer);
    };
  }, [id]);

  const show = () => {
    setOpen(true);
    document.dispatchEvent(new CustomEvent('atlas-info-open', { detail: id }));
  };

  return (
    <span
      className="atlas-info-tip"
      data-open={open ? 'true' : 'false'}
      ref={container}
      onFocusCapture={show}
      onBlurCapture={(event) => {
        if (
          !pinned &&
          !event.currentTarget.contains(event.relatedTarget as Node | null)
        )
          setOpen(false);
      }}
      onMouseEnter={show}
      onMouseLeave={() => {
        if (!pinned) setOpen(false);
      }}
      onKeyDown={(event) => {
        if (event.key !== 'Escape') return;
        event.stopPropagation();
        setOpen(false);
        setPinned(false);
        trigger.current?.focus();
      }}
    >
      <button
        type="button"
        className="atlas-info-tip__trigger"
        aria-label={`About ${label}`}
        aria-describedby={id}
        aria-expanded={open}
        ref={trigger}
        onClick={(event) => {
          event.stopPropagation();
          const next = !pinned;
          setPinned(next);
          setOpen(next);
          if (next)
            document.dispatchEvent(
              new CustomEvent('atlas-info-open', { detail: id }),
            );
        }}
      >
        i
      </button>
      <span
        className="atlas-info-tip__content"
        hidden={!open}
        id={id}
        role="tooltip"
      >
        {children}
      </span>
    </span>
  );
}
