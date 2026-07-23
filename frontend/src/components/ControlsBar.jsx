export default function ControlsBar({ sortBy, setSortBy, viewMode, setViewMode, count }) {
  return (
    <div className="controls-bar">
      <p>{count} results</p>
      <div className="controls-actions">
        <select value={sortBy} onChange={(event) => setSortBy(event.target.value)}>
          <option value="similarity">Sort by similarity</option>
          <option value="rating">Sort by rating</option>
          <option value="priceLow">Price: low to high</option>
          <option value="priceHigh">Price: high to low</option>
        </select>
        <div className="toggle-group" role="group" aria-label="Grid or list view">
          <button
            type="button"
            className={viewMode === "grid" ? "active" : ""}
            onClick={() => setViewMode("grid")}
          >
            Grid
          </button>
          <button
            type="button"
            className={viewMode === "list" ? "active" : ""}
            onClick={() => setViewMode("list")}
          >
            List
          </button>
        </div>
      </div>
    </div>
  );
}

