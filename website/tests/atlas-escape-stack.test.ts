import { describe, expect, it, vi } from 'vitest';

import {
  ESCAPE_LAYER_ORDER,
  createEscapeStack,
  handleEscapeKey,
} from '../src/components/atlas/escape-stack';

function escapeEvent(
  overrides: {
    defaultPrevented?: boolean;
    isComposing?: boolean;
    key?: string;
  } = {},
) {
  return {
    defaultPrevented: false,
    isComposing: false,
    key: 'Escape',
    preventDefault: vi.fn(),
    stopPropagation: vi.fn(),
    ...overrides,
  };
}

describe('explorer Escape stack (mobile sheets design §A.1.9)', () => {
  it('orders layers innermost first', () => {
    expect(ESCAPE_LAYER_ORDER).toEqual([
      'popover',
      'dialog',
      'external',
      'inspector',
      'sheet',
    ]);
  });

  it('closes one layer per Escape, innermost first, whatever the registration order', () => {
    const stack = createEscapeStack();
    const closed: string[] = [];
    for (const order of [
      'sheet',
      'inspector',
      'popover',
      'external',
      'dialog',
    ] as const) {
      stack.register(order, () => closed.push(order));
    }
    while (stack.closeTop());
    expect(closed).toEqual([
      'popover',
      'dialog',
      'external',
      'inspector',
      'sheet',
    ]);
    expect(stack.size()).toBe(0);
  });

  it('closes the most recently opened of two layers with the same order', () => {
    const stack = createEscapeStack();
    const closed: string[] = [];
    stack.register('popover', () => closed.push('first tip'));
    stack.register('popover', () => closed.push('second tip'));
    stack.closeTop();
    expect(closed).toEqual(['second tip']);
  });

  it('forgets an unregistered layer', () => {
    const stack = createEscapeStack();
    const close = vi.fn();
    const unregister = stack.register('inspector', close);
    unregister();
    expect(stack.closeTop()).toBe(false);
    expect(close).not.toHaveBeenCalled();
  });

  it('prevents and stops only the Escape that closed a layer', () => {
    const stack = createEscapeStack();
    const close = vi.fn();
    stack.register('dialog', close);
    const enter = escapeEvent({ key: 'Enter' });
    expect(handleEscapeKey(stack, enter)).toBe(false);
    expect(enter.preventDefault).not.toHaveBeenCalled();
    expect(handleEscapeKey(stack, escapeEvent({ isComposing: true }))).toBe(
      false,
    );
    expect(
      handleEscapeKey(stack, escapeEvent({ defaultPrevented: true })),
    ).toBe(false);
    const escape = escapeEvent();
    expect(handleEscapeKey(stack, escape)).toBe(true);
    expect(close).toHaveBeenCalledTimes(1);
    expect(escape.preventDefault).toHaveBeenCalledTimes(1);
    expect(escape.stopPropagation).toHaveBeenCalledTimes(1);
    const empty = escapeEvent();
    expect(handleEscapeKey(stack, empty)).toBe(false);
    expect(empty.preventDefault).not.toHaveBeenCalled();
  });
});
