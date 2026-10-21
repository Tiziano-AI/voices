import { startTransition, useCallback, useEffect, useRef, useState } from 'react';

import { deleteVoice, fetchUiConfig, fetchVoiceDetail, fetchVoices } from '../lib/api';
import {
  errorDetail,
  FALLBACK_CONFIG,
  integrityErrorDetail,
  resolveInitialTheme,
  THEME_STORAGE_KEY,
} from '../lib/appState';
import type { StudioThemeId } from '../lib/themes';
import type { CreationMode, UiConfig, VoiceDetail, VoiceSummary } from '../lib/types';
import type { StudioController } from './studioControllerTypes';
import { useAudioSession } from './useAudioSession';
import { useAuditionBoard } from './useAuditionBoard';
import { usePerformanceSession } from './usePerformanceSession';

export function useStudioController(): StudioController {
  const audioSession = useAudioSession();
  const [theme, setTheme] = useState<StudioThemeId>(resolveInitialTheme);
  const [uiConfig, setUiConfig] = useState<UiConfig>(FALLBACK_CONFIG);
  const [voices, setVoices] = useState<VoiceSummary[]>([]);
  const [selectedVoiceId, setSelectedVoiceId] = useState<string | null>(null);
  const [selectedVoiceDetail, setSelectedVoiceDetail] = useState<VoiceDetail | null>(null);
  const [scriptText, setScriptText] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [creationMode, setCreationMode] = useState<CreationMode>('design');
  const [creationOpen, setCreationOpen] = useState(false);
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [creationMessage, setCreationMessage] = useState<string | null>(null);
  const [edgeMessage, setEdgeMessage] = useState<string | null>(null);
  const [libraryIntegrityError, setLibraryIntegrityError] = useState<string | null>(null);
  const [bootstrapError, setBootstrapError] = useState<string | null>(null);
  const [appLoading, setAppLoading] = useState(true);
  const [overrideLanguage, setOverrideLanguage] = useState<string | null>(null);
  const detailRequestIdRef = useRef(0);
  const selectedVoice = voices.find((voice) => voice.id === selectedVoiceId);
  const activeVoiceDetail = selectedVoiceDetail?.summary.id === selectedVoiceId ? selectedVoiceDetail : null;

  const refreshVoices = useCallback(async (preferredVoiceId: string | null = null) => {
    const nextVoices = await fetchVoices();
    setLibraryIntegrityError(null);
    setBootstrapError(null);
    startTransition(() => {
      setVoices(nextVoices);
      if (nextVoices.length === 0) {
        setSelectedVoiceId(null);
        setSelectedVoiceDetail(null);
        return;
      }
      const preferred = preferredVoiceId && nextVoices.some((voice) => voice.id === preferredVoiceId);
      const nextSelectedVoiceId = preferred ? preferredVoiceId : (nextVoices[nextVoices.length - 1]?.id ?? null);
      setSelectedVoiceId(nextSelectedVoiceId);
      setSelectedVoiceDetail((current) => (current?.summary.id === nextSelectedVoiceId ? current : null));
    });
  }, []);
  const refreshInputs = useCallback(async () => {
    setUiConfig(await fetchUiConfig());
    await refreshVoices(selectedVoiceId);
  }, [refreshVoices, selectedVoiceId]);

  const bootstrapStudio = useCallback(async () => {
    setAppLoading(true);
    setBootstrapError(null);
    setEdgeMessage(null);
    try {
      setUiConfig(await fetchUiConfig());
      await refreshVoices();
    } catch (error) {
      const integrityDetail = integrityErrorDetail(error);
      if (integrityDetail !== null) {
        setLibraryIntegrityError(integrityDetail);
        return;
      }
      setLibraryIntegrityError(null);
      setBootstrapError(errorDetail(error, 'Unable to load the studio.'));
    } finally {
      setAppLoading(false);
    }
  }, [refreshVoices]);

  const performance = usePerformanceSession({
    voices,
    selectedVoiceId,
    scriptText,
    overrideLanguage,
    uiConfig,
    playAudio: audioSession.play,
    setMessage: setEdgeMessage,
    refreshInputs,
  });
  const auditionBoard = useAuditionBoard({
    voices,
    defaultLanguage: uiConfig.default_language,
    model: uiConfig,
    scriptText,
    playAudio: audioSession.play,
    refreshInputs,
  });

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  }, [theme]);
  useEffect(() => {
    void bootstrapStudio();
  }, [bootstrapStudio]);
  useEffect(() => {
    const requestId = ++detailRequestIdRef.current;
    if (!selectedVoice) {
      setSelectedVoiceDetail(null);
      return;
    }
    setSelectedVoiceDetail(null);
    void fetchVoiceDetail(selectedVoice.id)
      .then((detail) => {
        if (requestId === detailRequestIdRef.current) setSelectedVoiceDetail(detail);
      })
      .catch((error: unknown) => {
        if (requestId === detailRequestIdRef.current)
          setEdgeMessage(errorDetail(error, 'Unable to load voice details.'));
      });
  }, [selectedVoice]);

  const openCreation = (mode: CreationMode) => {
    performance.abandonGeneration();
    audioSession.stop();
    setCreationMode(mode);
    setCreationOpen(true);
    setCreationMessage(null);
    setEdgeMessage(null);
  };
  const selectVoice = (voiceId: string) => {
    performance.abandonGeneration();
    setSelectedVoiceId(voiceId);
    setSelectedVoiceDetail(null);
    setEdgeMessage(null);
    audioSession.stop();
  };
  const auditionReference = async (voiceId: string) => {
    setEdgeMessage(null);
    await audioSession.play({
      id: `reference:${voiceId}`,
      kind: 'reference',
      label: voices.find((voice) => voice.id === voiceId)?.name ?? voiceId,
      url: `/api/voices/${voiceId}/reference-audio`,
    });
  };
  const handleDeleteVoice = async (voice: VoiceSummary) => {
    if (!window.confirm(`Delete voice '${voice.name}'?`)) return;
    try {
      await deleteVoice(voice.id);
      performance.abandonGeneration();
      performance.removeCompareVoice(voice.id);
      setInspectorOpen(false);
      await refreshVoices(selectedVoiceId === voice.id ? null : selectedVoiceId);
    } catch (error) {
      const integrityDetail = integrityErrorDetail(error);
      if (integrityDetail !== null) {
        setLibraryIntegrityError(integrityDetail);
        setBootstrapError(null);
        return;
      }
      setEdgeMessage(errorDetail(error, 'Unable to delete the voice.'));
    }
  };
  const handleVoiceCreated = async (detail: VoiceDetail) => {
    setCreationOpen(false);
    setCreationMessage(null);
    setEdgeMessage(null);
    await refreshVoices(detail.record.id);
    setSelectedVoiceDetail(detail);
  };

  return {
    state: {
      theme,
      uiConfig,
      voices,
      selectedVoiceId,
      activeVoiceDetail,
      scriptText,
      previewClip: performance.previewClip,
      outputReason: performance.outputReason,
      compareVoiceIds: performance.compareVoiceIds,
      compareActionLabel: performance.compareActionLabel,
      compareClips: performance.compareClips,
      compareArtifacts: performance.compareArtifacts,
      renderArtifact: performance.renderArtifact,
      previewBusy: performance.previewBusy,
      compareBusy: performance.compareBusy,
      renderBusy: performance.renderBusy,
      compareRenderBusy: performance.compareRenderBusy,
      searchQuery,
      creationMode,
      creationOpen,
      inspectorOpen,
      creationMessage,
      edgeMessage,
      libraryIntegrityError,
      bootstrapError,
      appLoading,
      overrideLanguage,
      hasVoices: voices.length > 0,
      audioSession: audioSession.state,
      auditionBoard: auditionBoard.state,
    },
    actions: {
      bootstrapStudio,
      setTheme,
      setSearchQuery,
      setScriptText,
      setOverrideLanguage,
      setCreationMessage,
      openCreation,
      closeCreation: () => setCreationOpen(false),
      changeCreationMode: (mode) => {
        setCreationMode(mode);
        setCreationMessage(null);
      },
      openInspector: () => setInspectorOpen(true),
      closeInspector: () => setInspectorOpen(false),
      selectVoice,
      auditionReference,
      preview: performance.generatePreview,
      compare: performance.generateCompare,
      render: performance.savePreview,
      renderCompareSet: performance.saveCompare,
      toggleCompare: performance.toggleCompare,
      deleteVoice: handleDeleteVoice,
      voiceCreated: handleVoiceCreated,
      batchCreated: async (preferredVoiceId) => {
        setCreationMessage(null);
        setEdgeMessage(null);
        await refreshVoices(preferredVoiceId);
      },
      playAudio: audioSession.play,
      stopAudio: audioSession.stop,
      auditionBoard: auditionBoard.actions,
    },
  };
}
