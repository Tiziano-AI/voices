import { useRef, useState } from 'react';

import { compareVoices, EdgeRequestError, exportPreview, previewVoice, renderVoice } from '../lib/api';
import { errorDetail } from '../lib/appState';
import { freshnessReason, previewInput } from '../lib/previewInput';
import type {
  AudioPlayResult,
  AudioSource,
  ComparedPerformance,
  PreviewClip,
  PreviewInput,
  RenderArtifact,
  UiConfig,
  VoiceSummary,
} from '../lib/types';

interface PerformanceSessionInput {
  voices: VoiceSummary[];
  selectedVoiceId: string | null;
  scriptText: string;
  overrideLanguage: string | null;
  uiConfig: UiConfig;
  playAudio: (source: AudioSource) => Promise<AudioPlayResult>;
  setMessage: (message: string | null) => void;
  refreshInputs: () => Promise<void>;
}

/** Owns the displayed performances and their exports, separately from editing and playback. */
export function usePerformanceSession({
  voices,
  selectedVoiceId,
  scriptText,
  overrideLanguage,
  uiConfig,
  playAudio,
  setMessage,
  refreshInputs,
}: PerformanceSessionInput) {
  const [preview, setPreview] = useState<{ requestedInput: PreviewInput; clip: PreviewClip } | null>(null);
  const [compareVoiceIds, setCompareVoiceIds] = useState<string[]>([]);
  const [compareClips, setCompareClips] = useState<ComparedPerformance[]>([]);
  const [compareArtifacts, setCompareArtifacts] = useState<Record<string, RenderArtifact>>({});
  const [renderArtifact, setRenderArtifact] = useState<RenderArtifact | null>(null);
  const [previewBusy, setPreviewBusy] = useState(false);
  const [compareBusy, setCompareBusy] = useState(false);
  const [renderBusy, setRenderBusy] = useState(false);
  const [compareRenderBusy, setCompareRenderBusy] = useState(false);
  const previewRequest = useRef(0);
  const compareRequest = useRef(0);
  const savingPreview = useRef(false);
  const savingCompare = useRef(false);
  const targetFor = (voiceId: string): PreviewInput | undefined => {
    const voice = voices.find((item) => item.id === voiceId);
    return voice
      ? previewInput(
          voice,
          scriptText.trim(),
          overrideLanguage ?? voice.language ?? uiConfig.default_language,
          uiConfig,
        )
      : undefined;
  };
  const selectedTarget = selectedVoiceId ? targetFor(selectedVoiceId) : undefined;
  const renderedInput: PreviewInput | undefined = renderArtifact
    ? {
        ...renderArtifact.record,
        base_model_revision: renderArtifact.record.base_model_revision ?? '',
        reference_text_sha256: renderArtifact.record.reference_text_sha256 ?? '',
      }
    : undefined;
  const outputReason = preview
    ? freshnessReason(
        preview.requestedInput,
        preview.clip,
        preview.clip.voice_id === selectedVoiceId ? selectedTarget : undefined,
      )
    : renderedInput
      ? freshnessReason(renderedInput, null, renderedInput.voice_id === selectedVoiceId ? selectedTarget : undefined)
      : null;
  const compared = compareClips.map((performance) => ({
    ...performance,
    freshnessReason: freshnessReason(
      performance.requestedInput,
      performance.clip,
      compareVoiceIds.includes(performance.requestedInput.voice_id)
        ? targetFor(performance.requestedInput.voice_id)
        : undefined,
    ),
  }));
  const currentTarget = useRef(selectedTarget);
  currentTarget.current = selectedTarget;

  const reportError = async (error: unknown, fallback: string) => {
    setMessage(errorDetail(error, fallback));
    if (error instanceof EdgeRequestError && error.status === 409) {
      try {
        await refreshInputs();
      } catch {
        setMessage(`${errorDetail(error, fallback)} Refresh the studio before retrying.`);
      }
    }
  };

  const abandonGeneration = () => {
    previewRequest.current += 1;
    compareRequest.current += 1;
    setPreviewBusy(false);
    setCompareBusy(false);
  };

  const generatePreview = async () => {
    if (!selectedTarget?.text || savingPreview.current) return;
    const requestedInput = selectedTarget;
    const request = ++previewRequest.current;
    setPreviewBusy(true);
    setMessage(null);
    try {
      const clip = await previewVoice(requestedInput);
      if (request !== previewRequest.current) return;
      setPreview({ requestedInput, clip });
      setRenderArtifact(null);
      if (freshnessReason(requestedInput, clip, currentTarget.current) === null) {
        await playAudio({ id: `preview:${clip.token}`, kind: 'preview', label: clip.voice_id, url: clip.audio_url });
      }
    } catch (error) {
      if (request === previewRequest.current) await reportError(error, 'Unable to preview the current voice.');
    } finally {
      if (request === previewRequest.current) setPreviewBusy(false);
    }
  };

  const generateCompare = async () => {
    if (!scriptText.trim() || compareVoiceIds.length === 0 || savingCompare.current) return;
    const requested = compareVoiceIds.map(targetFor).filter((input): input is PreviewInput => input !== undefined);
    if (requested.length !== compareVoiceIds.length) {
      setMessage('A queued voice is no longer available. Refresh the selection.');
      return;
    }
    const request = ++compareRequest.current;
    setCompareBusy(true);
    setMessage(null);
    try {
      const clips = await compareVoices({
        voiceIds: compareVoiceIds,
        text: scriptText.trim(),
        language: overrideLanguage,
        expectedLanguages: Object.fromEntries(requested.map((input) => [input.voice_id, input.language])),
        expectedReferences: Object.fromEntries(
          requested.map((input) => [
            input.voice_id,
            {
              reference_sha256: input.reference_sha256,
              reference_text_sha256: input.reference_text_sha256,
            },
          ]),
        ),
        expectedModel: { base_model_id: uiConfig.base_model_id, base_model_revision: uiConfig.base_model_revision },
      });
      if (request !== compareRequest.current) return;
      setCompareClips(
        requested.map((input) => ({
          requestedInput: input,
          clip: clips.find((clip) => clip.voice_id === input.voice_id) ?? null,
          failureDetail: clips.some((clip) => clip.voice_id === input.voice_id)
            ? null
            : 'No compared performance returned.',
        })),
      );
      setCompareArtifacts({});
    } catch (error) {
      if (request === compareRequest.current) {
        setCompareClips(
          requested.map((input) => ({
            requestedInput: input,
            clip: null,
            failureDetail: errorDetail(error, 'Unable to compare the selected voices.'),
          })),
        );
        await reportError(error, 'Unable to compare the selected voices.');
      }
    } finally {
      if (request === compareRequest.current) setCompareBusy(false);
    }
  };

  const savePreview = async () => {
    if (savingPreview.current || (!preview && !selectedTarget?.text)) return;
    savingPreview.current = true;
    setRenderBusy(true);
    setMessage(null);
    try {
      // Retained previews always export their token, including obsolete inputs and expired tokens.
      const artifact = preview
        ? await exportPreview(preview.clip.token)
        : await renderVoice(selectedTarget as PreviewInput);
      setRenderArtifact(artifact);
    } catch (error) {
      await reportError(error, 'Unable to save the performance.');
    } finally {
      savingPreview.current = false;
      setRenderBusy(false);
    }
  };

  const saveCompare = async () => {
    if (savingCompare.current || compareBusy || compareClips.length === 0 || compareClips.some((item) => !item.clip))
      return;
    savingCompare.current = true;
    setCompareRenderBusy(true);
    setMessage(null);
    const results = await Promise.allSettled(
      compareClips.map(async ({ clip }) => ({
        token: (clip as PreviewClip).token,
        artifact: await exportPreview((clip as PreviewClip).token),
      })),
    );
    const failures: string[] = [];
    const saved: Record<string, RenderArtifact> = {};
    for (const result of results) {
      if (result.status === 'fulfilled') saved[result.value.token] = result.value.artifact;
      else failures.push(errorDetail(result.reason, 'Unable to save a compared clip.'));
    }
    setCompareArtifacts((current) => ({ ...current, ...saved }));
    if (failures.length > 0)
      setMessage(`${failures.length} compared clip(s) could not be saved. ${failures.join(' ')}`);
    savingCompare.current = false;
    setCompareRenderBusy(false);
  };

  return {
    previewClip: preview?.clip ?? null,
    outputReason,
    compareVoiceIds,
    compareClips: compared,
    compareArtifacts,
    renderArtifact,
    previewBusy,
    compareBusy,
    renderBusy,
    compareRenderBusy,
    generatePreview,
    generateCompare,
    savePreview,
    saveCompare,
    abandonGeneration,
    toggleCompare: (voiceId: string) =>
      setCompareVoiceIds((current) =>
        current.includes(voiceId) ? current.filter((id) => id !== voiceId) : [...current, voiceId],
      ),
    removeCompareVoice: (voiceId: string) => setCompareVoiceIds((current) => current.filter((id) => id !== voiceId)),
  };
}
