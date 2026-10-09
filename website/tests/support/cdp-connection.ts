/**
 * Minimal flattened Chrome DevTools Protocol client (fast-load design §B.1).
 *
 * Playwright's CDPSession cannot address the child sessions that
 * `Target.setAutoAttach {flatten: true}` creates for dedicated workers, so the
 * cold-load spec talks to the browser endpoint directly.
 *
 * Every command settles. It resolves with its result, or it rejects with
 * `<method>: <reason>` when the browser returns an error (message plus data,
 * with the raw error as `cause`), when its session or an ancestor session
 * detaches, when the socket closes or has closed, or when the socket refuses
 * the write.
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

/** A CDP error response. `data` names the refused parameter or state when present. */
interface CdpErrorBody {
  code?: number;
  message: string;
  data?: unknown;
}

interface CdpMessage {
  id?: number;
  method?: string;
  params?: Record<string, unknown>;
  result?: unknown;
  error?: CdpErrorBody;
  sessionId?: string;
}

interface PendingCommand {
  method: string;
  sessionId: string | undefined;
  resolve: (value: unknown) => void;
  reject: (error: Error) => void;
}

export class CdpConnection {
  readonly #socket: CdpSocket;
  readonly #pending = new Map<number, PendingCommand>();
  readonly #listeners = new Map<string, Set<CdpEventListener>>();
  /** Each auto-attached session's parent session (undefined: the browser). */
  readonly #parents = new Map<string, string | undefined>();
  #nextId = 1;
  #closed = false;

  constructor(socket: CdpSocket) {
    this.#socket = socket;
    socket.onMessage((data) => this.#receive(data));
    socket.onClose(() => this.#markClosed());
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
    // A WebSocket drops writes once closing, so nothing would ever answer.
    if (this.#closed)
      return Promise.reject(new Error(`${method}: CDP socket closed`));
    const id = this.#nextId;
    this.#nextId += 1;
    const message: CdpMessage =
      sessionId === undefined
        ? { id, method, params }
        : { id, method, params, sessionId };
    return new Promise<T>((resolve, reject) => {
      this.#pending.set(id, {
        method,
        sessionId,
        resolve: (value) => resolve(value as T),
        reject,
      });
      try {
        this.#socket.send(JSON.stringify(message));
      } catch (error) {
        this.#pending.delete(id);
        const reason = error instanceof Error ? error.message : String(error);
        reject(new Error(`${method}: ${reason}`, { cause: error }));
      }
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

  /** Rejects every pending command now; a WebSocket reports `close` only later. */
  close(): void {
    this.#markClosed();
    this.#socket.close();
  }

  #receive(raw: string): void {
    const message = JSON.parse(raw) as CdpMessage;
    if (message.id !== undefined) {
      const pending = this.#pending.get(message.id);
      if (pending === undefined) return;
      this.#pending.delete(message.id);
      if (message.error)
        pending.reject(protocolError(pending.method, message.error));
      else pending.resolve(message.result ?? {});
      return;
    }
    if (message.method === undefined) return;
    const params = message.params ?? {};
    if (
      message.method === 'Target.attachedToTarget' &&
      typeof params.sessionId === 'string'
    )
      this.#parents.set(params.sessionId, message.sessionId);
    if (
      message.method === 'Target.detachedFromTarget' &&
      typeof params.sessionId === 'string'
    )
      this.#detach(params.sessionId);
    for (const listener of this.#listeners.get(message.method) ?? [])
      listener(params, message.sessionId);
  }

  /**
   * The browser never answers a detached session's in-flight commands, so
   * reject them, and those of every session auto-attached beneath it.
   */
  #detach(sessionId: string): void {
    const detached = new Set([sessionId]);
    // A Set's iterator also visits members added during the loop.
    for (const session of detached)
      for (const [child, parent] of this.#parents)
        if (parent === session) detached.add(child);
    for (const session of detached) this.#parents.delete(session);
    for (const [id, pending] of this.#pending) {
      if (pending.sessionId === undefined || !detached.has(pending.sessionId))
        continue;
      this.#pending.delete(id);
      pending.reject(
        new Error(
          `${pending.method}: CDP session ${pending.sessionId} detached`,
        ),
      );
    }
  }

  #markClosed(): void {
    this.#closed = true;
    for (const pending of this.#pending.values())
      pending.reject(new Error(`${pending.method}: CDP socket closed`));
    this.#pending.clear();
    this.#parents.clear();
  }
}

/** `<method>: <message> (<data>)`, keeping the raw CDP error as `cause`. */
function protocolError(method: string, error: CdpErrorBody): Error {
  const data =
    error.data === undefined
      ? ''
      : ` (${typeof error.data === 'string' ? error.data : JSON.stringify(error.data)})`;
  return new Error(`${method}: ${error.message}${data}`, { cause: error });
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
