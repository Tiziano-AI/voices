import { useCallback, useMemo, useRef, useState } from 'react';

import { EdgeRequestError, exportPreview, previewVoice } from '../lib/api';
import { freshnessReason, previewInput, samePreviewInput } from '../lib/previewInput';
import type {
  AudioPlayResult,
  AudioSource,
  AuditionLanguageFilter,
  ClipCandidate,
  ClipPosition,
  ModelIdentity,
  PreviewInput,
  VoiceSummary,
} from '../lib/types';

interface UseAuditionBoardInput {
  voices: VoiceSummary[];
  defaultLanguage: string;
  model: ModelIdentity;
  scriptText: string;
  playAudio: (source: AudioSource) => Promise<AudioPlayResult>;
  refreshInputs: () => Promise<void>;
}

export interface BoardCandidate extends ClipCandidate {
  current: boolean;
  freshnessReason: string | null;
}

export interface AuditionBoardState {
  text: string;
  languageFilter: AuditionLanguageFilter;
  candidates: BoardCandidate[];
  targetCount: number;
  currentCount: number;
  pendingCount: number;
  failedCount: number;
  unattemptedCount: number;
  nextBatchSize: number;
  generationLimit: number;
  busy: boolean;
  saving: boolean;
  message: string | null;
}

export interface AuditionBoardActions {
  setText: (text: string) => void;
  syncFromScript: () => void;
  setLanguageFilter: (filter: AuditionLanguageFilter) => void;
  generate: () => Promise<void>;
  retryCandidate: (id: string) => Promise<void>;
  moveCandidate: (id: string, position: ClipPosition) => void;
  resetLayout: () => void;
  removeCandidate: (id: string) => void;
  clear: () => void;
  refresh: () => Promise<void>;
  playCandidate: (id: string) => Promise<void>;
  renderCandidate: (id: string) => Promise<void>;
}

export const AUDITION_CARD_WIDTH = 220;
export const AUDITION_CARD_HEIGHT = 262;
export const AUDITION_CARD_GAP = 14;
export const AUDITION_BOARD_PADDING = 14;
const BOARD_COLS = 4;
const GENERATION_BATCH_LIMIT = 8;

function positionForIndex(index: number): ClipPosition {
  return {
    x: AUDITION_BOARD_PADDING + (index % BOARD_COLS) * (AUDITION_CARD_WIDTH + AUDITION_CARD_GAP),
    y: AUDITION_BOARD_PADDING + Math.floor(index / BOARD_COLS) * (AUDITION_CARD_HEIGHT + AUDITION_CARD_GAP),
  };
}

function targetStatus(
  target: PreviewInput,
  candidates: ClipCandidate[],
): 'ready' | 'pending' | 'failed' | 'unattempted' {
  const matching = candidates.filter(
    (candidate) =>
      samePreviewInput(candidate.requestedInput, target) &&
      (!candidate.clip || samePreviewInput(candidate.clip.input, target)),
  );
  if (matching.some((candidate) => candidate.generationStatus === 'ready')) return 'ready';
  if (matching.some((candidate) => candidate.generationStatus === 'pending')) return 'pending';
  if (matching.some((candidate) => candidate.generationStatus === 'failed')) return 'failed';
  return 'unattempted';
}

export function useAuditionBoard({
  voices,
  defaultLanguage,
  model,
  scriptText,
  playAudio,
  refreshInputs,
}: UseAuditionBoardInput): { state: AuditionBoardState; actions: AuditionBoardActions } {
  const [text, setText] = useState('');
  const [languageFilter, setLanguageFilter] = useState<AuditionLanguageFilter>('all');
  const [candidates, setCandidates] = useState<ClipCandidate[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [generationBusy, setGenerationBusy] = useState(false);
  const generationAttempts = useRef(new Set<string>());
  const exports = useRef(new Set<string>());
  const batchRunning = useRef(false);

  const targets = useMemo(
    () =>
      voices
        .filter((voice) => languageFilter === 'all' || voice.language === languageFilter)
        .map((voice) => ({ voice, input: previewInput(voice, text.trim(), voice.language || defaultLanguage, model) })),
    [voices, languageFilter, text, defaultLanguage, model],
  );
  const targetStates = targets.map((target) => ({ ...target, status: targetStatus(target.input, candidates) }));
  const unattempted = targetStates.filter((target) => target.status === 'unattempted');
  const saving = candidates.some((candidate) => candidate.saveStatus === 'saving');
  const busy = generationBusy;
  const visibleCandidates = candidates.map((candidate) => {
    const target = targets.find((item) => item.input.voice_id === candidate.requestedInput.voice_id);
    const reason = freshnessReason(candidate.requestedInput, candidate.clip, target?.input);
    return { ...candidate, current: reason === null, freshnessReason: reason };
  });

  const generateCandidate = async (candidate: ClipCandidate) => {
    const attemptKey = `${candidate.id}:${candidate.attempt}`;
    if (generationAttempts.current.has(attemptKey)) return;
    generationAttempts.current.add(attemptKey);
    const update = (change: Partial<ClipCandidate>) =>
      setCandidates((current) =>
        current.map((item) =>
          item.id === candidate.id && item.attempt === candidate.attempt ? { ...item, ...change } : item,
        ),
      );
    try {
      const clip = await previewVoice(candidate.requestedInput);
      update({ clip, generationStatus: 'ready', generationError: null });
    } catch (error) {
      update({
        generationStatus: 'failed',
        generationError: error instanceof Error ? error.message : 'Preview failed.',
      });
      if (error instanceof EdgeRequestError && error.status === 409) {
        try {
          await refreshInputs();
        } catch {
          setMessage('Input changed; refresh the studio before retrying.');
        }
      }
    } finally {
      generationAttempts.current.delete(attemptKey);
    }
  };

  const generate = async () => {
    if (batchRunning.current || busy) return;
    if (!text.trim()) {
      setMessage('Enter audition text first.');
      return;
    }
    const next = unattempted.slice(0, GENERATION_BATCH_LIMIT).map(
      ({ voice, input }, index): ClipCandidate => ({
        id: crypto.randomUUID(),
        voiceName: voice.name,
        requestedInput: input,
        attempt: 1,
        generationStatus: 'pending',
        clip: null,
        generationError: null,
        position: positionForIndex(candidates.length + index),
        renderArtifact: null,
        saveStatus: 'idle',
        saveError: null,
      }),
    );
    if (next.length === 0) return;
    batchRunning.current = true;
    setGenerationBusy(true);
    setMessage(null);
    setCandidates((current) => [...current, ...next]);
    try {
      await Promise.all(next.map(generateCandidate));
    } finally {
      batchRunning.current = false;
      setGenerationBusy(false);
    }
  };

  const retryCandidate = async (id: string) => {
    const previous = visibleCandidates.find((candidate) => candidate.id === id);
    if (!previous?.current || previous.generationStatus !== 'failed' || generationAttempts.current.size > 0) return;
    const next: ClipCandidate = {
      ...previous,
      attempt: previous.attempt + 1,
      generationStatus: 'pending',
      generationError: null,
    };
    setGenerationBusy(true);
    setCandidates((current) => current.map((candidate) => (candidate.id === id ? next : candidate)));
    try {
      await generateCandidate(next);
    } finally {
      setGenerationBusy(false);
    }
  };

  const moveCandidate = useCallback((id: string, position: ClipPosition) => {
    setCandidates((current) =>
      current.map((candidate) =>
        candidate.id === id
          ? {
              ...candidate,
              position: { x: Math.max(0, Math.round(position.x)), y: Math.max(0, Math.round(position.y)) },
            }
          : candidate,
      ),
    );
  }, []);
  const resetLayout = useCallback(() => {
    setCandidates((current) =>
      current.map((candidate, index) => ({ ...candidate, position: positionForIndex(index) })),
    );
  }, []);
  const removeCandidate = useCallback((id: string) => {
    setCandidates((current) => current.filter((candidate) => candidate.id !== id || candidate.saveStatus === 'saving'));
  }, []);
  const clear = () => {
    if (saving || exports.current.size > 0) return;
    setCandidates([]);
    setMessage(null);
  };
  const playCandidate = async (id: string) => {
    const candidate = candidates.find((item) => item.id === id);
    const url = candidate?.renderArtifact?.audio_url ?? candidate?.clip?.audio_url;
    if (candidate && url) await playAudio({ id, kind: 'board', label: candidate.voiceName, url });
  };
  const renderCandidate = async (id: string) => {
    const candidate = candidates.find((item) => item.id === id);
    if (!candidate?.clip || exports.current.has(id)) return;
    const token = candidate.clip.token;
    exports.current.add(id);
    const update = (change: Partial<ClipCandidate>) =>
      setCandidates((current) =>
        current.map((item) => (item.id === id && item.clip?.token === token ? { ...item, ...change } : item)),
      );
    update({ saveStatus: 'saving', saveError: null });
    try {
      const artifact = await exportPreview(token);
      update({ saveStatus: 'saved', renderArtifact: artifact });
    } catch (error) {
      update({ saveStatus: 'failed', saveError: error instanceof Error ? error.message : 'Save failed.' });
    } finally {
      exports.current.delete(id);
    }
  };

  return {
    state: {
      text,
      languageFilter,
      candidates: visibleCandidates,
      targetCount: targets.length,
      currentCount: targetStates.filter((target) => target.status === 'ready').length,
      pendingCount: targetStates.filter((target) => target.status === 'pending').length,
      failedCount: targetStates.filter((target) => target.status === 'failed').length,
      unattemptedCount: unattempted.length,
      nextBatchSize: Math.min(GENERATION_BATCH_LIMIT, unattempted.length),
      generationLimit: GENERATION_BATCH_LIMIT,
      busy,
      saving,
      message,
    },
    actions: {
      setText,
      syncFromScript: () => setText(scriptText),
      setLanguageFilter,
      generate,
      retryCandidate,
      moveCandidate,
      resetLayout,
      removeCandidate,
      clear,
      refresh: async () => {
        try {
          await refreshInputs();
          setMessage('Voice and model inputs refreshed.');
        } catch (error) {
          setMessage(error instanceof Error ? error.message : 'Unable to refresh inputs.');
        }
      },
      playCandidate,
      renderCandidate,
    },
  };
}
