export type SourceKind = 'design' | 'clone';

export interface EdgeErrorPayload {
  error_code: string;
  detail: string;
}

export interface UiConfig {
  base_model_id: string;
  base_model_revision: string;
  supported_languages: string[];
  default_language: string;
  guided_record_target_seconds: number;
  free_record_minimum_seconds: number;
  guided_scripts: Record<string, string>;
}

export interface VoiceRecord {
  schema_version: 2;
  id: string;
  name: string;
  created_at: string;
  language: string;
  base_model_id: string;
  reference_text: string;
  reference_sha256: string;
  source:
    | {
        kind: 'design';
        model_id: string;
        instruct: string;
      }
    | {
        kind: 'clone';
      };
}

export interface VoiceSummary {
  id: string;
  name: string;
  language: string;
  source_kind: SourceKind;
  description: string;
  created_at: string;
  reference_sha256: string;
  reference_text_sha256: string;
}

export interface ReferenceIdentity {
  reference_sha256: string;
  reference_text_sha256: string;
}

export interface ModelIdentity {
  base_model_id: string;
  base_model_revision: string;
}

export interface PreviewInput extends ReferenceIdentity, ModelIdentity {
  voice_id: string;
  text: string;
  language: string;
}

export interface VoiceDetail {
  summary: VoiceSummary;
  record: VoiceRecord;
  reference_text: string;
  reference_audio_url: string;
}

export interface PreviewClip {
  token: string;
  voice_id: string;
  kind: 'generated' | 'reference';
  language: string;
  audio_url: string;
  input: PreviewInput;
}

export interface ComparedPerformance {
  requestedInput: PreviewInput;
  clip: PreviewClip | null;
  failureDetail: string | null;
  freshnessReason?: string | null;
}

export type CompareResult =
  | { voice_id: string; clip: PreviewClip; error: null }
  | { voice_id: string; clip: null; error: EdgeErrorPayload };

export interface RenderArtifact {
  record: {
    schema_version: 2;
    voice_id: string;
    created_at: string;
    language: string;
    base_model_id: string;
    base_model_revision: string | null;
    text: string;
    output_audio: string;
    reference_voice_id: string;
    reference_sha256: string;
    reference_text_sha256: string | null;
  };
  audio_url: string;
  sidecar_url: string;
}

export interface TranscriptionSegment {
  text: string;
  language: string;
  start: number;
  end: number;
}

export interface CloneReviewDraft {
  review_token: string;
  suggested_voice_id: string;
  transcript: string;
  language: string;
  duration_seconds: number;
  segments: TranscriptionSegment[];
  audio_url: string;
}

export interface BatchDesignRow {
  voice_id: string;
  name: string;
  status: 'dry_run' | 'ok' | 'error';
  detail: string;
}

export interface BatchDesignResult {
  dry_run: boolean;
  rows: BatchDesignRow[];
}

export type CreationMode = 'design' | 'clone' | 'record';

export type AudioSourceKind = 'reference' | 'preview' | 'compare' | 'board' | 'review';

export interface AudioSource {
  id: string;
  kind: AudioSourceKind;
  label: string;
  url: string;
}

export type AudioSessionStatus = 'idle' | 'loading' | 'playing' | 'paused' | 'blocked' | 'error';
export type AudioPlayResult = 'playing' | 'blocked' | 'error' | 'superseded';

export interface AudioSessionState {
  status: AudioSessionStatus;
  source: AudioSource | null;
  message: string | null;
}

export interface ClipPosition {
  x: number;
  y: number;
}

export interface ClipCandidate {
  id: string;
  voiceName: string;
  requestedInput: PreviewInput;
  attempt: number;
  generationStatus: 'pending' | 'ready' | 'failed';
  clip: PreviewClip | null;
  position: ClipPosition;
  renderArtifact: RenderArtifact | null;
  generationError: string | null;
  saveStatus: 'idle' | 'saving' | 'saved' | 'failed';
  saveError: string | null;
}

export type AuditionLanguageFilter = 'all' | string;
