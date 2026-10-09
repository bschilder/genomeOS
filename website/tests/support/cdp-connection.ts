/**
 * Minimal flattened Chrome DevTools Protocol client (fast-load design §B.1).
 *
 * Playwright's CDPSession cannot address the child sessions that
 * `Target.setAutoAttach {flatten: true}` creates for dedicated workers, so the
 * cold-load spec talks to the browser endpoint directly.
 */
export interface CdpSocket {
  send(data: string): void;
  close(): void;
  onMessage(listener: (data: string) => void): void;
  onClose(listener: () => void): void;
}

export type CdpEventListener = (
  params: Record<string, unknown>,
  sessionId: string | undefined,
) => void;

interface CdpMessage {
  id?: number;
  method?: string;
  params?: Record<string, unknown>;
  result?: unknown;
  error?: { message: string };
  sessionId?: string;
}

interface PendingCommand {
  method: string;
  resolve: (value: unknown) => void;
  reject: (error: Error) => void;
}

export class CdpConnection {
  readonly #socket: CdpSocket;
  readonly #pending = new Map<number, PendingCommand>();
  readonly #listeners = new Map<string, Set<CdpEventListener>>();
  #nextId = 1;

  constructor(socket: CdpSocket) {
    this.#socket = socket;
    socket.onMessage((data) => this.#receive(data));
    socket.onClose(() => this.#rejectAll(new Error('CDP socket closed')));
  }

  static async open(url: string): Promise<CdpConnection> {
    const socket = new WebSocket(url);
    await new Promise<void>((resolve, reject) => {
      socket.addEventListener('open', () => resolve(), { once: true });
      socket.addEventListener(
        'error',
        () => reject(new Error(`Could not open the CDP socket ${url}`)),
        { once: true },
      );
    });
    return new CdpConnection({
      send: (data) => socket.send(data),
      close: () => socket.close(),
      onMessage: (listener) =>
        socket.addEventListener('message', (event) =>
          listener(String(event.data)),
        ),
      onClose: (listener) => socket.addEventListener('close', () => listener()),
    });
  }

  send<T = Record<string, unknown>>(
    method: string,
    params: Record<string, unknown> = {},
    sessionId?: string,
  ): Promise<T> {
    const id = this.#nextId;
    this.#nextId += 1;
    const message: CdpMessage =
      sessionId === undefined
        ? { id, method, params }
        : { id, method, params, sessionId };
    return new Promise<T>((resolve, reject) => {
      this.#pending.set(id, {
        method,
        resolve: (value) => resolve(value as T),
        reject,
      });
      this.#socket.send(JSON.stringify(message));
    });
  }

  on(method: string, listener: CdpEventListener): () => void {
    const listeners =
      this.#listeners.get(method) ?? new Set<CdpEventListener>();
    this.#listeners.set(method, listeners);
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  }

  close(): void {
    this.#socket.close();
  }

  #receive(raw: string): void {
    const message = JSON.parse(raw) as CdpMessage;
    if (message.id !== undefined) {
      const pending = this.#pending.get(message.id);
      if (pending === undefined) return;
      this.#pending.delete(message.id);
      if (message.error)
        pending.reject(
          new Error(`${pending.method}: ${message.error.message}`),
        );
      else pending.resolve(message.result ?? {});
      return;
    }
    if (message.method === undefined) return;
    for (const listener of this.#listeners.get(message.method) ?? [])
      listener(message.params ?? {}, message.sessionId);
  }

  #rejectAll(error: Error): void {
    for (const pending of this.#pending.values()) pending.reject(error);
    this.#pending.clear();
  }
}

/** The browser-level DevTools WebSocket for a Chrome started with --remote-debugging-port. */
export async function browserWebSocketUrl(port: number): Promise<string> {
  const response = await fetch(`http://127.0.0.1:${port}/json/version`);
  if (!response.ok)
    throw new Error(
      `The DevTools endpoint on port ${port} returned HTTP ${response.status}.`,
    );
  const body = (await response.json()) as { webSocketDebuggerUrl?: string };
  if (!body.webSocketDebuggerUrl)
    throw new Error(
      'The DevTools endpoint did not report webSocketDebuggerUrl.',
    );
  return body.webSocketDebuggerUrl;
}
