import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  carryFocus,
  focusCarryPending,
} from '../src/components/atlas/useFocusCarry';

describe('focus carry across the 52rem switch (mobile sheets design §A.1.6)', () => {
  afterEach(() => {
    vi.runOnlyPendingTimers();
    vi.useRealTimers();
  });

  it('keeps a record only until the next task', () => {
    vi.useFakeTimers();
    expect(focusCarryPending()).toBe(false);
    carryFocus('catalog');
    expect(focusCarryPending()).toBe(true);
    vi.advanceTimersByTime(0);
    expect(focusCarryPending()).toBe(false);
  });
});
