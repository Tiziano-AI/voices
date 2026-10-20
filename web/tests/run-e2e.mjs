import { spawn } from 'node:child_process';
import { mkdir, rm } from 'node:fs/promises';
import net from 'node:net';
import path from 'node:path';
import process from 'node:process';

const repoRoot = path.resolve(process.cwd(), '..');
const screenshotDir = path.resolve(process.cwd(), 'storyshots');

async function freePort() {
  return await new Promise((resolve, reject) => {
    const server = net.createServer();
    server.listen(0, '127.0.0.1', () => {
      const address = server.address();
      if (!address || typeof address === 'string') {
        reject(new Error('Unable to resolve a free port.'));
        return;
      }
      server.close((error) => {
        if (error) {
          reject(error);
          return;
        }
        resolve(address.port);
      });
    });
  });
}

async function waitForServer(url) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < 30000) {
    try {
      const response = await fetch(`${url}/api/ui-config`);
      if (response.ok) {
        return;
      }
    } catch {
      // retry
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`Timed out waiting for ${url}`);
}

async function waitForProcessExit(process, label) {
  if (process.exitCode !== null || process.signalCode !== null) {
    return;
  }
  await Promise.race([
    new Promise((resolve) => process.once('exit', resolve)),
    new Promise((_resolve, reject) => {
      setTimeout(() => reject(new Error(`Timed out waiting for ${label} to exit`)), 5000);
    }),
  ]);
}

async function runFixture(fixture, specFile) {
  const port = await freePort();
  const baseUrl = `http://127.0.0.1:${port}`;
  const server = spawn(
    'uv',
    ['run', 'python', 'tests/ui_test_server.py', '--port', String(port), '--fixture', fixture],
    {
      cwd: repoRoot,
      stdio: 'inherit',
      env: process.env,
    },
  );

  try {
    await waitForServer(baseUrl);
    await new Promise((resolve, reject) => {
      const testProcess = spawn('pnpm', ['exec', 'playwright', 'test', specFile], {
        cwd: process.cwd(),
        stdio: 'inherit',
        env: {
          ...process.env,
          PLAYWRIGHT_BASE_URL: baseUrl,
          PLAYWRIGHT_SCREENSHOT_DIR: screenshotDir,
        },
      });
      testProcess.on('exit', (code) => {
        if (code === 0) {
          resolve();
          return;
        }
        reject(new Error(`Playwright failed for ${fixture} with code ${code}`));
      });
    });
  } finally {
    const serverExit = waitForProcessExit(server, `test server for ${fixture}`);
    server.kill('SIGTERM');
    await serverExit;
  }
}

await rm(screenshotDir, { recursive: true, force: true });
await mkdir(screenshotDir, { recursive: true });
await runFixture('empty', 'tests/empty-launchpad.spec.ts');
await runFixture('seeded', 'tests/studio.spec.ts');
await runFixture('seeded', 'tests/studio-board.spec.ts');
await runFixture('seeded', 'tests/studio-board-identity.spec.ts');
await runFixture('seeded', 'tests/studio-preview-export.spec.ts');
await runFixture('many', 'tests/studio-board-large.spec.ts');
await runFixture('seeded', 'tests/studio-creation.spec.ts');
await runFixture('seeded', 'tests/studio-record.spec.ts');
await runFixture('seeded', 'tests/studio-record-recovery.spec.ts');
await runFixture('slow-design', 'tests/studio-cancel.spec.ts');
