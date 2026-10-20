import type { AudioSource, CreationMode, UiConfig, VoiceDetail } from '../lib/types';
import { ClonePane } from './creation/ClonePane';
import { DesignPane } from './creation/DesignPane';
import { RecordPane } from './creation/RecordPane';

interface CreationStudioProps {
  open: boolean;
  mode: CreationMode;
  config: UiConfig;
  errorMessage: string | null;
  onModeChange: (mode: CreationMode) => void;
  onClose: () => void;
  onBatchCreated: (preferredVoiceId: string | null) => Promise<void>;
  onCreated: (detail: VoiceDetail) => void;
  onError: (message: string | null) => void;
  onPlayReviewAudio: (source: AudioSource) => void;
}

function modeHeading(mode: CreationMode): string {
  if (mode === 'design') {
    return 'Design a fresh reference voice';
  }
  if (mode === 'clone') {
    return 'Clone from an existing recording';
  }
  return 'Record a voice live on this Mac';
}

function modeCopy(mode: CreationMode): string {
  if (mode === 'design') {
    return 'Describe the voice, give it a line, and save the result directly into the library.';
  }
  if (mode === 'clone') {
    return 'Upload a recording, review the transcript, then save the approved reference voice.';
  }
  return 'Capture a take, review the local transcript, and save it as a clone voice.';
}

export function CreationStudio({
  open,
  mode,
  config,
  errorMessage,
  onModeChange,
  onClose,
  onBatchCreated,
  onCreated,
  onError,
  onPlayReviewAudio,
}: CreationStudioProps) {
  if (!open) {
    return null;
  }

  return (
    <div className="studio-modal-shell" role="dialog" aria-modal="true">
      <div className="studio-modal">
        <aside className="creation-rail">
          <div className="creation-rail-copy">
            <h2>Build a new voice</h2>
          </div>
          <div className="creation-tabs">
            {(['design', 'clone', 'record'] as const).map((tab) => (
              <button
                key={tab}
                type="button"
                className={`creation-tab ${mode === tab ? 'is-active' : ''}`}
                onClick={() => onModeChange(tab)}
              >
                <strong>{tab === 'design' ? 'Design' : tab === 'clone' ? 'Clone file' : 'Record live'}</strong>
              </button>
            ))}
          </div>
        </aside>

        <div className="creation-main">
          <div className="modal-header">
            <div>
              <h3>{modeHeading(mode)}</h3>
              <p className="muted-copy">{modeCopy(mode)}</p>
            </div>
            <button type="button" className="text-button" onClick={onClose}>
              Close
            </button>
          </div>

          {errorMessage ? <p className="edge-message">{errorMessage}</p> : null}

          {mode === 'design' ? (
            <DesignPane
              config={config}
              onBatchCreated={onBatchCreated}
              onCreated={onCreated}
              onError={onError}
              onPlayReviewAudio={onPlayReviewAudio}
            />
          ) : null}
          {mode === 'clone' ? (
            <ClonePane config={config} onCreated={onCreated} onError={onError} onPlayReviewAudio={onPlayReviewAudio} />
          ) : null}
          {mode === 'record' ? (
            <RecordPane config={config} onCreated={onCreated} onError={onError} onPlayReviewAudio={onPlayReviewAudio} />
          ) : null}
        </div>
      </div>
    </div>
  );
}
