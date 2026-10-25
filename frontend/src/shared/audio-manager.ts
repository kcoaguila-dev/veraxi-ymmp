/**
 * Audio Audition Manager
 *
 * Enforces strict single-audio-source invariant across Veraxi Studio:
 * 1. Only ONE voice audition or video preview may play at any given instant.
 * 2. In-flight synthesis requests are aborted when a new voice is clicked or stopped.
 * 3. Clicking the currently playing or loading voice toggles it OFF (stops immediately).
 * 4. Object URLs are revoked to prevent memory leaks.
 * 5. Coordinates with VideoPreview to pause video playback when auditioning and vice versa.
 */

import { api } from './api.ts';

export interface AuditionState {
  playingIndex: number | null;
  isLoading: boolean;
}

type StateListener = (state: AuditionState) => void;

export class AuditionManager {
  private activeAudio: HTMLAudioElement | null = null;
  private activeUrl: string | null = null;
  private abortController: AbortController | null = null;
  private activeSessionId: number = 0;
  private state: AuditionState = { playingIndex: null, isLoading: false };
  private listeners: Set<StateListener> = new Set();

  constructor() {
    // Listen for events from VideoPreview to stop voice audition if video starts
    if (typeof window !== 'undefined') {
      window.addEventListener('veraxi:stop-audition', () => {
        this.stop();
      });
    }
  }

  public getState(): AuditionState {
    return { ...this.state };
  }

  public subscribe(listener: StateListener): () => void {
    this.listeners.add(listener);
    listener(this.getState());
    return () => {
      this.listeners.delete(listener);
    };
  }

  private notify(): void {
    const currentState = this.getState();
    this.listeners.forEach((fn) => fn(currentState));
  }

  /**
   * Immediately stops any currently playing audio, revokes object URLs,
   * and aborts pending fetch requests.
   */
  public stop(): void {
    // Increment session ID to invalidate any in-flight promises
    this.activeSessionId++;

    // Abort pending HTTP requests
    if (this.abortController) {
      try {
        this.abortController.abort();
      } catch {
        // Ignore abort errors
      }
      this.abortController = null;
    }

    // Stop and unload active audio element
    if (this.activeAudio) {
      try {
        this.activeAudio.pause();
        this.activeAudio.currentTime = 0;
        this.activeAudio.src = '';
        this.activeAudio.onended = null;
        this.activeAudio.onerror = null;
      } catch (e) {
        console.warn('Error stopping audition audio', e);
      }
      this.activeAudio = null;
    }

    // Revoke object URL to avoid browser memory leaks
    if (this.activeUrl) {
      try {
        URL.revokeObjectURL(this.activeUrl);
      } catch {
        // Ignore revoke errors
      }
      this.activeUrl = null;
    }

    this.state = { playingIndex: null, isLoading: false };
    this.notify();
  }

  /**
   * Plays a single voice audition clip exclusively.
   * If the clicked index is already loading or playing, toggles it off.
   */
  public async toggle(index: number, text: string, character: string): Promise<void> {
    const trimmed = text.trim();
    if (!trimmed) return;

    // Toggle OFF if clicking the same line that is currently playing or loading
    if (this.state.playingIndex === index) {
      this.stop();
      return;
    }

    // Stop any existing audition before starting a new one
    this.stop();

    // Signal video preview to pause
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('veraxi:pause-preview'));
    }

    const sessionId = ++this.activeSessionId;
    const controller = new AbortController();
    this.abortController = controller;

    this.state = { playingIndex: index, isLoading: true };
    this.notify();

    try {
      const blob = await api.auditionVoice(trimmed, character, 1.0, controller.signal);

      // Verify this session is still the active one (user didn't click another or stop)
      if (sessionId !== this.activeSessionId) {
        return;
      }

      const url = URL.createObjectURL(blob);
      this.activeUrl = url;

      const audio = new Audio(url);
      this.activeAudio = audio;

      audio.onended = () => {
        if (sessionId === this.activeSessionId) {
          this.stop();
        }
      };

      audio.onerror = () => {
        if (sessionId === this.activeSessionId) {
          console.error('Audio playback error during audition');
          this.stop();
        }
      };

      this.state = { playingIndex: index, isLoading: false };
      this.notify();

      const playPromise = audio.play();
      if (playPromise !== undefined) {
        await playPromise.catch((err) => {
          // If aborted or paused before play completed, ignore AbortError
          if (err.name !== 'AbortError' && sessionId === this.activeSessionId) {
            console.warn('Audition audio play failed:', err);
            this.stop();
          }
        });
      }
    } catch (err: any) {
      if (err.name === 'AbortError' || sessionId !== this.activeSessionId) {
        // Request was cancelled cleanly, do nothing
        return;
      }
      console.error('VOICEVOX audition failed:', err);
      this.stop();
      alert('VOICEVOX試聴に失敗しました。VOICEVOXが起動しているか確認してください。');
    }
  }
}

// Global singleton instance for the app session
export const auditionManager = new AuditionManager();
