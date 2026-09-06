/** Bounded render-layer reuse for Atlas design §11. */

export class LayerCache<T> {
  readonly #entries = new Map<string, T>();

  constructor(readonly maximumSize: number) {
    if (!Number.isInteger(maximumSize) || maximumSize < 1) {
      throw new Error('Layer cache size must be a positive integer.');
    }
  }

  get(key: string): T | undefined {
    const value = this.#entries.get(key);
    if (value === undefined) return undefined;
    this.#entries.delete(key);
    this.#entries.set(key, value);
    return value;
  }

  set(key: string, value: T): void {
    this.#entries.delete(key);
    this.#entries.set(key, value);
  }

  prune(active: T, dispose: (value: T) => void): void {
    for (const [key, value] of this.#entries) {
      if (this.#entries.size <= this.maximumSize) return;
      if (value === active) continue;
      this.#entries.delete(key);
      dispose(value);
    }
  }
}
