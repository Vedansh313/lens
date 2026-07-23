import { trendingSearches } from "@/data/mockData";

export default function HeroSection({
  query,
  setQuery,
  onImageUpload,
  onCameraUpload,
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
        <label className="upload-dropzone">
          <input type="file" accept="image/*" onChange={onImageUpload} />
          <div className="upload-icon">?</div>
          <h3>Drop a photo to search</h3>
          <p>PNG, JPG up to 10MB • or pick from below</p>
          <div className="upload-actions">
            <span className="chip button-chip">Upload image</span>
            <button type="button" className="chip button-chip" onClick={onCameraUpload}>
              Use camera
            </button>
          </div>
        </label>

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
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="e.g. ribbed knit, warm tone"
              aria-label="AI search prompt"
            />
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

