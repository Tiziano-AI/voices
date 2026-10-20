interface BlockingStatesProps {
  appLoading: boolean;
  libraryIntegrityError: string | null;
  bootstrapError: string | null;
  onRetry: () => void;
}

export function BlockingStates({ appLoading, libraryIntegrityError, bootstrapError, onRetry }: BlockingStatesProps) {
  return (
    <>
      {appLoading ? <div className="loading-state">Loading voices…</div> : null}
      {libraryIntegrityError ? (
        <section className="integrity-block">
          <p className="eyebrow">Library blocked</p>
          <h1>Fix the saved library first.</h1>
          <p className="prose-copy">{libraryIntegrityError}</p>
        </section>
      ) : null}
      {!appLoading && !libraryIntegrityError && bootstrapError ? (
        <section className="integrity-block">
          <p className="eyebrow">Studio blocked</p>
          <h1>Load the local studio again.</h1>
          <p className="prose-copy">{bootstrapError}</p>
          <div className="launchpad-actions">
            <button type="button" className="primary-button" onClick={onRetry}>
              Retry load
            </button>
          </div>
        </section>
      ) : null}
    </>
  );
}
