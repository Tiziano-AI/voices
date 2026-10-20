import type { StudioThemeId } from '../lib/themes';
import type { CreationMode } from '../lib/types';
import { ThemePicker } from './ThemePicker';

interface LaunchpadProps {
  theme: StudioThemeId;
  onThemeChange: (value: StudioThemeId) => void;
  onOpenCreate: (mode: CreationMode) => void;
}

export function Launchpad({ theme, onThemeChange, onOpenCreate }: LaunchpadProps) {
  return (
    <section className="launchpad">
      <div className="launchpad-utility">
        <ThemePicker value={theme} onChange={onThemeChange} />
      </div>
      <div className="launchpad-copy">
        <h1>Start by making a voice.</h1>
        <p className="muted-copy">Design one from text, clone one from audio, or record one now.</p>
      </div>
      <div className="launchpad-actions">
        <button type="button" className="primary-button" onClick={() => onOpenCreate('design')}>
          Design
        </button>
        <button type="button" className="ghost-button" onClick={() => onOpenCreate('clone')}>
          Clone file
        </button>
        <button type="button" className="ghost-button" onClick={() => onOpenCreate('record')}>
          Record live
        </button>
      </div>
    </section>
  );
}
