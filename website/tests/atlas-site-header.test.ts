import { describe, expect, it } from 'vitest';

import {
  PICKER_GUTTER_PX,
  clampPickerTop,
  siteHeaderBottom,
} from '../src/components/atlas/site-header';

function rootWithHeader(bottom: number | null): ParentNode {
  return {
    querySelector: (selector: string) =>
      selector === '[data-site-header]' && bottom !== null
        ? { getBoundingClientRect: () => ({ bottom }) }
        : null,
  } as unknown as ParentNode;
}

describe('Atlas pickers open below the site header (mobile sheets design §A.1.2)', () => {
  it('reads the bottom edge of the data-site-header element', () => {
    expect(siteHeaderBottom(rootWithHeader(86.5))).toBe(86.5);
    expect(siteHeaderBottom(rootWithHeader(null))).toBe(0);
  });

  it('keeps the catalog between an 8 px gutter and 18 px below the header', () => {
    expect(PICKER_GUTTER_PX).toBe(8);
    expect(clampPickerTop(500, 86.5, 18)).toBe(104.5);
    expect(clampPickerTop(50, 86.5, 18)).toBe(94.5);
    expect(clampPickerTop(100, 86.5, 18)).toBe(100);
  });

  it('keeps the earth gallery between the gutter and 10 px below the header', () => {
    expect(clampPickerTop(500, 86.5, 10)).toBe(96.5);
    expect(clampPickerTop(90, 86.5, 10)).toBe(94.5);
  });

  it('follows a taller header instead of a fixed pixel offset', () => {
    expect(clampPickerTop(500, 140, 18)).toBe(158);
  });
});
