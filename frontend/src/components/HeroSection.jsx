import { trendingSearches } from "@/data/mockData";

export default function HeroSection({
  query,
  onQueryChange,
  suggestions = [],
  onPickSuggestion,
  onImageUpload,
  selectedImage,
  selectedImagePreview,
  onClearImage,
  onRunSearch,
  onChipClick,
}) {
  return (
    <section className="hero" id="hero">
      <div className="hero-header">
        <p className="hero-kicker">Visual Discovery</p>
        <h1>
          Find what you&apos;ve seen,
          <br />
          <em>not just what you can name.</em>
        </h1>
      </div>

      <div className="hero-grid">
        {/* A div, not a label. Any click inside a label activates the file
            input it wraps, so a "Clear photo" button nested in one fights the
            picker for the same click. Only the explicit choose-a-file targets
            below are labels; the clear button is a sibling and cannot open it. */}
        <div className={`upload-dropzone${selectedImage ? " has-image" : ""}`}>
          {selectedImage ? (
            <>
              {/* Confirms what is actually being searched. Without it, picking a
                  photo changed nothing on screen and looked like a dead click. */}
              {selectedImagePreview && (
                <img className="upload-preview" src={selectedImagePreview} alt="" />
              )}
              <h3>Searching this photo</h3>
              <p className="upload-filename" title={selectedImage}>
                {selectedImage}
              </p>
              <div className="upload-actions">
                <label className="chip button-chip upload-trigger">
                  <input type="file" accept="image/*" onChange={onImageUpload} />
                  Choose another
                </label>
                <button type="button" className="chip button-chip" onClick={onClearImage}>
                  Clear photo
                </button>
              </div>
            </>
          ) : (
            <label className="upload-empty">
              <input type="file" accept="image/*" onChange={onImageUpload} />
              <div className="upload-icon">?</div>
              <h3>Drop a photo to search</h3>
              <p>PNG, JPG up to 10MB • or pick from below</p>
              <div className="upload-actions">
                <span className="chip button-chip">Upload image</span>
              </div>
            </label>
          )}
        </div>

        <div className="ai-search-panel">
          <span className="search-tag">AI visual search</span>
          <h2>Describe it, or just <em>show us.</em></h2>
          <p>Combine image and natural language to improve semantic similarity ranking.</p>

          <form
            className="search-row"
            onSubmit={(event) => {
              event.preventDefault();
              onRunSearch();
            }}
          >
            <div className="search-input-wrap">
              <input
                value={query}
                onChange={(event) => onQueryChange(event.target.value)}
                placeholder="e.g. blue running shoes for men"
                aria-label="AI search prompt"
                autoComplete="off"
              />
              {suggestions.length > 0 && (
                <ul className="autocomplete">
                  {suggestions.map((suggestion) => (
                    <li key={suggestion}>
                      <button type="button" onClick={() => onPickSuggestion(suggestion)}>
                        {suggestion}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <button type="submit">Search</button>
          </form>

          <div className="chip-group">
            {trendingSearches.map((chip) => (
              <button
                key={chip}
                className="chip"
                type="button"
                onClick={() => onChipClick(chip)}
              >
                {chip}
              </button>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
