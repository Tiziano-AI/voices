import type { ModelIdentity, PreviewClip, PreviewInput, VoiceSummary } from './types';

/** The browser submits this exact text once; the server returns the input it actually used. */
export function previewInput(voice: VoiceSummary, text: string, language: string, model: ModelIdentity): PreviewInput {
  return {
    voice_id: voice.id,
    text,
    language,
    base_model_id: model.base_model_id,
    base_model_revision: model.base_model_revision,
    reference_sha256: voice.reference_sha256,
    reference_text_sha256: voice.reference_text_sha256,
  };
}

export function samePreviewInput(a: PreviewInput, b: PreviewInput): boolean {
  return (
    a.voice_id === b.voice_id &&
    a.text === b.text &&
    a.language === b.language &&
    a.base_model_id === b.base_model_id &&
    a.base_model_revision === b.base_model_revision &&
    a.reference_sha256 === b.reference_sha256 &&
    a.reference_text_sha256 === b.reference_text_sha256
  );
}

export function freshnessReason(
  requested: PreviewInput,
  clip: PreviewClip | null,
  target: PreviewInput | undefined,
): string | null {
  if (!target) return 'Voice is not in the current selection.';
  if (requested.text !== target.text) return 'Audition text changed.';
  if (requested.language !== target.language) return 'Language changed.';
  if (
    requested.reference_sha256 !== target.reference_sha256 ||
    requested.reference_text_sha256 !== target.reference_text_sha256
  )
    return 'Voice reference changed.';
  if (requested.base_model_id !== target.base_model_id || requested.base_model_revision !== target.base_model_revision)
    return 'Model changed.';
  if (clip && !samePreviewInput(clip.input, target)) return 'Generated input differs from the current input.';
  return null;
}
