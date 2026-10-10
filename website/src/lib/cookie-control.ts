/**
 * The cookie control (#422; consent model refined by the owner on 2026-10-10): a small collapsed
 * cookie icon on every page that expands into a panel with the visitor's analytics setting.
 *
 * - Everyone sees the panel's on/off switch for analytics cookies, showing the current state
 *   (`resolveConsent`): their choice, Global Privacy Control, the opt-in default of an EEA, UK or
 *   Swiss time zone, or the opt-out default elsewhere.
 * - An undecided visitor in an opt-in time zone sees Accept and Decline instead, and the panel opens
 *   by itself on the first page of a visit, without taking focus.
 * - Every `[data-cookie-settings]` control opens the same panel: the footer's Cookie settings link
 *   and, on /app/, the icon docked in the Atlas (`[data-cookie-dock]`, AtlasCookieSettings.tsx),
 *   which stands in for the corner icon there.
 * - Escape, a pointer press outside and Tab out of the panel collapse it, as the site's other
 *   popovers do. Escape and a choice hand focus back to the control that opened the panel.
 */

import {
  applyConsentChoice,
  browserTimeZone,
  clearAnalyticsCookies,
  readConsentChoice,
  readPromptDismissed,
  resolveConsent,
  sendsGlobalPrivacyControl,
  shouldPromptOnLoad,
  writeConsentChoice,
  writePromptDismissed,
  type ConsentChoice,
  type ConsentState,
} from './consent';
import { panelPlacement } from './cookie-panel-placement';

/** Controls elsewhere on the page that open the panel. */
const TRIGGER = '[data-cookie-settings]';
/** The Atlas's docked icon, which takes the corner icon's place on /app/. */
const DOCK = '[data-cookie-dock]';

function storageOrNull(
  view: Window,
  kind: 'localStorage' | 'sessionStorage',
): Storage | null {
  try {
    return view[kind];
  } catch {
    return null;
  }
}

function isShown(element: Element | null | undefined): element is HTMLElement {
  return (
    element instanceof HTMLElement &&
    element.isConnected &&
    element.getClientRects().length > 0
  );
}

export function initCookieControl(doc: Document = document): void {
  const root = doc.querySelector<HTMLElement>('[data-cookie-control]');
  const toggle = root?.querySelector<HTMLElement>('[data-cookie-toggle]');
  const panel = root?.querySelector<HTMLElement>('[data-cookie-panel]');
  const prompt = panel?.querySelector<HTMLElement>('[data-cookie-prompt]');
  const setting = panel?.querySelector<HTMLElement>('[data-cookie-setting]');
  const analyticsSwitch = panel?.querySelector<HTMLElement>(
    '[data-cookie-switch]',
  );
  const switchState = panel?.querySelector<HTMLElement>(
    '[data-cookie-switch-state]',
  );
  const gpcNote = panel?.querySelector<HTMLElement>('[data-cookie-gpc]');
  const view = doc.defaultView;
  if (
    !root ||
    !toggle ||
    !panel ||
    !prompt ||
    !setting ||
    !analyticsSwitch ||
    !switchState ||
    !gpcNote ||
    !view
  )
    return;
  // Starlight renders it inside its content frame, a stacking context under the docs sidebars; as
  // a child of <body> it sits above every page's own layers.
  if (root.parentElement !== doc.body) doc.body.append(root);

  const local = storageOrNull(view, 'localStorage');
  const session = storageOrNull(view, 'sessionStorage');
  let state: ConsentState = resolveConsent({
    choice: readConsentChoice(local),
    gpc: sendsGlobalPrivacyControl(view.navigator),
    timeZone: browserTimeZone(),
  });
  let opener: HTMLElement | null = null;
  let frame = 0;
  let placed = '';

  const render = () => {
    const prompting = state.source === 'opt-in-region';
    prompt.hidden = !prompting;
    setting.hidden = prompting;
    const on = state.analytics === 'granted';
    analyticsSwitch.setAttribute('aria-checked', String(on));
    switchState.textContent = on ? 'On' : 'Off';
    gpcNote.hidden = state.source !== 'gpc';
    root.dataset.consent = state.analytics;
  };

  const setExpanded = (open: boolean) => {
    for (const control of [toggle, ...doc.querySelectorAll(TRIGGER)])
      if (control.hasAttribute('aria-controls'))
        control.setAttribute('aria-expanded', String(open));
  };

  /** The icon the panel opens beside: the docked one that opened it, else whichever is shown. */
  const anchor = (): HTMLElement | null => {
    if (opener?.matches(DOCK) && isShown(opener)) return opener;
    if (isShown(toggle)) return toggle;
    for (const dock of doc.querySelectorAll(DOCK))
      if (isShown(dock)) return dock;
    return null;
  };

  const place = () => {
    const icon = anchor();
    if (!icon) {
      if (placed !== 'corner') {
        panel.removeAttribute('style');
        panel.dataset.placement = 'corner';
        placed = 'corner';
      }
      return;
    }
    const header = doc
      .querySelector('[data-site-header]')
      ?.getBoundingClientRect();
    const placement = panelPlacement({
      anchor: icon.getBoundingClientRect(),
      panel: { width: panel.offsetWidth, height: panel.scrollHeight },
      viewport: {
        width: doc.documentElement.clientWidth,
        height: view.innerHeight,
      },
      headerBottom: header ? Math.max(0, header.bottom) : 0,
    });
    const key = JSON.stringify(placement);
    if (key === placed) return;
    placed = key;
    panel.dataset.placement = placement.side;
    panel.style.right = `${placement.right}px`;
    panel.style.top =
      placement.side === 'below' ? `${placement.offset}px` : 'auto';
    panel.style.bottom =
      placement.side === 'above' ? `${placement.offset}px` : 'auto';
    panel.style.maxHeight = `${placement.maxHeight}px`;
  };

  // While open, the panel follows its icon: the phone Atlas's credit row moves with the sheet.
  const follow = () => {
    frame = 0;
    if (panel.hidden) return;
    place();
    frame = view.requestAnimationFrame(follow);
  };

  const open = (from: HTMLElement | null, focus: boolean) => {
    opener = from;
    render();
    panel.hidden = false;
    root.dataset.open = '';
    setExpanded(true);
    placed = '';
    place();
    if (!frame) frame = view.requestAnimationFrame(follow);
    if (focus) panel.focus({ preventScroll: true });
  };

  const close = (restoreFocus: boolean) => {
    if (panel.hidden) return;
    const hadFocus = panel.contains(doc.activeElement);
    panel.hidden = true;
    delete root.dataset.open;
    setExpanded(false);
    if (frame) view.cancelAnimationFrame(frame);
    frame = 0;
    // Closing the opt-in prompt without a choice keeps it collapsed for the rest of the visit.
    if (state.source === 'opt-in-region') writePromptDismissed(session);
    if (restoreFocus && hadFocus) {
      const back = isShown(opener) ? opener : anchor();
      back?.focus({ preventScroll: true });
    }
    opener = null;
  };

  const choose = (choice: ConsentChoice) => {
    writeConsentChoice(local, choice);
    applyConsentChoice(choice);
    if (choice === 'denied') clearAnalyticsCookies(doc);
    state = { analytics: choice, source: 'choice' };
    render();
  };

  // The corner icon is a disclosure: the panel follows it in the tab order, so focus stays put.
  toggle.addEventListener('click', () => {
    if (panel.hidden) open(toggle, false);
    else close(true);
  });

  // Controls elsewhere move focus into the panel, and back on Escape.
  doc.addEventListener('click', (event) => {
    const control =
      event.target instanceof Element
        ? event.target.closest<HTMLElement>(TRIGGER)
        : null;
    if (!control) return;
    event.preventDefault();
    if (!panel.hidden && opener === control) close(true);
    else open(control, true);
  });

  panel.addEventListener('click', (event) => {
    const target = event.target instanceof Element ? event.target : null;
    const answer = target?.closest<HTMLElement>('[data-consent-choice]');
    if (answer) {
      choose(answer.dataset.consentChoice === 'granted' ? 'granted' : 'denied');
      close(true);
      return;
    }
    if (target?.closest('[data-cookie-switch]'))
      choose(state.analytics === 'granted' ? 'denied' : 'granted');
  });

  // Capture on the window, ahead of the Atlas's document-level Escape stack: while the panel is
  // open it is the top layer, and this Escape belongs to it alone.
  view.addEventListener(
    'keydown',
    (event) => {
      if (event.key !== 'Escape' || event.isComposing || panel.hidden) return;
      event.preventDefault();
      event.stopPropagation();
      close(true);
    },
    true,
  );

  const inControl = (node: EventTarget | null) =>
    node instanceof Node &&
    (root.contains(node) ||
      (node instanceof Element && node.closest(TRIGGER) !== null));

  doc.addEventListener(
    'pointerdown',
    (event) => {
      if (!panel.hidden && !inControl(event.target)) close(false);
    },
    true,
  );

  panel.addEventListener('focusout', (event) => {
    const next = event.relatedTarget;
    if (next instanceof Node && !inControl(next)) close(false);
  });

  render();
  if (shouldPromptOnLoad(state, readPromptDismissed(session)))
    open(null, false);
}
