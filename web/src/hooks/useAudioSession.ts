import { useCallback, useEffect, useRef, useState } from 'react';

import type { AudioPlayResult, AudioSessionState, AudioSource } from '../lib/types';

const INITIAL_AUDIO_SESSION: AudioSessionState = {
  status: 'idle',
  source: null,
  message: null,
};

function playbackErrorStatus(error: unknown): AudioSessionState['status'] {
  if (error instanceof DOMException && error.name === 'NotAllowedError') {
    return 'blocked';
  }
  return 'error';
}

function playbackErrorMessage(error: unknown): string {
  if (error instanceof DOMException && error.name === 'NotAllowedError') {
    return 'Browser audio is blocked. Click a play control again to start this clip.';
  }
  if (error instanceof Error) {
    return error.message;
  }
  return 'Unable to play this audio clip.';
}

export function useAudioSession() {
  const [state, setState] = useState<AudioSessionState>(INITIAL_AUDIO_SESSION);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const playIdRef = useRef(0);

  const ensureAudio = useCallback(() => {
    if (audioRef.current === null) {
      audioRef.current = new Audio();
      audioRef.current.preload = 'auto';
    }
    return audioRef.current;
  }, []);

  const stop = useCallback(() => {
    playIdRef.current += 1;
    const audio = audioRef.current;
    if (audio) {
      audio.pause();
      audio.removeAttribute('src');
      audio.load();
    }
    setState({ status: 'idle', source: null, message: null });
  }, []);

  const play = useCallback(
    async (source: AudioSource): Promise<AudioPlayResult> => {
      const playId = playIdRef.current + 1;
      playIdRef.current = playId;
      const audio = ensureAudio();
      audio.pause();
      audio.src = source.url;
      audio.currentTime = 0;
      setState({ status: 'loading', source, message: null });

      audio.onended = () => {
        if (playIdRef.current === playId) {
          setState({ status: 'paused', source, message: null });
        }
      };
      audio.onerror = () => {
        if (playIdRef.current === playId) {
          setState({ status: 'error', source, message: 'Unable to load this audio clip.' });
        }
      };

      try {
        await audio.play();
        if (playIdRef.current !== playId) {
          return 'superseded';
        }
        setState({ status: 'playing', source, message: null });
        return 'playing';
      } catch (error) {
        if (playIdRef.current !== playId) {
          return 'superseded';
        }
        const status = playbackErrorStatus(error);
        setState({ status, source, message: playbackErrorMessage(error) });
        return status === 'blocked' ? 'blocked' : 'error';
      }
    },
    [ensureAudio],
  );

  useEffect(
    () => () => {
      const audio = audioRef.current;
      if (audio) {
        audio.pause();
        audio.removeAttribute('src');
        audio.load();
      }
      audioRef.current = null;
    },
    [],
  );

  return { state, play, stop };
}
