export type StudioThemeId = 'violet' | 'petrol' | 'ember';

export interface StudioThemeOption {
  id: StudioThemeId;
  label: string;
}

export const DEFAULT_THEME_ID: StudioThemeId = 'violet';

export const STUDIO_THEMES = [
  { id: 'violet', label: 'Violet' },
  { id: 'petrol', label: 'Petrol Noir' },
  { id: 'ember', label: 'Ember Alloy' },
] satisfies readonly [StudioThemeOption, ...StudioThemeOption[]];

export function isStudioThemeId(value: string | null): value is StudioThemeId {
  return STUDIO_THEMES.some((theme) => theme.id === value);
}
