import type { ChangeEvent } from 'react';

import { isStudioThemeId, STUDIO_THEMES, type StudioThemeId } from '../lib/themes';

interface ThemePickerProps {
  value: StudioThemeId;
  onChange: (value: StudioThemeId) => void;
}

export function ThemePicker({ value, onChange }: ThemePickerProps) {
  const handleChange = (event: ChangeEvent<HTMLSelectElement>) => {
    const nextTheme = event.target.value;
    if (isStudioThemeId(nextTheme)) {
      onChange(nextTheme);
    }
  };

  return (
    <div className="theme-picker-shell">
      <label className="theme-picker-field">
        <span className="eyebrow">Palette</span>
        <div className="theme-picker-row">
          <span className="theme-swatch" aria-hidden="true" />
          <select aria-label="Palette" value={value} onChange={handleChange}>
            {STUDIO_THEMES.map((theme) => (
              <option key={theme.id} value={theme.id}>
                {theme.label}
              </option>
            ))}
          </select>
        </div>
      </label>
    </div>
  );
}
