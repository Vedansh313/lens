// Real catalog facets from GET /categories. Single-select per facet (matches
// the catalog API, which takes one value per dimension). Brand was intentionally
// dropped — the dataset has no brand field.

export default function FilterSidebar({ facets, filters, setFilters }) {
  const priceMin = Math.floor(facets.priceRange?.min ?? 0);
  const priceMax = Math.ceil(facets.priceRange?.max ?? 500);

  const toggle = (key, value) =>
    setFilters((prev) => ({ ...prev, [key]: prev[key] === value ? null : value }));

  const reset = () =>
    setFilters({
      category: null,
      articleType: null,
      colour: null,
      gender: null,
      inStock: false,
      maxPrice: priceMax,
    });

  const chipRow = (key, values) => (
    <div className="chip-group">
      {values.map((value) => (
        <button
          key={value}
          type="button"
          className={`chip ${filters[key] === value ? "active" : ""}`}
          onClick={() => toggle(key, value)}
        >
          {value}
        </button>
      ))}
    </div>
  );

  return (
    <aside className="filters">
      <div className="filters-header">
        <h3>Refine</h3>
      </div>

      <div className="filter-block">
        <h4>Category</h4>
        {chipRow("category", facets.categories)}
      </div>

      <div className="filter-block">
        <h4>Gender</h4>
        {chipRow("gender", facets.genders)}
      </div>

      <div className="filter-block">
        <h4>Type</h4>
        <select
          value={filters.articleType ?? ""}
          onChange={(event) =>
            setFilters((prev) => ({ ...prev, articleType: event.target.value || null }))
          }
        >
          <option value="">All types</option>
          {facets.articleTypes.map((type) => (
            <option key={type} value={type}>
              {type}
            </option>
          ))}
        </select>
      </div>

      <div className="filter-block">
        <h4>Color</h4>
        {chipRow("colour", facets.colours)}
      </div>

      <div className="filter-block">
        <h4>Max price (${filters.maxPrice ?? priceMax})</h4>
        <input
          className="range"
          type="range"
          min={priceMin}
          max={priceMax}
          value={filters.maxPrice ?? priceMax}
          onChange={(event) =>
            setFilters((prev) => ({ ...prev, maxPrice: Number(event.target.value) }))
          }
        />
      </div>

      <div className="filter-block">
        <h4>Availability</h4>
        <label className="availability">
          <input
            type="checkbox"
            checked={filters.inStock}
            onChange={(event) =>
              setFilters((prev) => ({ ...prev, inStock: event.target.checked }))
            }
          />
          In stock only
        </label>
      </div>

      <button className="reset-btn" onClick={reset}>
        Reset filters
      </button>
    </aside>
  );
}
