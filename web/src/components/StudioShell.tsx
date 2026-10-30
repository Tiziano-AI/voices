import type { StudioController } from '../hooks/studioControllerTypes';
import { AuditionBoard } from './AuditionBoard';
import { BlockingStates } from './BlockingStates';
import { CreationStudio } from './CreationStudio';
import { Inspector } from './Inspector';
import { Launchpad } from './Launchpad';
import { PerformanceDeck } from './PerformanceDeck';
import { VoiceRack } from './VoiceRack';

interface StudioShellProps {
  controller: StudioController;
}

/**
 * Renders the top-level browser studio composition from controller state.
 * This component has no network, storage, or persistence side effects.
 */
export function StudioShell({ controller }: StudioShellProps) {
  const { state, actions } = controller;
  const studioReady = !state.appLoading && !state.libraryIntegrityError && !state.bootstrapError;
  const hasRetainedWork =
    state.previewClip !== null ||
    state.renderArtifact !== null ||
    state.compareClips.length > 0 ||
    Object.keys(state.compareArtifacts).length > 0 ||
    state.auditionBoard.candidates.length > 0;

  return (
    <div className="studio-shell">
      <div className="studio-background" />
      {state.uiConfig.compute_backend === 'dgx' ? (
        <div role="status">DGX compute · reference library, review and exports stay on this Mac</div>
      ) : null}
      <CreationStudio
        open={state.creationOpen}
        mode={state.creationMode}
        config={state.uiConfig}
        errorMessage={state.creationMessage ?? state.edgeMessage}
        onModeChange={actions.changeCreationMode}
        onClose={actions.closeCreation}
        onBatchCreated={actions.batchCreated}
        onCreated={(detail) => void actions.voiceCreated(detail)}
        onError={actions.setCreationMessage}
        onPlayReviewAudio={(source) => void actions.playAudio(source)}
      />

      <BlockingStates
        appLoading={state.appLoading}
        libraryIntegrityError={state.libraryIntegrityError}
        bootstrapError={state.bootstrapError}
        onRetry={() => void actions.bootstrapStudio()}
      />
      {studioReady && !state.hasVoices && !hasRetainedWork ? (
        <Launchpad theme={state.theme} onThemeChange={actions.setTheme} onOpenCreate={actions.openCreation} />
      ) : null}

      {studioReady && (state.hasVoices || hasRetainedWork) ? (
        <div className="studio-frame">
          <VoiceRack
            voices={state.voices}
            selectedVoiceId={state.selectedVoiceId}
            compareVoiceIds={state.compareVoiceIds}
            searchQuery={state.searchQuery}
            onSearchQueryChange={actions.setSearchQuery}
            onSelectVoice={actions.selectVoice}
            onToggleCompare={actions.toggleCompare}
            onAuditionReference={(voiceId) => void actions.auditionReference(voiceId)}
          />
          <div className="studio-stage-column">
            <PerformanceDeck
              detail={state.activeVoiceDetail}
              theme={state.theme}
              scriptText={state.scriptText}
              onScriptTextChange={actions.setScriptText}
              previewClip={state.previewClip}
              outputReason={state.outputReason}
              compareVoiceIds={state.compareVoiceIds}
              compareActionLabel={state.compareActionLabel}
              compareClips={state.compareClips}
              compareArtifacts={state.compareArtifacts}
              previewBusy={state.previewBusy}
              compareBusy={state.compareBusy}
              renderBusy={state.renderBusy}
              compareRenderBusy={state.compareRenderBusy}
              renderArtifact={state.renderArtifact}
              edgeMessage={state.creationOpen ? null : state.edgeMessage}
              audioSession={state.audioSession}
              onPreview={() => void actions.preview()}
              onCompare={() => void actions.compare()}
              onRender={() => void actions.render()}
              onRenderCompareSet={() => void actions.renderCompareSet()}
              onPlayAudio={(source) => void actions.playAudio(source)}
              onStopAudio={actions.stopAudio}
              onOpenCreate={actions.openCreation}
              onOpenInspector={actions.openInspector}
              onThemeChange={actions.setTheme}
              onAuditionReference={() => {
                if (state.selectedVoiceId && state.activeVoiceDetail) {
                  void actions.auditionReference(state.selectedVoiceId);
                }
              }}
            />
            <AuditionBoard
              state={state.auditionBoard}
              actions={actions.auditionBoard}
              languageOptions={state.uiConfig.supported_languages}
              audioSession={state.audioSession}
            />
          </div>
        </div>
      ) : null}

      <Inspector
        open={state.inspectorOpen}
        detail={state.activeVoiceDetail}
        overrideLanguage={state.overrideLanguage}
        languageOptions={state.uiConfig.supported_languages}
        onClose={actions.closeInspector}
        onOverrideLanguageChange={actions.setOverrideLanguage}
        onDeleteVoice={(voice) => void actions.deleteVoice(voice)}
        onPlayReference={(detail) =>
          void actions.playAudio({
            id: `reference:${detail.summary.id}:inspector`,
            kind: 'reference',
            label: detail.summary.name,
            url: detail.reference_audio_url,
          })
        }
      />
    </div>
  );
}
