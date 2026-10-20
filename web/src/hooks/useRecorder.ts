import { useCallback, useEffect, useRef, useState } from 'react';

export type RecorderMode = 'guided' | 'free';
export type RecorderStatus = 'idle' | 'requesting' | 'recording' | 'processing' | 'error';

interface StartOptions {
  mode: RecorderMode;
  limitSeconds: number;
}

interface RecorderState {
  status: RecorderStatus;
  elapsedSeconds: number;
  level: number;
  audioBlob: Blob | null;
  error: string | null;
}

const INITIAL_STATE: RecorderState = {
  status: 'idle',
  elapsedSeconds: 0,
  level: 0,
  audioBlob: null,
  error: null,
};

export function useRecorder() {
  const [state, setState] = useState<RecorderState>(INITIAL_STATE);

  const statusRef = useRef<RecorderStatus>(INITIAL_STATE.status);
  const captureIdRef = useRef(0);
  const streamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const rafRef = useRef<number | null>(null);
  const intervalRef = useRef<number | null>(null);
  const guidedTimeoutRef = useRef<number | null>(null);
  const clearTimers = useCallback(() => {
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    if (intervalRef.current !== null) {
      window.clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    if (guidedTimeoutRef.current !== null) {
      window.clearTimeout(guidedTimeoutRef.current);
      guidedTimeoutRef.current = null;
    }
  }, []);

  const cleanupMedia = useCallback(() => {
    clearTimers();
    const recorder = recorderRef.current;
    if (recorder) {
      recorder.ondataavailable = null;
      recorder.onstop = null;
      recorder.onerror = null;
      if (recorder.state !== 'inactive') {
        try {
          recorder.stop();
        } catch {
          // Track retirement below must still happen if the encoder already stopped.
        }
      }
    }
    recorderRef.current = null;

    if (streamRef.current) {
      for (const track of streamRef.current.getTracks()) {
        track.stop();
      }
      streamRef.current = null;
    }

    if (audioContextRef.current) {
      audioContextRef.current.close().catch(() => undefined);
      audioContextRef.current = null;
    }

    analyserRef.current = null;
  }, [clearTimers]);

  useEffect(
    () => () => {
      captureIdRef.current += 1;
      cleanupMedia();
    },
    [cleanupMedia],
  );

  const beginMetering = useCallback((stream: MediaStream) => {
    const audioContext = new AudioContext();
    audioContextRef.current = audioContext;
    const source = audioContext.createMediaStreamSource(stream);
    const analyser = audioContext.createAnalyser();
    analyser.fftSize = 2048;
    source.connect(analyser);
    analyserRef.current = analyser;
    const tick = () => {
      const currentAnalyser = analyserRef.current;
      if (!currentAnalyser) {
        return;
      }

      const samples = new Uint8Array(currentAnalyser.fftSize);
      currentAnalyser.getByteTimeDomainData(samples);
      let total = 0;
      for (const sample of samples) {
        const centered = sample / 128 - 1;
        total += centered * centered;
      }
      const rms = Math.sqrt(total / samples.length);
      setState((current) => ({ ...current, level: Math.min(rms * 4, 1) }));
      rafRef.current = requestAnimationFrame(tick);
    };

    tick();
  }, []);

  const stop = useCallback(() => {
    const recorder = recorderRef.current;
    if (!recorder || recorder.state === 'inactive') {
      return;
    }
    clearTimers();
    recorder.stop();
  }, [clearTimers]);

  const start = useCallback(
    async ({ mode, limitSeconds }: StartOptions) => {
      if (
        statusRef.current === 'requesting' ||
        statusRef.current === 'recording' ||
        statusRef.current === 'processing'
      ) {
        return;
      }
      cleanupMedia();
      const captureId = ++captureIdRef.current;
      chunksRef.current = [];
      statusRef.current = 'requesting';
      setState({ ...INITIAL_STATE, status: 'requesting' });

      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        if (captureId !== captureIdRef.current) {
          for (const track of stream.getTracks()) {
            track.stop();
          }
          return;
        }
        streamRef.current = stream;
        const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus' : '';
        const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
        recorderRef.current = recorder;
        beginMetering(stream);

        recorder.ondataavailable = (event) => {
          if (event.data.size > 0) {
            chunksRef.current.push(event.data);
          }
        };

        recorder.onstop = () => {
          if (captureId !== captureIdRef.current) {
            return;
          }
          const audioBlob = new Blob(chunksRef.current, { type: recorder.mimeType || 'audio/webm' });
          cleanupMedia();
          statusRef.current = 'processing';
          setState((current) => ({
            ...current,
            status: 'processing',
            audioBlob,
            level: 0,
          }));
        };

        recorder.onerror = () => {
          if (captureId !== captureIdRef.current) {
            return;
          }
          cleanupMedia();
          statusRef.current = 'error';
          setState({
            ...INITIAL_STATE,
            status: 'error',
            error: 'Recording failed. Check microphone permissions and retry.',
          });
        };

        recorder.start(250);
        intervalRef.current = window.setInterval(() => {
          setState((current) => ({
            ...current,
            elapsedSeconds: current.status === 'recording' ? current.elapsedSeconds + 0.125 : current.elapsedSeconds,
          }));
        }, 125);
        statusRef.current = 'recording';
        setState((current) => ({ ...current, status: 'recording' }));

        if (mode === 'guided') {
          guidedTimeoutRef.current = window.setTimeout(() => {
            stop();
          }, limitSeconds * 1000);
        }
      } catch {
        if (captureId !== captureIdRef.current) {
          return;
        }
        cleanupMedia();
        statusRef.current = 'error';
        setState({
          ...INITIAL_STATE,
          status: 'error',
          error: 'Microphone access was denied or is unavailable in this browser.',
        });
      }
    },
    [beginMetering, cleanupMedia, stop],
  );

  const reset = useCallback(() => {
    captureIdRef.current += 1;
    cleanupMedia();
    chunksRef.current = [];
    statusRef.current = 'idle';
    setState(INITIAL_STATE);
  }, [cleanupMedia]);

  const consumeAudioBlob = useCallback(() => {
    statusRef.current = 'idle';
    setState((current) => ({ ...current, audioBlob: null, status: 'idle' }));
  }, []);

  return {
    ...state,
    start,
    stop,
    reset,
    consumeAudioBlob,
    isRecording: state.status === 'recording',
  };
}
