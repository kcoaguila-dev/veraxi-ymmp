import { describe, it, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { apiUrl, getApiBaseUrl, initApiBaseUrl, isTauriRuntime, setApiBaseUrl } from './api.ts';

describe('api URL resolution', () => {
  const originalWindow = (globalThis as any).window;

  beforeEach(() => {
    setApiBaseUrl('');
  });

  afterEach(() => {
    setApiBaseUrl('');
    if (originalWindow === undefined) {
      delete (globalThis as any).window;
    } else {
      (globalThis as any).window = originalWindow;
    }
  });

  it('uses relative paths in browser / Vite dev mode', async () => {
    delete (globalThis as any).window;
    assert.strictEqual(isTauriRuntime(), false);
    assert.strictEqual(await initApiBaseUrl(), '');
    assert.strictEqual(apiUrl('/api/projects'), '/api/projects');
    assert.strictEqual(apiUrl('api/health'), '/api/health');
  });

  it('prefixes cached base URL when set and preserves absolute URLs', () => {
    setApiBaseUrl('http://127.0.0.1:54321/');
    assert.strictEqual(getApiBaseUrl(), 'http://127.0.0.1:54321');
    assert.strictEqual(apiUrl('/api/projects/demo/media/qa_test.mp4'), 'http://127.0.0.1:54321/api/projects/demo/media/qa_test.mp4');
    assert.strictEqual(apiUrl('https://example.com/a.png'), 'https://example.com/a.png');
  });

  it('resolves base URL via __TAURI_INTERNALS__.invoke when in Tauri runtime', async () => {
    let calledCmd = '';
    (globalThis as any).window = {
      __TAURI_INTERNALS__: {
        invoke: async (cmd: string) => {
          calledCmd = cmd;
          return 'http://127.0.0.1:61234';
        },
      },
    };
    assert.strictEqual(isTauriRuntime(), true);
    const base = await initApiBaseUrl();
    assert.strictEqual(calledCmd, 'get_api_base_url');
    assert.strictEqual(base, 'http://127.0.0.1:61234');
    assert.strictEqual(apiUrl('/api/health'), 'http://127.0.0.1:61234/api/health');
  });
});
