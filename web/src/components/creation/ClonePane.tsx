import { useEffect, useRef, useState } from 'react';

import { reviewClone, saveClone } from '../../lib/api';
import type { CloneReviewDraft } from '../../lib/types';
import { type CreationPaneProps, displayNameFromVoiceId } from './shared';

export function ClonePane({ config, onCreated, onError, onPlayReviewAudio }: CreationPaneProps) {
  const [cloneFile, setCloneFile] = useState<File | null>(null);
  const [cloneLanguage, setCloneLanguage] = useState(config.default_language);
  const [cloneName, setCloneName] = useState('');
  const [cloneVoiceId, setCloneVoiceId] = useState('');
  const [cloneTranscript, setCloneTranscript] = useState('');
  const [cloneOverwrite, setCloneOverwrite] = useState(false);
  const [cloneBusy, setCloneBusy] = useState(false);
  const [cloneReview, setCloneReview] = useState<CloneReviewDraft | null>(null);
  const [reviewName, setReviewName] = useState('');
  const [reviewVoiceId, setReviewVoiceId] = useState('');
  const [reviewTranscript, setReviewTranscript] = useState('');
  const [saveBusy, setSaveBusy] = useState(false);
  const reviewRequestIdRef = useRef(0);
  const saveRequestIdRef = useRef(0);
  const saveAbortControllerRef = useRef<AbortController | null>(null);

  useEffect(
    () => () => {
      reviewRequestIdRef.current += 1;
      saveRequestIdRef.current += 1;
      saveAbortControllerRef.current?.abort();
      saveAbortControllerRef.current = null;
    },
    [],
  );

  const handleCloneReview = async () => {
    if (!cloneFile) {
      onError('Choose an audio file first.');
      return;
    }
    reviewRequestIdRef.current += 1;
    const requestId = reviewRequestIdRef.current;
    setCloneBusy(true);
    onError(null);
    try {
      const review = await reviewClone({
        file: cloneFile,
        language: cloneLanguage,
        reviewPolicy: 'import',
        transcript: cloneTranscript || null,
        name: cloneName || null,
        voiceId: cloneVoiceId || null,
      });
      if (requestId !== reviewRequestIdRef.current) {
        return;
      }
      setCloneReview(review);
      setReviewVoiceId(review.suggested_voice_id);
      setReviewName(cloneName || displayNameFromVoiceId(review.suggested_voice_id));
      setReviewTranscript(review.transcript);
    } catch (error) {
      if (requestId !== reviewRequestIdRef.current) {
        return;
      }
      onError(error instanceof Error ? error.message : 'Unable to review the clone source.');
    } finally {
      if (requestId === reviewRequestIdRef.current) {
        setCloneBusy(false);
      }
    }
  };

  const handleCloneSave = async () => {
    if (!cloneReview) {
      return;
    }
    saveRequestIdRef.current += 1;
    const requestId = saveRequestIdRef.current;
    const abortController = new AbortController();
    saveAbortControllerRef.current = abortController;
    setSaveBusy(true);
    onError(null);
    try {
      const detail = await saveClone({
        reviewToken: cloneReview.review_token,
        voiceId: reviewVoiceId,
        name: reviewName,
        transcript: reviewTranscript,
        overwrite: cloneOverwrite,
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
      onError(error instanceof Error ? error.message : 'Unable to save the cloned voice.');
    } finally {
      if (saveAbortControllerRef.current === abortController) {
        saveAbortControllerRef.current = null;
      }
      if (requestId === saveRequestIdRef.current) {
        setSaveBusy(false);
      }
    }
  };

  if (!cloneReview) {
    return (
      <section className="creation-body">
        <label>
          <span>Audio file</span>
          <input type="file" accept="audio/*" onChange={(event) => setCloneFile(event.target.files?.[0] ?? null)} />
        </label>
        <div className="form-grid-two">
          <label>
            <span>Name</span>
            <input value={cloneName} onChange={(event) => setCloneName(event.target.value)} placeholder="Optional" />
          </label>
          <label>
            <span>Language</span>
            <select value={cloneLanguage} onChange={(event) => setCloneLanguage(event.target.value)}>
              {config.supported_languages.map((language) => (
                <option key={language} value={language}>
                  {language}
                </option>
              ))}
            </select>
          </label>
        </div>
        <label>
          <span>Transcript</span>
          <textarea
            value={cloneTranscript}
            onChange={(event) => setCloneTranscript(event.target.value)}
            placeholder="Leave blank to run local STT first."
            rows={4}
          />
        </label>
        <label>
          <span>Voice id</span>
          <input
            value={cloneVoiceId}
            onChange={(event) => setCloneVoiceId(event.target.value)}
            placeholder="Optional"
          />
        </label>
        <label className="checkbox-row">
          <input
            type="checkbox"
            checked={cloneOverwrite}
            onChange={(event) => setCloneOverwrite(event.target.checked)}
          />
          <span>Overwrite existing voice</span>
        </label>
        <button type="button" className="primary-button" onClick={handleCloneReview} disabled={cloneBusy}>
          {cloneBusy ? 'Reviewing…' : 'Review transcript'}
        </button>
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
              id: `review:${cloneReview.review_token}`,
              kind: 'review',
              label: reviewName || cloneReview.suggested_voice_id,
              url: cloneReview.audio_url,
            })
          }
        >
          Play source
        </button>
        <p className="muted-copy">Listen, edit the transcript if needed, then save the clone voice.</p>
      </div>
      <div className="form-grid-two">
        <label>
          <span>Name</span>
          <input value={reviewName} onChange={(event) => setReviewName(event.target.value)} />
        </label>
        <label>
          <span>Voice id</span>
          <input value={reviewVoiceId} onChange={(event) => setReviewVoiceId(event.target.value)} />
        </label>
      </div>
      <label>
        <span>Transcript</span>
        <textarea value={reviewTranscript} onChange={(event) => setReviewTranscript(event.target.value)} rows={5} />
      </label>
      <div className="segment-list">
        {cloneReview.segments.map((segment) => (
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
            setSaveBusy(false);
            onError(null);
            setCloneReview(null);
            setReviewName('');
            setReviewVoiceId('');
            setReviewTranscript('');
          }}
        >
          Retry
        </button>
        <button type="button" className="primary-button" onClick={handleCloneSave} disabled={saveBusy}>
          {saveBusy ? 'Saving…' : 'Save clone'}
        </button>
      </div>
    </section>
  );
}
