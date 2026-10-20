import type { Page } from '@playwright/test';

export type AudioPlayMode = 'resolve' | 'pending' | 'block' | 'reject';

type StudioAudioWindow = Window &
  typeof globalThis & {
    __playedAudioUrls: string[];
    __setAudioPlayMode: (mode: AudioPlayMode) => void;
    __resolveAudioPlay: () => void;
    __rejectAudioPlay: () => void;
  };

export function fakeAudioFilePayload(name: string) {
  return {
    name,
    mimeType: 'audio/wav',
    buffer: Buffer.from('524946460000000057415645666d7420', 'hex'),
  };
}

export async function installStudioBrowserMocks(page: Page): Promise<void> {
  await page.addInitScript(() => {
    type AudioPlayMode = 'resolve' | 'pending' | 'block' | 'reject';
    type StudioAudioWindow = Window &
      typeof globalThis & {
        __playedAudioUrls: string[];
        __setAudioPlayMode: (mode: AudioPlayMode) => void;
        __resolveAudioPlay: () => void;
        __rejectAudioPlay: () => void;
      };

    class FakeAudioContext {
      createMediaStreamSource() {
        return { connect() {} };
      }
      createAnalyser() {
        return {
          fftSize: 2048,
          getByteTimeDomainData(array: Uint8Array) {
            array.fill(128);
          },
        };
      }
      close() {
        return Promise.resolve();
      }
    }

    class FakeMediaRecorder {
      static isTypeSupported() {
        return true;
      }

      mimeType = 'audio/webm';
      state = 'inactive';
      ondataavailable: ((event: BlobEvent) => void) | null = null;
      onstop: (() => void) | null = null;
      onerror: (() => void) | null = null;

      start() {
        this.state = 'recording';
        const blob = new Blob(['fake-audio'], { type: 'audio/webm' });
        window.setTimeout(() => {
          this.ondataavailable?.({ data: blob } as BlobEvent);
        }, 50);
      }

      stop() {
        this.state = 'inactive';
        window.setTimeout(() => {
          this.onstop?.();
        }, 25);
      }
    }

    Object.defineProperty(window, 'AudioContext', { value: FakeAudioContext });
    Object.defineProperty(window, 'MediaRecorder', { value: FakeMediaRecorder });
    Object.defineProperty(navigator, 'mediaDevices', {
      value: {
        getUserMedia: async () => new MediaStream(),
      },
    });
    const studioWindow = window as StudioAudioWindow;
    let playMode: AudioPlayMode = 'resolve';
    let pendingResolve: (() => void) | null = null;
    let pendingReject: (() => void) | null = null;

    Object.defineProperty(window, '__playedAudioUrls', { value: [], writable: true });
    Object.defineProperty(window, '__setAudioPlayMode', {
      value(nextMode: AudioPlayMode) {
        playMode = nextMode;
      },
    });
    Object.defineProperty(window, '__resolveAudioPlay', {
      value() {
        pendingResolve?.();
        pendingResolve = null;
        pendingReject = null;
      },
    });
    Object.defineProperty(window, '__rejectAudioPlay', {
      value() {
        pendingReject?.();
        pendingResolve = null;
        pendingReject = null;
      },
    });
    Object.defineProperty(window.HTMLMediaElement.prototype, 'play', {
      value() {
        const audio = this as HTMLMediaElement;
        studioWindow.__playedAudioUrls.push(audio.currentSrc || audio.src);
        if (playMode === 'block') {
          return Promise.reject(new DOMException('Blocked by browser policy.', 'NotAllowedError'));
        }
        if (playMode === 'reject') {
          return Promise.reject(new Error('Synthetic playback failure.'));
        }
        if (playMode === 'pending') {
          return new Promise<void>((resolve, reject) => {
            pendingResolve = resolve;
            pendingReject = () => reject(new Error('Synthetic playback failure.'));
          });
        }
        return Promise.resolve();
      },
    });
  });
}

export async function setAudioPlayMode(page: Page, mode: AudioPlayMode): Promise<void> {
  await page.evaluate((nextMode) => {
    (window as StudioAudioWindow).__setAudioPlayMode(nextMode);
  }, mode);
}

export async function resolveAudioPlay(page: Page): Promise<void> {
  await page.evaluate(() => {
    (window as StudioAudioWindow).__resolveAudioPlay();
  });
}

export async function playedAudioUrls(page: Page): Promise<string[]> {
  return await page.evaluate(() => (window as StudioAudioWindow).__playedAudioUrls);
}
