import { useDeferredValue, useMemo } from 'react';

import type { VoiceSummary } from '../lib/types';

interface VoiceRackProps {
  voices: VoiceSummary[];
  selectedVoiceId: string | null;
  compareVoiceIds: string[];
  searchQuery: string;
  onSearchQueryChange: (value: string) => void;
  onSelectVoice: (voiceId: string) => void;
  onToggleCompare: (voiceId: string) => void;
  onAuditionReference: (voiceId: string) => void;
}

function formatCreatedAt(value: string): string {
  return value.slice(0, 10);
}

export function VoiceRack({
  voices,
  selectedVoiceId,
  compareVoiceIds,
  searchQuery,
  onSearchQueryChange,
  onSelectVoice,
  onToggleCompare,
  onAuditionReference,
}: VoiceRackProps) {
  const deferredQuery = useDeferredValue(searchQuery.trim().toLowerCase());
  const visibleVoices = useMemo(() => {
    if (!deferredQuery) {
      return voices;
    }
    return voices.filter((voice) => {
      const haystack = `${voice.name} ${voice.id} ${voice.description} ${voice.language}`.toLowerCase();
      return haystack.includes(deferredQuery);
    });
  }, [deferredQuery, voices]);

  return (
    <aside className="voice-rack">
      <div className="voice-rack-header">
        <div>
          <p className="eyebrow">Library</p>
          <h2>Saved voices</h2>
        </div>
        <span className="rack-count">{voices.length}</span>
      </div>

      <label className="search-shell">
        <span>Search</span>
        <input
          value={searchQuery}
          onChange={(event) => onSearchQueryChange(event.target.value)}
          placeholder="Name, id, tone"
          aria-label="Search voices"
        />
      </label>

      <ul className="voice-list" aria-label="Saved voices">
        {visibleVoices.map((voice) => {
          const isSelected = voice.id === selectedVoiceId;
          const isCompared = compareVoiceIds.includes(voice.id);
          return (
            <li key={voice.id} className={`voice-row ${isSelected ? 'is-selected' : ''}`}>
              <button
                className="voice-row-main"
                onClick={() => onSelectVoice(voice.id)}
                type="button"
                aria-label={`Select ${voice.name} (${voice.id})`}
              >
                <span className="voice-row-title">{voice.name}</span>
                <span className="voice-row-meta">
                  <span>{voice.id}</span>
                  <span>{voice.language}</span>
                  <span>{voice.source_kind}</span>
                  <span>{formatCreatedAt(voice.created_at)}</span>
                </span>
                <span className="voice-row-desc">{voice.description}</span>
              </button>
              <div className="voice-row-tools">
                <button
                  type="button"
                  className="micro-button"
                  onClick={() => onAuditionReference(voice.id)}
                  aria-label={`Listen to ${voice.name} (${voice.id})`}
                >
                  Listen
                </button>
                <button
                  type="button"
                  className={`micro-button ${isCompared ? 'is-active' : ''}`}
                  onClick={() => onToggleCompare(voice.id)}
                  aria-label={`${isCompared ? 'Remove' : 'Add'} ${voice.name} (${voice.id}) ${
                    isCompared ? 'from' : 'to'
                  } compare`}
                >
                  {isCompared ? 'Queued' : 'Compare'}
                </button>
              </div>
            </li>
          );
        })}
      </ul>
    </aside>
  );
}
