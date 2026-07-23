export default function HistoryAndSaved({ searchHistory, savedSearches, onReuseSearch }) {
  return (
    <section className="history-layout">
      <article>
        <h4>Recent searches</h4>
        <div className="chip-group">
          {searchHistory.length ? (
            searchHistory.map((term) => (
              <button key={term} className="chip" onClick={() => onReuseSearch(term)}>
                {term}
              </button>
            ))
          ) : (
            <p className="muted">No searches yet</p>
          )}
        </div>
      </article>
      <article>
        <h4>Saved searches</h4>
        <div className="chip-group">
          {savedSearches.length ? (
            savedSearches.map((term) => (
              <button key={term} className="chip" onClick={() => onReuseSearch(term)}>
                {term}
              </button>
            ))
          ) : (
            <p className="muted">No saved queries yet</p>
          )}
        </div>
      </article>
    </section>
  );
}

