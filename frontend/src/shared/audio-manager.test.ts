import { test, describe, beforeEach, mock } from 'node:test';
import assert from 'node:assert';
import { AuditionManager } from './audio-manager.ts';
import { api } from './api.ts';

// Polyfill minimal browser globals for testing
class MockAudio {
  public src: string = '';
  public currentTime: number = 0;
  public paused: boolean = true;
  public onended: (() => void) | null = null;
  public onerror: (() => void) | null = null;
  public static instances: MockAudio[] = [];

  constructor(src?: string) {
    if (src) this.src = src;
    MockAudio.instances.push(this);
  }

  play(): Promise<void> {
    this.paused = false;
    return Promise.resolve();
  }

  pause(): void {
    this.paused = true;
  }
}

// Global mocks setup
(globalThis as any).Audio = MockAudio;
(globalThis as any).URL = {
  createObjectURL: (_blob: any) => `blob:mock-url-${Math.random()}`,
  revokeObjectURL: mock.fn(),
};

describe('AuditionManager - Exclusive Playback Tests', () => {
  let manager: AuditionManager;
  let dispatchedEvents: string[] = [];
  let windowEventHandlers: Record<string, Function[]> = {};

  beforeEach(() => {
    MockAudio.instances = [];
    dispatchedEvents = [];
    windowEventHandlers = {};

    (globalThis as any).window = {
      addEventListener: (type: string, handler: Function) => {
        if (!windowEventHandlers[type]) windowEventHandlers[type] = [];
        windowEventHandlers[type].push(handler);
      },
      removeEventListener: (type: string, handler: Function) => {
        if (windowEventHandlers[type]) {
          windowEventHandlers[type] = windowEventHandlers[type].filter(h => h !== handler);
        }
      },
      dispatchEvent: (event: any) => {
        dispatchedEvents.push(event.type);
        if (windowEventHandlers[event.type]) {
          windowEventHandlers[event.type].forEach(h => h(event));
        }
        return true;
      },
    };

    (globalThis as any).CustomEvent = class {
      type: string;
      detail: any;
      constructor(type: string, detail?: any) {
        this.type = type;
        this.detail = detail;
      }
    };

    manager = new AuditionManager();
  });

  test('toggle starts playback for a line and pauses video preview', async () => {
    const mockBlob = new Blob(['test-audio'], { type: 'audio/wav' });
    mock.method(api, 'auditionVoice', async () => mockBlob);

    await manager.toggle(0, 'こんにちは', 'ずんだもん');

    const state = manager.getState();
    assert.strictEqual(state.playingIndex, 0);
    assert.strictEqual(state.isLoading, false);
    assert.strictEqual(MockAudio.instances.length, 1);
    assert.strictEqual(MockAudio.instances[0].paused, false);
    assert.ok(dispatchedEvents.includes('veraxi:pause-preview'));
  });

  test('clicking another line stops the previous audio before starting the new one', async () => {
    const mockBlob = new Blob(['test-audio'], { type: 'audio/wav' });
    mock.method(api, 'auditionVoice', async () => mockBlob);

    // Start line 0
    await manager.toggle(0, 'こんにちはなのだ', 'ずんだもん');
    const firstAudio = MockAudio.instances[0];
    assert.strictEqual(manager.getState().playingIndex, 0);
    assert.strictEqual(firstAudio.paused, false);

    // Click line 1
    await manager.toggle(1, '四国めたんですわ', '四国めたん');
    const secondAudio = MockAudio.instances[1];

    // First audio MUST be paused and cleared
    assert.strictEqual(firstAudio.paused, true);
    assert.strictEqual(firstAudio.src, '');

    // Second audio is the only active audio
    assert.strictEqual(manager.getState().playingIndex, 1);
    assert.strictEqual(secondAudio.paused, false);
  });

  test('clicking the currently playing line toggles it off (stops immediately)', async () => {
    const mockBlob = new Blob(['test-audio'], { type: 'audio/wav' });
    mock.method(api, 'auditionVoice', async () => mockBlob);

    await manager.toggle(2, 'テストなのだ', 'ずんだもん');
    assert.strictEqual(manager.getState().playingIndex, 2);

    // Click line 2 again
    await manager.toggle(2, 'テストなのだ', 'ずんだもん');
    assert.strictEqual(manager.getState().playingIndex, null);
    assert.strictEqual(manager.getState().isLoading, false);
    assert.strictEqual(MockAudio.instances[0].paused, true);
  });

  test('in-flight request cancellation: rapid clicks discard previous synthesis', async () => {
    let resolveFirst: (val: any) => void = () => {};
    let resolveSecond: (val: any) => void = () => {};

    const p1 = new Promise((res) => { resolveFirst = res; });
    const p2 = new Promise((res) => { resolveSecond = res; });

    let callCount = 0;
    mock.method(api, 'auditionVoice', () => {
      callCount++;
      return callCount === 1 ? p1 : p2;
    });

    // User clicks line 0 (slow synthesis in flight)
    const toggle1 = manager.toggle(0, 'Line 0 slow', 'ずんだもん');
    assert.strictEqual(manager.getState().playingIndex, 0);
    assert.strictEqual(manager.getState().isLoading, true);

    // User quickly clicks line 1 before line 0 completes
    const toggle2 = manager.toggle(1, 'Line 1 quick', '四国めたん');
    assert.strictEqual(manager.getState().playingIndex, 1);
    assert.strictEqual(manager.getState().isLoading, true);

    // Now line 0 finally finishes late
    resolveFirst(new Blob(['slow-audio'], { type: 'audio/wav' }));
    await toggle1;

    // Line 0 should NOT have played because session was invalidated!
    assert.strictEqual(MockAudio.instances.length, 0);

    // Now line 1 finishes
    resolveSecond(new Blob(['quick-audio'], { type: 'audio/wav' }));
    await toggle2;

    // Only line 1 plays
    assert.strictEqual(MockAudio.instances.length, 1);
    assert.strictEqual(manager.getState().playingIndex, 1);
    assert.strictEqual(MockAudio.instances[0].paused, false);
  });

  test('stop revokes Object URL and resets all playback state', async () => {
    const mockBlob = new Blob(['test-audio'], { type: 'audio/wav' });
    mock.method(api, 'auditionVoice', async () => mockBlob);

    await manager.toggle(3, 'セリフ', 'ずんだもん');
    assert.strictEqual(manager.getState().playingIndex, 3);

    manager.stop();
    assert.strictEqual(manager.getState().playingIndex, null);
    assert.strictEqual(manager.getState().isLoading, false);
  });

  test('veraxi:stop-audition event stops playback immediately', async () => {
    const mockBlob = new Blob(['test-audio'], { type: 'audio/wav' });
    mock.method(api, 'auditionVoice', async () => mockBlob);

    await manager.toggle(4, '動画プレビューとの連動テスト', 'ずんだもん');
    assert.strictEqual(manager.getState().playingIndex, 4);

    // Simulate video preview starting to play
    (globalThis as any).window.dispatchEvent(new (globalThis as any).CustomEvent('veraxi:stop-audition'));

    assert.strictEqual(manager.getState().playingIndex, null);
    assert.strictEqual(manager.getState().isLoading, false);
    assert.strictEqual(MockAudio.instances[0].paused, true);
  });

  test('audio onended event cleanly resets playing state', async () => {
    const mockBlob = new Blob(['test-audio'], { type: 'audio/wav' });
    mock.method(api, 'auditionVoice', async () => mockBlob);

    await manager.toggle(5, '自然終了テスト', 'ずんだもん');
    assert.strictEqual(manager.getState().playingIndex, 5);

    const activeAudio = MockAudio.instances[0];
    assert.ok(activeAudio.onended);

    // Trigger onended
    activeAudio.onended();

    assert.strictEqual(manager.getState().playingIndex, null);
    assert.strictEqual(manager.getState().isLoading, false);
  });

  test('handles empty or whitespace text gracefully without playing', async () => {
    await manager.toggle(6, '   ', 'ずんだもん');
    assert.strictEqual(manager.getState().playingIndex, null);
    assert.strictEqual(MockAudio.instances.length, 0);
  });

  test('notifies subscribers on state changes', async () => {
    const mockBlob = new Blob(['test-audio'], { type: 'audio/wav' });
    mock.method(api, 'auditionVoice', async () => mockBlob);

    const states: any[] = [];
    const unsubscribe = manager.subscribe((state) => {
      states.push({ ...state });
    });

    await manager.toggle(7, '購読テスト', 'ずんだもん');
    manager.stop();
    unsubscribe();

    assert.ok(states.length >= 3);
    // Final state after stop is playingIndex: null
    assert.strictEqual(states[states.length - 1].playingIndex, null);
  });
});
