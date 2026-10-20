import type { VoiceDetail, VoiceSummary } from '../lib/types';

interface InspectorProps {
  open: boolean;
  detail: VoiceDetail | null;
  overrideLanguage: string | null;
  languageOptions: string[];
  onClose: () => void;
  onOverrideLanguageChange: (value: string | null) => void;
  onDeleteVoice: (voice: VoiceSummary) => void;
  onPlayReference: (detail: VoiceDetail) => void;
}

export function Inspector({
  open,
  detail,
  overrideLanguage,
  languageOptions,
  onClose,
  onOverrideLanguageChange,
  onDeleteVoice,
  onPlayReference,
}: InspectorProps) {
  return (
    <div className={`inspector-shell ${open ? 'is-open' : ''}`} aria-hidden={!open}>
      <button type="button" className="inspector-scrim" onClick={onClose} aria-label="Close details" />
      <aside className="inspector-panel">
        <div className="inspector-topline">
          <div>
            <p className="eyebrow">Details</p>
            <h2>{detail?.summary.name ?? 'No voice selected'}</h2>
          </div>
          <button type="button" className="text-button" onClick={onClose}>
            Close
          </button>
        </div>

        {!detail ? (
          <p className="muted-copy">Pick a saved voice to inspect its reference clip and management controls.</p>
        ) : (
          <>
            <div className="inspector-metadata-row">
              <span className="meta-chip">{detail.summary.language}</span>
              <span className="meta-chip">{detail.summary.source_kind}</span>
              <span className="meta-chip mono-chip">{detail.summary.id}</span>
            </div>

            <section className="inspector-section">
              <p className="eyebrow">Reference clip</p>
              <button type="button" className="ghost-button" onClick={() => onPlayReference(detail)}>
                Play reference
              </button>
            </section>

            <section className="inspector-section">
              <label className="inspector-field">
                <span>Render language</span>
                <select
                  value={overrideLanguage ?? ''}
                  onChange={(event) => onOverrideLanguageChange(event.target.value || null)}
                  aria-label="Render language override"
                >
                  <option value="">Use voice default</option>
                  {languageOptions.map((language) => (
                    <option key={language} value={language}>
                      {language}
                    </option>
                  ))}
                </select>
              </label>
            </section>

            <section className="inspector-section">
              <p className="eyebrow">Reference text</p>
              <p className="prose-copy">{detail.reference_text}</p>
            </section>

            <details className="inspector-details">
              <summary>Full metadata</summary>
              <dl>
                <div>
                  <dt>Created</dt>
                  <dd>{detail.record.created_at}</dd>
                </div>
                <div>
                  <dt>Base model</dt>
                  <dd>{detail.record.base_model_id}</dd>
                </div>
                <div>
                  <dt>Reference SHA</dt>
                  <dd className="mono-copy">{detail.record.reference_sha256}</dd>
                </div>
                {detail.record.source.kind === 'design' ? (
                  <div>
                    <dt>Design prompt</dt>
                    <dd>{detail.record.source.instruct}</dd>
                  </div>
                ) : null}
              </dl>
            </details>

            <section className="inspector-section inspector-danger-zone">
              <p className="eyebrow">Manage</p>
              <button type="button" className="danger-button" onClick={() => onDeleteVoice(detail.summary)}>
                Delete voice
              </button>
            </section>
          </>
        )}
      </aside>
    </div>
  );
}
