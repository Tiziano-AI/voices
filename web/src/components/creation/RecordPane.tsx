import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { type RecorderMode, useRecorder } from '../../hooks/useRecorder';
import { reviewClone, saveClone } from '../../lib/api';
import type { CloneReviewDraft } from '../../lib/types';
import { type CreationPaneProps, displayNameFromVoiceId } from './shared';

function takeFilename(blob: Blob): string {
  const extension = blob.type.includes('mp4') ? 'mp4' : blob.type.includes('ogg') ? 'ogg' : 'webm';
  return `recorded-take.${extension}`;
}

export function RecordPane({ config, onCreated, onError, onPlayReviewAudio }: CreationPaneProps) {
  const { audioBlob, consumeAudioBlob, elapsedSeconds, error, isRecording, level, reset, start, status, stop } =
    useRecorder();
  const [recordLanguage, setRecordLanguage] = useState(config.default_language);
  const [recordName, setRecordName] = useState('');
  const [recordVoiceId, setRecordVoiceId] = useState('');
  const [recordOverwrite, setRecordOverwrite] = useState(false);
  const [recordMode, setRecordMode] = useState<RecorderMode>('guided');
  const [customGuidedScript, setCustomGuidedScript] = useState(false);
  const [guidedScript, setGuidedScript] = useState(config.guided_scripts[config.default_language] ?? '');
  const [recordReview, setRecordReview] = useState<CloneReviewDraft | null>(null);
  const [recordReviewName, setRecordReviewName] = useState('');
  const [recordReviewVoiceId, setRecordReviewVoiceId] = useState('');
  const [recordReviewTranscript, setRecordReviewTranscript] = useState('');
  const [recordSaveBusy, setRecordSaveBusy] = useState(false);
  const [recordReviewBusy, setRecordReviewBusy] = useState(false);
  const [recordErrorMessage, setRecordErrorMessage] = useState<string | null>(null);
  const [takeUrl, setTakeUrl] = useState<string | null>(null);
  const reviewRequestIdRef = useRef(0);
  const saveRequestIdRef = useRef(0);
  const saveAbortControllerRef = useRef<AbortController | null>(null);
  const recordLanguageRef = useRef(recordLanguage);
  const recordModeRef = useRef(recordMode);
  const recordNameRef = useRef(recordName);
  const recordVoiceIdRef = useRef(recordVoiceId);

  useEffect(() => {
    recordLanguageRef.current = recordLanguage;
    recordModeRef.current = recordMode;
    recordNameRef.current = recordName;
    recordVoiceIdRef.current = recordVoiceId;
  }, [recordLanguage, recordMode, recordName, recordVoiceId]);

  useEffect(() => {
    if (!customGuidedScript) {
      setGuidedScript(config.guided_scripts[recordLanguage] ?? '');
    }
  }, [config.guided_scripts, customGuidedScript, recordLanguage]);

  useEffect(
    () => () => {
      reviewRequestIdRef.current += 1;
      saveRequestIdRef.current += 1;
      saveAbortControllerRef.current?.abort();
      saveAbortControllerRef.current = null;
    },
    [],
  );

  useEffect(() => {
    if (!audioBlob) {
      setTakeUrl(null);
      return;
    }
    const url = URL.createObjectURL(audioBlob);
    setTakeUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [audioBlob]);

  const reviewRecordedTake = useCallback(async () => {
    if (audioBlob === null) {
      return;
    }

    reviewRequestIdRef.current += 1;
    const requestId = reviewRequestIdRef.current;
    const reviewLanguage = recordLanguageRef.current;
    const reviewMode = recordModeRef.current;
    const reviewName = recordNameRef.current;
    const reviewVoiceId = recordVoiceIdRef.current;

    setRecordReviewBusy(true);
    setRecordErrorMessage(null);
    onError(null);
    try {
      const recordedFile = new File([audioBlob], takeFilename(audioBlob), {
        type: audioBlob.type || 'audio/webm',
      });
      const review = await reviewClone({
        file: recordedFile,
        language: reviewLanguage,
        reviewPolicy: reviewMode === 'guided' ? 'record_guided' : 'record_free',
        transcript: null,
        name: reviewName || null,
        voiceId: reviewVoiceId || null,
      });
      if (requestId !== reviewRequestIdRef.current) {
        return;
      }
      setRecordReview(review);
      setRecordReviewVoiceId(review.suggested_voice_id);
      setRecordReviewName(reviewName || displayNameFromVoiceId(review.suggested_voice_id));
      setRecordReviewTranscript(review.transcript);
      consumeAudioBlob();
    } catch (error) {
      if (requestId !== reviewRequestIdRef.current) {
        return;
      }
      const detail = error instanceof Error ? error.message : 'Unable to review the recorded take.';
      setRecordErrorMessage(detail);
      onError(detail);
    } finally {
      if (requestId === reviewRequestIdRef.current) {
        setRecordReviewBusy(false);
      }
    }
  }, [audioBlob, consumeAudioBlob, onError]);

  useEffect(() => {
    void reviewRecordedTake();
  }, [reviewRecordedTake]);

  const guidedLimit = config.guided_record_target_seconds;
  const recorderModeLabel = useMemo(() => (recordMode === 'guided' ? 'Guided read' : 'Free take'), [recordMode]);
  const recordStartDisabled =
    status === 'requesting' || status === 'processing' || audioBlob !== null || recordReviewBusy || recordSaveBusy;
  const recordResetDisabled = isRecording || recordReviewBusy || recordSaveBusy;
  const captureSettingsDisabled = status === 'requesting' || isRecording || audioBlob !== null;

  const handleRecordStart = async () => {
    if (recordStartDisabled) {
      return;
    }
    setRecordErrorMessage(null);
    onError(null);
    await start({ mode: recordMode, limitSeconds: guidedLimit });
  };

  const handleRecordSave = async () => {
    if (!recordReview) {
      return;
    }
    saveRequestIdRef.current += 1;
    const requestId = saveRequestIdRef.current;
    const abortController = new AbortController();
    saveAbortControllerRef.current = abortController;
    setRecordSaveBusy(true);
    setRecordErrorMessage(null);
    onError(null);
    try {
      const detail = await saveClone({
        reviewToken: recordReview.review_token,
        voiceId: recordReviewVoiceId,
        name: recordReviewName,
        transcript: recordReviewTranscript,
        overwrite: recordOverwrite,
        signal: abortController.signal,
      });
      if (requestId !== saveRequestIdRef.current) {
        return;
      }
      onCreated(detail);
    } catch (error) {
      if (requestId !== saveRequestIdRef.current) {
        return;
      }
      const detail = error instanceof Error ? error.message : 'Unable to save the recorded voice.';
      setRecordErrorMessage(detail);
      onError(detail);
    } finally {
      if (saveAbortControllerRef.current === abortController) {
        saveAbortControllerRef.current = null;
      }
      if (requestId === saveRequestIdRef.current) {
        setRecordSaveBusy(false);
      }
    }
  };

  if (!recordReview) {
    return (
      <section className="creation-body">
        <div className="form-grid-two">
          <label>
            <span>Name</span>
            <input value={recordName} onChange={(event) => setRecordName(event.target.value)} placeholder="Optional" />
          </label>
          <label>
            <span>Language</span>
            <select
              value={recordLanguage}
              onChange={(event) => setRecordLanguage(event.target.value)}
              disabled={captureSettingsDisabled}
            >
              {config.supported_languages.map((language) => (
                <option key={language} value={language}>
                  {language}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="form-grid-two">
          <label>
            <span>Voice id</span>
            <input
              value={recordVoiceId}
              onChange={(event) => setRecordVoiceId(event.target.value)}
              placeholder="Optional"
            />
          </label>
          <label>
            <span>Capture mode</span>
            <select
              value={recordMode}
              onChange={(event) => setRecordMode(event.target.value as RecorderMode)}
              disabled={captureSettingsDisabled}
            >
              <option value="guided">Guided</option>
              <option value="free">Free</option>
            </select>
          </label>
        </div>
        <label className="checkbox-row">
          <input
            type="checkbox"
            checked={recordOverwrite}
            onChange={(event) => setRecordOverwrite(event.target.checked)}
          />
          <span>Overwrite existing voice</span>
        </label>
        {recordMode === 'guided' ? (
          <div className="guided-script-panel">
            <div className="script-header">
              <span>Guided script</span>
              <label className="checkbox-row compact-checkbox">
                <input
                  type="checkbox"
                  checked={customGuidedScript}
                  onChange={(event) => setCustomGuidedScript(event.target.checked)}
                  disabled={captureSettingsDisabled}
                />
                <span>Custom</span>
              </label>
            </div>
            <textarea
              value={guidedScript}
              onChange={(event) => setGuidedScript(event.target.value)}
              rows={6}
              disabled={!customGuidedScript || captureSettingsDisabled}
            />
            <p className="muted-copy">Auto-stops after {guidedLimit.toFixed(0)}s.</p>
          </div>
        ) : (
          <p className="muted-copy">
            Free mode records until you stop. Takes under {config.free_record_minimum_seconds.toFixed(0)}s are rejected.
          </p>
        )}
        <div className="record-panel">
          <div className="record-readout">
            <span>{recorderModeLabel}</span>
            <strong>{elapsedSeconds.toFixed(1)}s</strong>
          </div>
          <div className="level-meter" aria-hidden="true">
            <div className="level-meter-fill" style={{ width: `${Math.max(level * 100, 4)}%` }} />
          </div>
          <div className="primary-action-row">
            {isRecording ? (
              <button type="button" className="primary-button" onClick={stop}>
                Stop
              </button>
            ) : (
              <button
                type="button"
                className="primary-button"
                onClick={() => void handleRecordStart()}
                disabled={recordStartDisabled}
              >
                {status === 'requesting' ? 'Requesting mic…' : 'Start recording'}
              </button>
            )}
            <button
              type="button"
              className="ghost-button"
              onClick={() => {
                setRecordErrorMessage(null);
                reset();
              }}
              disabled={recordResetDisabled}
            >
              Reset
            </button>
          </div>
        </div>
        {error ? <p className="edge-message">{error}</p> : null}
        {recordErrorMessage ? <p className="edge-message">{recordErrorMessage}</p> : null}
        {audioBlob && recordErrorMessage && !recordReviewBusy ? (
          <div className="review-panel">
            <p className="muted-copy">
              Your take is kept while this recording panel stays open. Retry review without recording again, download
              it, or reset to discard it.
            </p>
            <div className="primary-action-row">
              <button type="button" className="primary-button" onClick={() => void reviewRecordedTake()}>
                Retry review
              </button>
              {takeUrl ? (
                <a className="ghost-button" href={takeUrl} download={takeFilename(audioBlob)}>
                  Download take
                </a>
              ) : null}
            </div>
          </div>
        ) : null}
        {recordReviewBusy ? <p className="muted-copy">Preparing transcript review…</p> : null}
      </section>
    );
  }

  return (
    <section className="creation-body">
      <div className="review-panel">
        <button
          type="button"
          className="ghost-button"
          onClick={() =>
            onPlayReviewAudio({
              id: `review:${recordReview.review_token}`,
              kind: 'review',
              label: recordReviewName || recordReview.suggested_voice_id,
              url: recordReview.audio_url,
            })
          }
        >
          Play take
        </button>
        <p className="muted-copy">Listen, edit the transcript if needed, then save it as a clone voice.</p>
      </div>
      <div className="form-grid-two">
        <label>
          <span>Name</span>
          <input value={recordReviewName} onChange={(event) => setRecordReviewName(event.target.value)} />
        </label>
        <label>
          <span>Voice id</span>
          <input value={recordReviewVoiceId} onChange={(event) => setRecordReviewVoiceId(event.target.value)} />
        </label>
      </div>
      <label>
        <span>Transcript</span>
        <textarea
          value={recordReviewTranscript}
          onChange={(event) => setRecordReviewTranscript(event.target.value)}
          rows={5}
        />
      </label>
      {recordErrorMessage ? <p className="edge-message">{recordErrorMessage}</p> : null}
      <div className="segment-list">
        {recordReview.segments.map((segment) => (
          <div key={`${segment.start}-${segment.end}-${segment.text}`} className="segment-row">
            <span>{segment.start.toFixed(1)}s</span>
            <span>{segment.end.toFixed(1)}s</span>
            <span>{segment.text}</span>
          </div>
        ))}
      </div>
      <div className="primary-action-row">
        <button
          type="button"
          className="ghost-button"
          onClick={() => {
            saveRequestIdRef.current += 1;
            saveAbortControllerRef.current?.abort();
            saveAbortControllerRef.current = null;
            setRecordSaveBusy(false);
            setRecordErrorMessage(null);
            setRecordReview(null);
            setRecordReviewName('');
            setRecordReviewVoiceId('');
            setRecordReviewTranscript('');
            reset();
          }}
        >
          Retry
        </button>
        <button type="button" className="primary-button" onClick={handleRecordSave} disabled={recordSaveBusy}>
          {recordSaveBusy ? 'Saving…' : 'Save recording'}
        </button>
      </div>
    </section>
  );
}
