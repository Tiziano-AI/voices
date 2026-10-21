import type {
  BatchDesignResult,
  CloneReviewDraft,
  CompareResult,
  EdgeErrorPayload,
  ModelIdentity,
  PreviewClip,
  PreviewInput,
  ReferenceIdentity,
  RenderArtifact,
  UiConfig,
  VoiceDetail,
  VoiceSummary,
} from './types';

export class EdgeRequestError extends Error {
  readonly payload: EdgeErrorPayload;
  readonly status: number;

  constructor(status: number, payload: EdgeErrorPayload) {
    super(payload.detail);
    this.name = 'EdgeRequestError';
    this.payload = payload;
    this.status = status;
  }
}

export const STUDIO_CONNECTION_LOST_MESSAGE =
  'Studio connection lost. Relaunch uv run voices ui and keep the process running.';

async function parseResponse<T>(response: Response): Promise<T> {
  if (response.ok) {
    return (await response.json()) as T;
  }

  const fallback = {
    error_code: 'UnknownError',
    detail: response.statusText || 'Request failed.',
  } satisfies EdgeErrorPayload;

  let payload = fallback;
  try {
    payload = (await response.json()) as EdgeErrorPayload;
  } catch {
    payload = fallback;
  }
  throw new EdgeRequestError(response.status, payload);
}

async function requestJson<T>(input: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(input, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        ...(init?.headers ?? {}),
      },
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new Error('Request cancelled.');
    }
    throw new Error(STUDIO_CONNECTION_LOST_MESSAGE);
  }
  return parseResponse<T>(response);
}

async function requestForm<T>(input: string, formData: FormData, init?: RequestInit): Promise<T> {
  const response = await fetch(input, {
    ...init,
    method: 'POST',
    body: formData,
  });
  return parseResponse<T>(response);
}

export function fetchUiConfig(): Promise<UiConfig> {
  return requestJson<UiConfig>('/api/ui-config');
}

export function fetchVoices(): Promise<VoiceSummary[]> {
  return requestJson<VoiceSummary[]>('/api/voices');
}

export function fetchVoiceDetail(voiceId: string): Promise<VoiceDetail> {
  return requestJson<VoiceDetail>(`/api/voices/${voiceId}`);
}

export function previewVoice(input: PreviewInput): Promise<PreviewClip> {
  return requestJson<PreviewClip>('/api/preview', {
    method: 'POST',
    body: JSON.stringify({
      voice_id: input.voice_id,
      text: input.text,
      language: input.language,
      expected_reference: {
        reference_sha256: input.reference_sha256,
        reference_text_sha256: input.reference_text_sha256,
      },
      expected_model: { base_model_id: input.base_model_id, base_model_revision: input.base_model_revision },
    }),
  });
}

export function compareVoices(input: {
  voiceIds: string[];
  text: string;
  language: string | null;
  expectedLanguages: Record<string, string>;
  expectedReferences: Record<string, ReferenceIdentity>;
  expectedModel: ModelIdentity;
}): Promise<CompareResult[]> {
  return requestJson<CompareResult[]>('/api/compare', {
    method: 'POST',
    body: JSON.stringify({
      voice_ids: input.voiceIds,
      text: input.text,
      language: input.language,
      expected_languages: input.expectedLanguages,
      expected_references: input.expectedReferences,
      expected_model: input.expectedModel,
    }),
  });
}

export function renderVoice(input: PreviewInput): Promise<RenderArtifact> {
  return requestJson<RenderArtifact>('/api/render', {
    method: 'POST',
    body: JSON.stringify({
      voice_id: input.voice_id,
      text: input.text,
      language: input.language,
      expected_reference: {
        reference_sha256: input.reference_sha256,
        reference_text_sha256: input.reference_text_sha256,
      },
      expected_model: { base_model_id: input.base_model_id, base_model_revision: input.base_model_revision },
    }),
  });
}

export function exportPreview(token: string): Promise<RenderArtifact> {
  return requestJson<RenderArtifact>(`/api/previews/${encodeURIComponent(token)}/export`, { method: 'POST' });
}

export function designVoice(input: {
  name: string;
  voiceId: string | null;
  instruct: string;
  text: string;
  language: string;
  overwrite: boolean;
  operationToken: string;
  signal?: AbortSignal;
}): Promise<VoiceDetail> {
  return requestJson<VoiceDetail>('/api/design', {
    method: 'POST',
    signal: input.signal,
    body: JSON.stringify({
      name: input.name,
      voice_id: input.voiceId,
      instruct: input.instruct,
      text: input.text,
      language: input.language,
      overwrite: input.overwrite,
      operation_token: input.operationToken,
    }),
  });
}

export function batchDesignVoicePack(input: {
  file: File;
  language: string;
  text: string;
  overwrite: boolean;
  dryRun: boolean;
  operationToken: string;
  signal?: AbortSignal;
}): Promise<BatchDesignResult> {
  const formData = new FormData();
  formData.append('file', input.file);
  formData.append('language', input.language);
  formData.append('text', input.text);
  formData.append('overwrite', String(input.overwrite));
  formData.append('dry_run', String(input.dryRun));
  formData.append('operation_token', input.operationToken);
  return requestForm<BatchDesignResult>('/api/design/batch', formData, { signal: input.signal });
}

export async function cancelOperation(operationToken: string): Promise<void> {
  const response = await fetch(`/api/operations/${encodeURIComponent(operationToken)}/cancel`, {
    method: 'POST',
    keepalive: true,
  });
  if (!response.ok) {
    await parseResponse(response);
  }
}

export function reviewClone(input: {
  file: File;
  language: string;
  reviewPolicy: 'import' | 'record_guided' | 'record_free';
  transcript: string | null;
  name: string | null;
  voiceId: string | null;
}): Promise<CloneReviewDraft> {
  const formData = new FormData();
  formData.append('audio', input.file);
  formData.append('language', input.language);
  formData.append('review_policy', input.reviewPolicy);
  if (input.transcript) {
    formData.append('transcript', input.transcript);
  }
  if (input.name) {
    formData.append('name', input.name);
  }
  if (input.voiceId) {
    formData.append('voice_id', input.voiceId);
  }
  return requestForm<CloneReviewDraft>('/api/clone/review', formData);
}

export function saveClone(input: {
  reviewToken: string;
  voiceId: string;
  name: string;
  transcript: string;
  overwrite: boolean;
  signal?: AbortSignal;
}): Promise<VoiceDetail> {
  return requestJson<VoiceDetail>('/api/clone/save', {
    method: 'POST',
    signal: input.signal,
    body: JSON.stringify({
      review_token: input.reviewToken,
      voice_id: input.voiceId,
      name: input.name,
      transcript: input.transcript,
      overwrite: input.overwrite,
    }),
  });
}

export async function deleteVoice(voiceId: string): Promise<void> {
  const response = await fetch(`/api/voices/${voiceId}`, { method: 'DELETE' });
  if (!response.ok) {
    await parseResponse(response);
  }
}
