import type { AudioSource, UiConfig, VoiceDetail } from '../../lib/types';

export interface CreationPaneProps {
  config: UiConfig;
  onCreated: (detail: VoiceDetail) => void;
  onError: (message: string | null) => void;
  onPlayReviewAudio: (source: AudioSource) => void;
}

export function displayNameFromVoiceId(voiceId: string): string {
  return voiceId
    .replaceAll('-', ' ')
    .replaceAll('_', ' ')
    .replace(/\b\w/g, (match) => match.toUpperCase());
}
