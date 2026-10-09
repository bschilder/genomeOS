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
});
