/** Local `.gosa` transport for the test and performance servers (fast-load design §B.9). */
import { spawn, type ChildProcess } from 'node:child_process';
import { once } from 'node:events';
import {
  copyFileSync,
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from 'node:fs';
import { createServer } from 'node:net';
import os from 'node:os';
import path from 'node:path';

import { afterAll, beforeAll, describe, expect, it } from 'vitest';

const websiteRoot = path.resolve(import.meta.dirname, '..');

async function freePort(): Promise<number> {
  const probe = createServer();
  probe.listen(0, '127.0.0.1');
  await once(probe, 'listening');
  const address = probe.address();
  probe.close();
  await once(probe, 'close');
  if (address === null || typeof address === 'string')
    throw new Error('No TCP port was assigned.');
  return address.port;
}

async function waitForServer(url: string): Promise<void> {
  const deadline = Date.now() + 15_000;
  while (Date.now() < deadline) {
    try {
      if ((await fetch(url)).ok) return;
    } catch {
      // not listening yet
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error(`Timed out waiting for ${url}`);
}

describe('local .gosa serving', () => {
  const root = mkdtempSync(path.join(os.tmpdir(), 'atlas-serve-'));
  let server: ChildProcess | undefined;
  let origin = '';

  beforeAll(async () => {
    mkdirSync(path.join(root, 'site', 'grids'), { recursive: true });
    writeFileSync(
      path.join(root, 'site', 'grids', 'probe.gosa'),
      Buffer.alloc(65_536),
    );
    copyFileSync(
      path.join(websiteRoot, 'serve.json'),
      path.join(root, 'serve.json'),
    );
    const port = await freePort();
    origin = `http://127.0.0.1:${port}`;
    server = spawn(
      process.execPath,
      [
        path.join(websiteRoot, 'node_modules', 'serve', 'build', 'main.js'),
        'site',
        '-c',
        '../serve.json',
        '-l',
        `tcp://127.0.0.1:${port}`,
        '--no-clipboard',
      ],
      { cwd: root, stdio: 'ignore' },
    );
    await waitForServer(`${origin}/grids/probe.gosa`);
  });

  afterAll(async () => {
    if (server && server.exitCode === null) {
      server.kill('SIGTERM');
      await once(server, 'exit');
    }
    rmSync(root, { force: true, recursive: true });
  });

  it('sends .gosa as compressed application/octet-stream', async () => {
    const response = await fetch(`${origin}/grids/probe.gosa`, {
      headers: { 'Accept-Encoding': 'gzip, deflate' },
    });
    expect(response.status).toBe(200);
    expect(response.headers.get('content-type')).toBe(
      'application/octet-stream',
    );
    expect(['gzip', 'br']).toContain(response.headers.get('content-encoding'));
    expect((await response.arrayBuffer()).byteLength).toBe(65_536);
  });

  it('serves the test build with the rule and never deploys it', () => {
    const scripts = (
      JSON.parse(
        readFileSync(path.join(websiteRoot, 'package.json'), 'utf8'),
      ) as { scripts: Record<string, string> }
    ).scripts;
    expect(scripts['serve:test']).toBe(
      'serve dist -c ../serve.json -l tcp://127.0.0.1:${PLAYWRIGHT_PORT:-4322} --no-clipboard',
    );
    expect(existsSync(path.join(websiteRoot, 'public', 'serve.json'))).toBe(
      false,
    );
    expect(existsSync(path.join(websiteRoot, 'dist', 'serve.json'))).toBe(
      false,
    );
  });
});
