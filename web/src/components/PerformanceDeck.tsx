import type { StudioThemeId } from '../lib/themes';
import type {
  AudioSessionState,
  AudioSource,
  ComparedPerformance,
  PreviewClip,
  RenderArtifact,
  VoiceDetail,
} from '../lib/types';
import { ThemePicker } from './ThemePicker';

interface PerformanceDeckProps {
  detail: VoiceDetail | null;
  theme: StudioThemeId;
  scriptText: string;
  onScriptTextChange: (value: string) => void;
  previewClip: PreviewClip | null;
  outputReason: string | null;
  compareVoiceIds: string[];
  compareClips: ComparedPerformance[];
  compareArtifacts: Record<string, RenderArtifact>;
  previewBusy: boolean;
  compareBusy: boolean;
  renderBusy: boolean;
  compareRenderBusy: boolean;
  renderArtifact: RenderArtifact | null;
  edgeMessage: string | null;
  audioSession: AudioSessionState;
  onPreview: () => void;
  onCompare: () => void;
  onRender: () => void;
  onRenderCompareSet: () => void;
  onPlayAudio: (source: AudioSource) => void;
  onStopAudio: () => void;
  onOpenCreate: (mode: 'design' | 'clone' | 'record') => void;
  onOpenInspector: () => void;
  onThemeChange: (value: StudioThemeId) => void;
  onAuditionReference: () => void;
}

function comparePerformanceFor(voiceId: string, compareClips: ComparedPerformance[]): ComparedPerformance | null {
  return compareClips.find((performance) => performance.requestedInput.voice_id === voiceId) ?? null;
}

function audioStatusLabel(audioSession: AudioSessionState): string {
  if (!audioSession.source) {
    return 'Idle';
  }
  if (audioSession.status === 'loading') {
    return `Loading ${audioSession.source.label}`;
  }
  if (audioSession.status === 'playing') {
    return `Playing ${audioSession.source.label}`;
  }
  if (audioSession.status === 'blocked') {
    return `Blocked ${audioSession.source.label}`;
  }
  if (audioSession.status === 'error') {
    return `Error ${audioSession.source.label}`;
  }
  return `Paused ${audioSession.source.label}`;
}

export function PerformanceDeck({
  detail,
  theme,
  scriptText,
  onScriptTextChange,
  previewClip,
  outputReason,
  compareVoiceIds,
  compareClips,
  compareArtifacts,
  previewBusy,
  compareBusy,
  renderBusy,
  compareRenderBusy,
  renderArtifact,
  edgeMessage,
  audioSession,
  onPreview,
  onCompare,
  onRender,
  onRenderCompareSet,
  onPlayAudio,
  onStopAudio,
  onOpenCreate,
  onOpenInspector,
  onThemeChange,
  onAuditionReference,
}: PerformanceDeckProps) {
  const selectedName = detail?.summary.name ?? 'Choose a saved voice';
  const selectedDescription = detail?.summary.description ?? 'Pick a voice to audition a line.';
  const selectedVoiceId = detail?.summary.id ?? 'no-voice-selected';
  const hasClipOutput = previewClip !== null || renderArtifact !== null;
  const hasCompareOutput =
    compareVoiceIds.length > 0 || compareClips.length > 0 || Object.keys(compareArtifacts).length > 0;
  const displayedVoiceIds = [
    ...new Set([...compareVoiceIds, ...compareClips.map((item) => item.requestedInput.voice_id)]),
  ];
  const compareOriginal = compareClips.some((performance) => performance.freshnessReason !== null);

  return (
    <main className="performance-deck">
      <header className="workbench-header">
        <div className="workbench-title">
          <p className="eyebrow">Local voice studio</p>
          <h1>{selectedName}</h1>
          <p className="stage-description">{selectedDescription}</p>
          {detail ? (
            <div className="stage-meta-row">
              <span className="meta-chip">{detail.summary.language}</span>
              <span className="meta-chip">{detail.summary.source_kind}</span>
              <span className="meta-chip mono-chip">{selectedVoiceId}</span>
            </div>
          ) : null}
        </div>
        <div className="stage-toolbar">
          <ThemePicker value={theme} onChange={onThemeChange} />
          <div className="studio-command-row">
            <button type="button" className="text-button" onClick={() => onOpenCreate('design')}>
              Design
            </button>
            <button type="button" className="text-button" onClick={() => onOpenCreate('clone')}>
              Clone file
            </button>
            <button type="button" className="text-button" onClick={() => onOpenCreate('record')}>
              Record live
            </button>
            <button type="button" className="text-button" onClick={onOpenInspector} disabled={!detail}>
              Details
            </button>
          </div>
        </div>
      </header>

      <section className="audition-strip">
        <label className="script-editor">
          <span>Line</span>
          <textarea
            value={scriptText}
            onChange={(event) => onScriptTextChange(event.target.value)}
            placeholder="Type the line you want this voice to speak."
            rows={4}
          />
        </label>
        <div
          className="transport-panel"
          data-audio-status={audioSession.status}
          data-audio-source-kind={audioSession.source?.kind ?? 'none'}
          data-audio-source-id={audioSession.source?.id ?? 'none'}
        >
          <p className="eyebrow">Transport</p>
          <strong>{audioStatusLabel(audioSession)}</strong>
          {audioSession.message ? <span className="audio-message">{audioSession.message}</span> : null}
          <button
            type="button"
            className="micro-button"
            onClick={onStopAudio}
            disabled={audioSession.status === 'idle'}
          >
            Stop
          </button>
        </div>
      </section>

      <div className="action-row">
        <button
          type="button"
          className="primary-button"
          onClick={onPreview}
          disabled={!detail || previewBusy || renderBusy || !scriptText.trim()}
        >
          {previewBusy ? 'Generating…' : 'Play preview'}
        </button>
        <button
          type="button"
          className="ghost-button"
          onClick={onCompare}
          disabled={compareVoiceIds.length === 0 || compareBusy || compareRenderBusy || !scriptText.trim()}
        >
          {compareBusy ? 'Comparing…' : `Compare ${compareVoiceIds.length || ''}`.trim()}
        </button>
        <button
          type="button"
          className="ghost-button"
          onClick={onRender}
          disabled={renderBusy || previewBusy || (!previewClip && (!detail || !scriptText.trim()))}
        >
          {renderBusy
            ? 'Saving…'
            : previewClip
              ? outputReason
                ? 'Save original clip'
                : 'Save preview'
              : 'Render export'}
        </button>
        <button type="button" className="ghost-button" onClick={onAuditionReference} disabled={!detail}>
          Reference
        </button>
      </div>

      {edgeMessage ? <p className="edge-message">{edgeMessage}</p> : null}

      {hasClipOutput || hasCompareOutput ? (
        <section className="output-grid">
          {hasClipOutput ? (
            <article className="output-panel">
              <div className="panel-heading">
                <p className="eyebrow">{outputReason ? 'Original clip' : 'Current clip'}</p>
                {previewClip ? <span className="meta-chip">Ready</span> : null}
              </div>
              <p className="prose-copy">{previewClip?.input.text ?? renderArtifact?.record.text}</p>
              {outputReason ? <p className="muted-copy">Original clip · {outputReason}</p> : null}
              {previewClip ? (
                <button
                  type="button"
                  className="ghost-button"
                  onClick={() =>
                    onPlayAudio({
                      id: `preview:${previewClip.token}`,
                      kind: 'preview',
                      label: previewClip.voice_id,
                      url: previewClip.audio_url,
                    })
                  }
                >
                  Replay preview
                </button>
              ) : null}
              {renderArtifact ? (
                <div className="download-row">
                  <a href={renderArtifact.audio_url} download className="secondary-link">
                    Download WAV
                  </a>
                  <a href={renderArtifact.sidecar_url} download className="secondary-link">
                    Download JSON
                  </a>
                </div>
              ) : null}
            </article>
          ) : null}

          {hasCompareOutput ? (
            <article className="output-panel compare-panel">
              <div className="panel-heading">
                <p className="eyebrow">Compare</p>
                <span className="muted-copy">{compareVoiceIds.length} queued</span>
              </div>
              <div className="compare-lanes">
                {displayedVoiceIds.map((voiceId) => {
                  const performance = comparePerformanceFor(voiceId, compareClips);
                  const clip = performance?.clip;
                  const artifact = clip ? compareArtifacts[clip.token] : null;
                  return (
                    <article key={voiceId} className="compare-lane" data-voice-id={voiceId}>
                      <header className="compare-lane-header">
                        <strong>{voiceId}</strong>
                        <span>
                          {compareBusy && !clip
                            ? 'Generating'
                            : performance?.failureDetail
                              ? 'Failed'
                              : clip
                                ? 'Ready'
                                : 'Waiting'}
                        </span>
                      </header>
                      {performance?.failureDetail ? <p className="muted-copy">{performance.failureDetail}</p> : null}
                      {clip ? (
                        <p className="candidate-text" title={clip.input.text}>
                          {clip.input.text}
                        </p>
                      ) : null}
                      {performance?.freshnessReason ? (
                        <p className="muted-copy">Original clip · {performance.freshnessReason}</p>
                      ) : null}
                      {clip ? (
                        <button
                          type="button"
                          className="micro-button"
                          onClick={() =>
                            onPlayAudio({
                              id: `compare:${clip.token}`,
                              kind: 'compare',
                              label: voiceId,
                              url: clip.audio_url,
                            })
                          }
                        >
                          Play
                        </button>
                      ) : null}
                      {artifact ? (
                        <div className="download-row compact-download-row">
                          <a href={artifact.audio_url} download className="secondary-link">
                            WAV
                          </a>
                          <a href={artifact.sidecar_url} download className="secondary-link">
                            JSON
                          </a>
                        </div>
                      ) : null}
                    </article>
                  );
                })}
              </div>
              <div className="compare-footer">
                <button
                  type="button"
                  className="ghost-button"
                  onClick={onRenderCompareSet}
                  disabled={
                    compareRenderBusy ||
                    compareBusy ||
                    compareClips.length === 0 ||
                    compareClips.some((performance) => !performance.clip)
                  }
                >
                  {compareRenderBusy
                    ? 'Saving…'
                    : compareOriginal
                      ? 'Save original compared clips'
                      : 'Save compared clips'}
                </button>
              </div>
            </article>
          ) : null}
        </section>
      ) : null}
    </main>
  );
}
