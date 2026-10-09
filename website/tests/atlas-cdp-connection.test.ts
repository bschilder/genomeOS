/** Unit tests for the flattened CDP client (fast-load design §B.1). */
import { describe, expect, it } from 'vitest';

import { CdpConnection, type CdpSocket } from './support/cdp-connection';

class FakeSocket implements CdpSocket {
  sent: Record<string, unknown>[] = [];
  #message: ((data: string) => void) | undefined;
  #close: (() => void) | undefined;
  send(data: string): void {
    this.sent.push(JSON.parse(data) as Record<string, unknown>);
  }
  close(): void {
    this.#close?.();
  }
  onMessage(listener: (data: string) => void): void {
    this.#message = listener;
  }
  onClose(listener: () => void): void {
    this.#close = listener;
  }
  deliver(message: object): void {
    this.#message?.(JSON.stringify(message));
  }
}

/** A real WebSocket reports `close` later, after `close()` has returned. */
class SlowClosingSocket extends FakeSocket {
  override close(): void {}
}

/** `WebSocket.send` throws, for example, while the socket is still CONNECTING. */
class RefusingSocket extends FakeSocket {
  override send(): void {
    throw new Error('InvalidStateError: still CONNECTING');
  }
}

describe('CdpConnection', () => {
  it('numbers commands, routes session ids and resolves results', async () => {
    const socket = new FakeSocket();
    const cdp = new CdpConnection(socket);
    const browserLevel = cdp.send('Target.getTargets');
    const sessionLevel = cdp.send(
      'Emulation.setCPUThrottlingRate',
      { rate: 4 },
      'worker-1',
    );
    expect(socket.sent).toEqual([
      { id: 1, method: 'Target.getTargets', params: {} },
      {
        id: 2,
        method: 'Emulation.setCPUThrottlingRate',
        params: { rate: 4 },
        sessionId: 'worker-1',
      },
    ]);
    socket.deliver({ id: 2, result: {} });
    socket.deliver({ id: 1, result: { targetInfos: [] } });
    await expect(browserLevel).resolves.toEqual({ targetInfos: [] });
    await expect(sessionLevel).resolves.toEqual({});
  });

  it('rejects a CDP error with the method name', async () => {
    const socket = new FakeSocket();
    const cdp = new CdpConnection(socket);
    const refused = cdp.send(
      'Emulation.setCPUThrottlingRate',
      { rate: 4 },
      'worker-1',
    );
    socket.deliver({
      id: 1,
      error: { message: 'Operation is only supported for pages, not workers' },
    });
    await expect(refused).rejects.toThrow(
      'Emulation.setCPUThrottlingRate: Operation is only supported for pages, not workers',
    );
  });

  it('dispatches events with their session id until unsubscribed', () => {
    const socket = new FakeSocket();
    const cdp = new CdpConnection(socket);
    const seen: [unknown, string | undefined][] = [];
    const off = cdp.on('Target.attachedToTarget', (params, sessionId) =>
      seen.push([params, sessionId]),
    );
    socket.deliver({
      method: 'Target.attachedToTarget',
      params: { sessionId: 'w' },
      sessionId: 'page',
    });
    off();
    socket.deliver({
      method: 'Target.attachedToTarget',
      params: { sessionId: 'x' },
      sessionId: 'page',
    });
    expect(seen).toEqual([[{ sessionId: 'w' }, 'page']]);
  });

  it('rejects pending commands when the socket closes', async () => {
    const socket = new FakeSocket();
    const cdp = new CdpConnection(socket);
    const pending = cdp.send('Network.enable');
    cdp.close();
    await expect(pending).rejects.toThrow('CDP socket closed');
  });

  it('keeps the CDP error data and the raw error', async () => {
    const socket = new FakeSocket();
    const cdp = new CdpConnection(socket);
    const invalid = cdp.send('Target.attachToTarget', {});
    const structured = cdp.send('Runtime.evaluate', {}, 'page');
    const invalidError = {
      code: -32602,
      message: 'Invalid parameters',
      data: 'Failed to deserialize params.targetId',
    };
    socket.deliver({ id: 1, error: invalidError });
    socket.deliver({
      id: 2,
      error: { code: -32000, message: 'Refused', data: { reason: 'busy' } },
    });
    await expect(invalid).rejects.toThrow(
      'Target.attachToTarget: Invalid parameters (Failed to deserialize params.targetId)',
    );
    await expect(invalid).rejects.toMatchObject({ cause: invalidError });
    await expect(structured).rejects.toThrow(
      'Runtime.evaluate: Refused ({"reason":"busy"})',
    );
  });

  it('rejects pending and later commands as soon as close() is called', async () => {
    const socket = new SlowClosingSocket();
    const cdp = new CdpConnection(socket);
    const pending = cdp.send('Network.enable');
    cdp.close();
    await expect(pending).rejects.toThrow('Network.enable: CDP socket closed');
    await expect(cdp.send('Target.getTargets')).rejects.toThrow(
      'Target.getTargets: CDP socket closed',
    );
    expect(socket.sent.map((message) => message.method)).toEqual([
      'Network.enable',
    ]);
  });

  it('rejects commands sent after the browser closed the socket', async () => {
    const socket = new FakeSocket();
    const cdp = new CdpConnection(socket);
    socket.close();
    await expect(cdp.send('Target.getTargets')).rejects.toThrow(
      'Target.getTargets: CDP socket closed',
    );
    expect(socket.sent).toEqual([]);
  });

  it('rejects in-flight commands of a session when it detaches', async () => {
    const socket = new FakeSocket();
    const cdp = new CdpConnection(socket);
    const detached: unknown[] = [];
    cdp.on('Target.detachedFromTarget', (params) => detached.push(params));
    const worker = cdp.send('Runtime.runIfWaitingForDebugger', {}, 'worker-1');
    const page = cdp.send('Network.enable', {}, 'page');
    const browser = cdp.send('Target.getTargets');
    socket.deliver({
      method: 'Target.detachedFromTarget',
      params: { sessionId: 'worker-1', targetId: 'w1' },
      sessionId: 'page',
    });
    await expect(worker).rejects.toThrow(
      'Runtime.runIfWaitingForDebugger: CDP session worker-1 detached',
    );
    expect(detached).toEqual([{ sessionId: 'worker-1', targetId: 'w1' }]);
    socket.deliver({ id: 2, result: {} });
    socket.deliver({ id: 3, result: { targetInfos: [] } });
    await expect(page).resolves.toEqual({});
    await expect(browser).resolves.toEqual({ targetInfos: [] });
  });

  it('rejects in-flight commands of child sessions when their parent detaches', async () => {
    const socket = new FakeSocket();
    const cdp = new CdpConnection(socket);
    socket.deliver({
      method: 'Target.attachedToTarget',
      params: {
        sessionId: 'worker-1',
        targetInfo: { type: 'worker' },
        waitingForDebugger: true,
      },
      sessionId: 'page',
    });
    socket.deliver({
      method: 'Target.attachedToTarget',
      params: { sessionId: 'nested', targetInfo: { type: 'worker' } },
      sessionId: 'worker-1',
    });
    const worker = cdp.send(
      'Emulation.setCPUThrottlingRate',
      { rate: 4 },
      'worker-1',
    );
    const nested = cdp.send('Runtime.runIfWaitingForDebugger', {}, 'nested');
    const other = cdp.send('Network.enable', {}, 'other-page');
    socket.deliver({
      method: 'Target.detachedFromTarget',
      params: { sessionId: 'page' },
    });
    await expect(worker).rejects.toThrow(
      'Emulation.setCPUThrottlingRate: CDP session worker-1 detached',
    );
    await expect(nested).rejects.toThrow(
      'Runtime.runIfWaitingForDebugger: CDP session nested detached',
    );
    socket.deliver({ id: 3, result: {} });
    await expect(other).resolves.toEqual({});
  });

  it('rejects with the method name when the socket refuses a write', async () => {
    const socket = new RefusingSocket();
    const cdp = new CdpConnection(socket);
    const refused = cdp.send('Network.enable');
    await expect(refused).rejects.toThrow(
      'Network.enable: InvalidStateError: still CONNECTING',
    );
    await expect(refused).rejects.toMatchObject({
      cause: new Error('InvalidStateError: still CONNECTING'),
    });
  });
});
