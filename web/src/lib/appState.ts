import { EdgeRequestError } from './api';
import type { StudioThemeId } from './themes';
import { DEFAULT_THEME_ID, isStudioThemeId } from './themes';
import type { UiConfig } from './types';

export const FALLBACK_CONFIG: UiConfig = {
  base_model_id: '',
  base_model_revision: '',
  supported_languages: ['English'],
  default_language: 'English',
  guided_record_target_seconds: 30,
  free_record_minimum_seconds: 3,
  guided_scripts: { English: '' },
};
export const THEME_STORAGE_KEY = 'voices-studio-theme';

export function resolveInitialTheme(): StudioThemeId {
  if (typeof window === 'undefined') {
    return DEFAULT_THEME_ID;
  }
  const storedTheme = window.localStorage.getItem(THEME_STORAGE_KEY);
  return isStudioThemeId(storedTheme) ? storedTheme : DEFAULT_THEME_ID;
}

export function errorDetail(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

export function integrityErrorDetail(error: unknown): string | null {
  if (!(error instanceof EdgeRequestError)) {
    return null;
  }
  if (error.payload.error_code === 'LibraryIntegrityError' || error.payload.error_code === 'InvalidVoiceEntryError') {
    return error.message;
  }
  return null;
}
