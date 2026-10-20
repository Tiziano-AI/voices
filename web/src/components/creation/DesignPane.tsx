import { useEffect, useRef, useState } from 'react';

import { batchDesignVoicePack, cancelOperation, designVoice } from '../../lib/api';
import type { BatchDesignResult } from '../../lib/types';
import type { CreationPaneProps } from './shared';

interface DesignPaneProps extends CreationPaneProps {
  onBatchCreated: (preferredVoiceId: string | null) => Promise<void>;
}

function cancelOperationToken(operationToken: string, onError: (message: string | null) => void) {
  void cancelOperation(operationToken).catch((error: unknown) => {
    onError(error instanceof Error ? error.message : 'Unable to cancel the in-flight request.');
  });
}

export function DesignPane({ config, onBatchCreated, onCreated, onError }: DesignPaneProps) {
  const [designName, setDesignName] = useState('');
  const [designVoiceId, setDesignVoiceId] = useState('');
  const [designInstruct, setDesignInstruct] = useState('');
  const [designText, setDesignText] = useState('');
  const [designLanguage, setDesignLanguage] = useState(config.default_language);
  const [designOverwrite, setDesignOverwrite] = useState(false);
  const [designBusy, setDesignBusy] = useState(false);
  const [showBatch, setShowBatch] = useState(false);
  const [batchFile, setBatchFile] = useState<File | null>(null);
  const [batchText, setBatchText] = useState('');
  const [batchLanguage, setBatchLanguage] = useState(config.default_language);
  const [batchOverwrite, setBatchOverwrite] = useState(false);
  const [batchDryRun, setBatchDryRun] = useState(true);
  const [batchBusy, setBatchBusy] = useState(false);
  const [batchResult, setBatchResult] = useState<BatchDesignResult | null>(null);
  const designRequestIdRef = useRef(0);
  const batchRequestIdRef = useRef(0);
  const designAbortRef = useRef<AbortController | null>(null);
  const batchAbortRef = useRef<AbortController | null>(null);
  const designOperationTokenRef = useRef<string | null>(null);
  const batchOperationTokenRef = useRef<string | null>(null);

  useEffect(() => {
    setDesignLanguage(config.default_language);
    setBatchLanguage(config.default_language);
  }, [config.default_language]);

  useEffect(
    () => () => {
      designRequestIdRef.current += 1;
      batchRequestIdRef.current += 1;
      designAbortRef.current?.abort();
      batchAbortRef.current?.abort();
      if (designOperationTokenRef.current) {
        cancelOperationToken(designOperationTokenRef.current, onError);
        designOperationTokenRef.current = null;
      }
      if (batchOperationTokenRef.current) {
        cancelOperationToken(batchOperationTokenRef.current, onError);
        batchOperationTokenRef.current = null;
      }
    },
    [onError],
  );

  const handleDesignSubmit = async () => {
    designRequestIdRef.current += 1;
    const requestId = designRequestIdRef.current;
    designAbortRef.current?.abort();
    if (designOperationTokenRef.current) {
      cancelOperationToken(designOperationTokenRef.current, onError);
    }
    const operationToken = globalThis.crypto.randomUUID();
    designOperationTokenRef.current = operationToken;
    const abortController = new AbortController();
    designAbortRef.current = abortController;
    setDesignBusy(true);
    onError(null);
    try {
      const detail = await designVoice({
        name: designName,
        voiceId: designVoiceId || null,
        instruct: designInstruct,
        text: designText,
        language: designLanguage,
        overwrite: designOverwrite,
        operationToken,
        signal: abortController.signal,
      });
      if (requestId !== designRequestIdRef.current) {
        return;
      }
      onCreated(detail);
    } catch (error) {
      if (abortController.signal.aborted) {
        return;
      }
      if (requestId !== designRequestIdRef.current) {
        return;
      }
      onError(error instanceof Error ? error.message : 'Unable to design the voice.');
    } finally {
      if (requestId === designRequestIdRef.current) {
        setDesignBusy(false);
      }
      if (designAbortRef.current === abortController) {
        designAbortRef.current = null;
      }
      if (designOperationTokenRef.current === operationToken) {
        designOperationTokenRef.current = null;
      }
    }
  };

  const handleBatchDesign = async () => {
    if (!batchFile) {
      onError('Choose a prompt pack before running batch design.');
      return;
    }
    batchRequestIdRef.current += 1;
    const requestId = batchRequestIdRef.current;
    batchAbortRef.current?.abort();
    if (batchOperationTokenRef.current) {
      cancelOperationToken(batchOperationTokenRef.current, onError);
    }
    const operationToken = globalThis.crypto.randomUUID();
    batchOperationTokenRef.current = operationToken;
    const abortController = new AbortController();
    batchAbortRef.current = abortController;
    setBatchBusy(true);
    onError(null);
    try {
      const result = await batchDesignVoicePack({
        file: batchFile,
        language: batchLanguage,
        text: batchText,
        overwrite: batchOverwrite,
        dryRun: batchDryRun,
        operationToken,
        signal: abortController.signal,
      });
      if (requestId !== batchRequestIdRef.current) {
        return;
      }
      setBatchResult(result);
      if (!result.dry_run) {
        const createdRows = result.rows.filter((row) => row.status === 'ok');
        if (createdRows.length > 0) {
          await onBatchCreated(createdRows[createdRows.length - 1]?.voice_id ?? null);
        }
      }
    } catch (error) {
      if (abortController.signal.aborted) {
        return;
      }
      if (requestId !== batchRequestIdRef.current) {
        return;
      }
      onError(error instanceof Error ? error.message : 'Unable to run batch design.');
    } finally {
      if (requestId === batchRequestIdRef.current) {
        setBatchBusy(false);
      }
      if (batchAbortRef.current === abortController) {
        batchAbortRef.current = null;
      }
      if (batchOperationTokenRef.current === operationToken) {
        batchOperationTokenRef.current = null;
      }
    }
  };

  return (
    <section className="creation-body">
      <label>
        <span>Name</span>
        <input value={designName} onChange={(event) => setDesignName(event.target.value)} placeholder="Noir Narrator" />
      </label>
      <label>
        <span>Voice design</span>
        <textarea
          value={designInstruct}
          onChange={(event) => setDesignInstruct(event.target.value)}
          placeholder="Low, smoky, restrained authority."
          rows={4}
        />
      </label>
      <label>
        <span>Reference text</span>
        <textarea
          value={designText}
          onChange={(event) => setDesignText(event.target.value)}
          placeholder="Control is not the absence of feeling."
          rows={4}
        />
      </label>
      <div className="form-grid-two">
        <label>
          <span>Language</span>
          <select value={designLanguage} onChange={(event) => setDesignLanguage(event.target.value)}>
            {config.supported_languages.map((language) => (
              <option key={language} value={language}>
                {language}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Voice id</span>
          <input
            value={designVoiceId}
            onChange={(event) => setDesignVoiceId(event.target.value)}
            placeholder="Auto from name"
          />
        </label>
      </div>
      <label className="checkbox-row">
        <input
          type="checkbox"
          checked={designOverwrite}
          onChange={(event) => setDesignOverwrite(event.target.checked)}
        />
        <span>Overwrite existing voice</span>
      </label>
      <div className="primary-action-row">
        <button type="button" className="primary-button" onClick={handleDesignSubmit} disabled={designBusy}>
          {designBusy ? 'Creating…' : 'Create voice'}
        </button>
      </div>

      <details className="power-panel" open={showBatch} onToggle={(event) => setShowBatch(event.currentTarget.open)}>
        <summary>Prompt-pack batch design</summary>
        <div className="power-panel-body">
          <label>
            <span>Prompt pack</span>
            <input
              type="file"
              accept=".jsonl,.txt"
              onChange={(event) => setBatchFile(event.target.files?.[0] ?? null)}
            />
          </label>
          <div className="form-grid-two">
            <label>
              <span>Language</span>
              <select value={batchLanguage} onChange={(event) => setBatchLanguage(event.target.value)}>
                {config.supported_languages.map((language) => (
                  <option key={language} value={language}>
                    {language}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Shared text</span>
              <input
                value={batchText}
                onChange={(event) => setBatchText(event.target.value)}
                placeholder="Required for .txt packs"
              />
            </label>
          </div>
          <div className="form-grid-two compact-grid">
            <label className="checkbox-row">
              <input type="checkbox" checked={batchDryRun} onChange={(event) => setBatchDryRun(event.target.checked)} />
              <span>Dry run</span>
            </label>
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={batchOverwrite}
                onChange={(event) => setBatchOverwrite(event.target.checked)}
              />
              <span>Overwrite matches</span>
            </label>
          </div>
          <button type="button" className="ghost-button" onClick={handleBatchDesign} disabled={batchBusy}>
            {batchBusy ? 'Running…' : 'Run prompt pack'}
          </button>
          {batchResult ? (
            <div className="batch-result-list">
              {batchResult.rows.map((row) => (
                <article key={`${row.voice_id}-${row.status}`} className={`batch-row batch-${row.status}`}>
                  <strong>{row.voice_id}</strong>
                  <span>{row.name}</span>
                  <p>{row.detail}</p>
                </article>
              ))}
            </div>
          ) : null}
        </div>
      </details>
    </section>
  );
}
