import { type CSSProperties, type PointerEvent, useCallback, useMemo, useRef, useState } from 'react';

import {
  AUDITION_BOARD_PADDING,
  AUDITION_CARD_HEIGHT,
  AUDITION_CARD_WIDTH,
  type AuditionBoardActions,
  type AuditionBoardState,
  type BoardCandidate,
} from '../hooks/useAuditionBoard';
import type { AudioSessionState } from '../lib/types';

interface AuditionBoardProps {
  state: AuditionBoardState;
  actions: AuditionBoardActions;
  languageOptions: string[];
  audioSession: AudioSessionState;
}

interface DragState {
  id: string;
  startX: number;
  startY: number;
  pointerX: number;
  pointerY: number;
}

function displayStatus(candidate: BoardCandidate, audioSession: AudioSessionState): string {
  if (candidate.saveStatus === 'saving') return 'saving';
  if (candidate.generationStatus === 'pending') return 'generating';
  if (candidate.generationStatus === 'failed') return 'error';
  if (!candidate.current) return 'stale';
  if (audioSession.source?.kind === 'board' && audioSession.source.id === candidate.id) {
    if (audioSession.status === 'playing' || audioSession.status === 'blocked') return audioSession.status;
  }
  return candidate.saveStatus === 'saved' ? 'saved' : 'ready';
}

export function AuditionBoard({ state, actions, languageOptions, audioSession }: AuditionBoardProps) {
  const boardRef = useRef<HTMLDivElement>(null);
  const [drag, setDrag] = useState<DragState | null>(null);
  const candidateCount = state.targetCount;
  const generateLabel = useMemo(() => {
    if (state.busy) {
      return 'Generating…';
    }
    if (state.nextBatchSize === 0) {
      return state.failedCount > 0 ? 'All attempted' : 'Complete';
    }
    if (candidateCount > state.generationLimit) {
      return state.currentCount > 0 || state.failedCount > 0
        ? `Generate next ${state.nextBatchSize}`
        : `Generate ${state.nextBatchSize} of ${candidateCount}`;
    }
    return `Generate ${state.nextBatchSize}`;
  }, [candidateCount, state.busy, state.currentCount, state.failedCount, state.generationLimit, state.nextBatchSize]);
  const boardHeight = Math.max(
    360,
    ...state.candidates.map((candidate) => candidate.position.y + AUDITION_CARD_HEIGHT + AUDITION_BOARD_PADDING),
  );

  const startDrag = useCallback((candidate: BoardCandidate, event: PointerEvent<HTMLButtonElement>) => {
    if (event.button !== 0) {
      return;
    }
    event.currentTarget.setPointerCapture(event.pointerId);
    setDrag({
      id: candidate.id,
      startX: candidate.position.x,
      startY: candidate.position.y,
      pointerX: event.clientX,
      pointerY: event.clientY,
    });
  }, []);

  const moveDrag = useCallback(
    (event: PointerEvent<HTMLDivElement>) => {
      if (!drag) {
        return;
      }
      actions.moveCandidate(drag.id, {
        x: drag.startX + event.clientX - drag.pointerX,
        y: drag.startY + event.clientY - drag.pointerY,
      });
    },
    [actions, drag],
  );

  const stopDrag = useCallback(() => {
    setDrag(null);
  }, []);

  return (
    <section className="audition-board" aria-label="Audition Board">
      <header className="board-header">
        <div>
          <p className="eyebrow">Audition board</p>
          <h2>Generate, listen, group.</h2>
        </div>
        <div className="board-stats">
          <span>{state.candidates.length} clips</span>
          <span>{candidateCount} voices</span>
          {candidateCount > state.generationLimit ? <span>{state.generationLimit}/batch</span> : null}
        </div>
      </header>

      <div className="board-controls">
        <label className="board-text">
          <span>Audition text</span>
          <textarea
            value={state.text}
            onChange={(event) => actions.setText(event.target.value)}
            placeholder="Type the line to audition across voices."
            rows={3}
          />
        </label>
        <div className="board-actions">
          <button type="button" className="ghost-button" onClick={actions.syncFromScript}>
            Use line
          </button>
          <button
            type="button"
            className="primary-button"
            onClick={() => void actions.generate()}
            disabled={state.busy || !state.text.trim() || state.nextBatchSize === 0}
          >
            {generateLabel}
          </button>
        </div>
      </div>

      <fieldset className="board-filter-row">
        <legend className="sr-only">Audition language filter</legend>
        <button
          type="button"
          className={`micro-button ${state.languageFilter === 'all' ? 'is-active' : ''}`}
          onClick={() => actions.setLanguageFilter('all')}
        >
          All
        </button>
        {languageOptions.map((language) => (
          <button
            key={language}
            type="button"
            className={`micro-button ${state.languageFilter === language ? 'is-active' : ''}`}
            onClick={() => actions.setLanguageFilter(language)}
          >
            {language}
          </button>
        ))}
        <span className="board-filter-spacer" />
        <button type="button" className="ghost-button" onClick={() => void actions.refresh()}>
          Refresh voices
        </button>
        <button
          type="button"
          className="ghost-button"
          onClick={actions.resetLayout}
          disabled={state.candidates.length === 0}
        >
          Fit grid
        </button>
        <button
          type="button"
          className="ghost-button"
          onClick={actions.clear}
          disabled={state.saving || (state.candidates.length === 0 && !state.busy)}
        >
          Clear
        </button>
      </fieldset>

      <p className="board-progress" role="status">
        {state.currentCount} ready. {state.pendingCount} pending. {state.failedCount} failed. {state.unattemptedCount}{' '}
        unattempted.
      </p>
      <p className="edge-message" role="alert">
        {state.message}
      </p>

      <div
        ref={boardRef}
        className="audition-canvas"
        style={
          {
            '--audition-card-height': `${AUDITION_CARD_HEIGHT}px`,
            '--audition-card-width': `${AUDITION_CARD_WIDTH}px`,
            '--board-height': `${boardHeight}px`,
          } as CSSProperties
        }
        onPointerMove={moveDrag}
        onPointerUp={stopDrag}
        onPointerLeave={stopDrag}
      >
        {state.candidates.length === 0 && !state.busy ? (
          <div className="board-empty">
            <strong>No clips yet.</strong>
            <span>Generate a line, then drag candidates into your own similarity map.</span>
          </div>
        ) : null}

        {state.candidates.map((candidate) => {
          const status = displayStatus(candidate, audioSession);
          return (
            <article
              key={candidate.id}
              className={`audition-card is-${status}`}
              data-clip-id={candidate.id}
              data-status={status}
              data-current={candidate.current}
              data-generation={candidate.generationStatus}
              data-save={candidate.saveStatus}
              style={
                {
                  '--card-x': `${candidate.position.x}px`,
                  '--card-y': `${candidate.position.y}px`,
                } as CSSProperties
              }
            >
              <header className="audition-card-header">
                <button
                  type="button"
                  className="drag-handle"
                  aria-label={`Move ${candidate.voiceName}`}
                  onPointerDown={(event) => startDrag(candidate, event)}
                >
                  ⠿
                </button>
                <div>
                  <strong>{candidate.voiceName}</strong>
                  <span>{candidate.requestedInput.voice_id}</span>
                </div>
                <button
                  type="button"
                  className="icon-button"
                  aria-label={`Remove ${candidate.voiceName}`}
                  onClick={() => actions.removeCandidate(candidate.id)}
                  disabled={candidate.saveStatus === 'saving'}
                >
                  ×
                </button>
              </header>

              <div className="candidate-meta">
                <span>{candidate.clip?.input.language ?? candidate.requestedInput.language}</span>
                <span>
                  {candidate.generationStatus === 'pending'
                    ? 'Generating'
                    : candidate.generationStatus === 'failed'
                      ? 'Failed'
                      : 'Ready'}
                  {candidate.saveStatus === 'saving' ? ' · Saving' : candidate.saveStatus === 'saved' ? ' · Saved' : ''}
                </span>
              </div>
              <p className="candidate-text" title={candidate.clip?.input.text ?? candidate.requestedInput.text}>
                {candidate.clip?.input.text ?? candidate.requestedInput.text}
              </p>
              {!candidate.current ? (
                <p className="candidate-freshness">Original clip · {candidate.freshnessReason}</p>
              ) : null}
              {candidate.generationError || candidate.saveError ? (
                <p className="candidate-error">{candidate.generationError ?? candidate.saveError}</p>
              ) : null}

              <div className="candidate-actions">
                <button
                  type="button"
                  className="micro-button"
                  onClick={() => void actions.playCandidate(candidate.id)}
                  disabled={!candidate.clip && !candidate.renderArtifact}
                >
                  Play
                </button>
                <button
                  type="button"
                  className="micro-button"
                  onClick={() => void actions.renderCandidate(candidate.id)}
                  disabled={!candidate.clip || candidate.saveStatus === 'saving'}
                >
                  {candidate.saveStatus === 'saving'
                    ? 'Saving…'
                    : candidate.current
                      ? 'Save clip'
                      : 'Save original clip'}
                </button>
                {candidate.generationStatus === 'failed' && candidate.current ? (
                  <button
                    type="button"
                    className="micro-button"
                    disabled={state.busy}
                    onClick={() => void actions.retryCandidate(candidate.id)}
                  >
                    Retry
                  </button>
                ) : null}
              </div>

              {candidate.renderArtifact ? (
                <div className="candidate-links">
                  <a href={candidate.renderArtifact.audio_url} download>
                    WAV
                  </a>
                  <a href={candidate.renderArtifact.sidecar_url} download>
                    JSON
                  </a>
                </div>
              ) : null}
            </article>
          );
        })}
      </div>
    </section>
  );
}
