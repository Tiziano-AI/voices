import type { StudioThemeId } from '../lib/themes';
import type {
  AudioPlayResult,
  AudioSessionState,
  AudioSource,
  ComparedPerformance,
  CreationMode,
  PreviewClip,
  RenderArtifact,
  UiConfig,
  VoiceDetail,
  VoiceSummary,
} from '../lib/types';
import type { AuditionBoardActions, AuditionBoardState } from './useAuditionBoard';

/** State projected from the browser studio controller into the top-level shell. */
export interface StudioControllerState {
  theme: StudioThemeId;
  uiConfig: UiConfig;
  voices: VoiceSummary[];
  selectedVoiceId: string | null;
  activeVoiceDetail: VoiceDetail | null;
  scriptText: string;
  previewClip: PreviewClip | null;
  outputReason: string | null;
  compareVoiceIds: string[];
  compareClips: ComparedPerformance[];
  compareArtifacts: Record<string, RenderArtifact>;
  renderArtifact: RenderArtifact | null;
  searchQuery: string;
  creationMode: CreationMode;
  creationOpen: boolean;
  inspectorOpen: boolean;
  creationMessage: string | null;
  edgeMessage: string | null;
  libraryIntegrityError: string | null;
  bootstrapError: string | null;
  previewBusy: boolean;
  compareBusy: boolean;
  renderBusy: boolean;
  compareRenderBusy: boolean;
  appLoading: boolean;
  overrideLanguage: string | null;
  hasVoices: boolean;
  audioSession: AudioSessionState;
  auditionBoard: AuditionBoardState;
}

/** Browser studio actions that may perform local UI state changes or loopback API calls. */
export interface StudioControllerActions {
  bootstrapStudio: () => Promise<void>;
  setTheme: (theme: StudioThemeId) => void;
  setSearchQuery: (query: string) => void;
  setScriptText: (text: string) => void;
  setOverrideLanguage: (language: string | null) => void;
  setCreationMessage: (message: string | null) => void;
  openCreation: (mode: CreationMode) => void;
  closeCreation: () => void;
  changeCreationMode: (mode: CreationMode) => void;
  openInspector: () => void;
  closeInspector: () => void;
  selectVoice: (voiceId: string) => void;
  auditionReference: (voiceId: string) => Promise<void>;
  preview: () => Promise<void>;
  compare: () => Promise<void>;
  render: () => Promise<void>;
  renderCompareSet: () => Promise<void>;
  toggleCompare: (voiceId: string) => void;
  deleteVoice: (voice: VoiceSummary) => Promise<void>;
  voiceCreated: (detail: VoiceDetail) => Promise<void>;
  batchCreated: (preferredVoiceId: string | null) => Promise<void>;
  playAudio: (source: AudioSource) => Promise<AudioPlayResult>;
  stopAudio: () => void;
  auditionBoard: AuditionBoardActions;
}

/** Browser studio controller envelope consumed by the top-level shell. */
export interface StudioController {
  state: StudioControllerState;
  actions: StudioControllerActions;
}
