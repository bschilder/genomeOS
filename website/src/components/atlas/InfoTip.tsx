/** Keyboard, pointer, and touch-accessible help text for Atlas design §11. */

import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

interface InfoTipProps {
  children: React.ReactNode;
  label: string;
}

export function InfoTip({ children, label }: InfoTipProps) {
  const id = useId();
  const container = useRef<HTMLSpanElement>(null);
  const content = useRef<HTMLSpanElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(false);
  const [pinned, setPinned] = useState(false);
  const [position, setPosition] = useState({ left: 12, top: 12, width: 288 });

  useEffect(() => {
    const closeFromOutside = (event: PointerEvent) => {
      if (
        !container.current?.contains(event.target as Node) &&
        !content.current?.contains(event.target as Node)
      ) {
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

  useLayoutEffect(() => {
    if (!open || !trigger.current || !content.current) return;
    const place = () => {
      if (!trigger.current || !content.current) return;
      const margin = 12;
      const gap = 8;
      const anchor = trigger.current.getBoundingClientRect();
      const width = Math.min(288, window.innerWidth - margin * 2);
      const height = content.current.offsetHeight;
      const left = Math.min(
        Math.max(margin, anchor.left),
        window.innerWidth - width - margin,
      );
      const below = anchor.bottom + gap;
      const top =
        below + height <= window.innerHeight - margin
          ? below
          : Math.max(margin, anchor.top - gap - height);
      setPosition({ left, top, width });
    };
    place();
    window.addEventListener('resize', place);
    document.addEventListener('scroll', place, true);
    return () => {
      window.removeEventListener('resize', place);
      document.removeEventListener('scroll', place, true);
    };
  }, [open]);

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
      {open &&
        createPortal(
          <span
            className="atlas-info-tip__content"
            id={id}
            ref={content}
            role="tooltip"
            style={position}
          >
            {children}
          </span>,
          document.body,
        )}
    </span>
  );
}
