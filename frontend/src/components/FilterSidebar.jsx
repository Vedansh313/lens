import { brands, categories, colors } from "@/data/mockData";

export default function FilterSidebar({ filters, setFilters, maxPrice }) {
  const toggleArrayValue = (key, value) => {
    setFilters((prev) => {
      const values = prev[key].includes(value)
        ? prev[key].filter((item) => item !== value)
        : [...prev[key], value];
      return { ...prev, [key]: values };
    });
  };

  return (
    <aside className="filters">
      <div className="filters-header">
        <h3>Refine</h3>
      </div>

      <div className="filter-block">
        <h4>Category</h4>
        <div className="chip-group">
          {categories.map((category) => (
            <button
              key={category}
              type="button"
              className={`chip ${filters.categories.includes(category) ? "active" : ""}`}
              onClick={() => toggleArrayValue("categories", category)}
            >
              {category}
            </button>
          ))}
        </div>
      </div>

      <div className="filter-block">
        <h4>Brand</h4>
        <div className="chip-group">
          {brands.map((brand) => (
            <button
              key={brand}
              type="button"
              className={`chip ${filters.brands.includes(brand) ? "active" : ""}`}
              onClick={() => toggleArrayValue("brands", brand)}
            >
              {brand}
            </button>
          ))}
        </div>
      </div>

      <div className="filter-block">
        <h4>Color</h4>
        <div className="chip-group">
          {colors.map((color) => (
            <button
              key={color}
              type="button"
              className={`chip ${filters.colors.includes(color) ? "active" : ""}`}
              onClick={() => toggleArrayValue("colors", color)}
            >
              {color}
            </button>
          ))}
        </div>
      </div>

      <div className="filter-block">
        <h4>Max price (${filters.maxPrice})</h4>
        <input
          className="range"
          type="range"
          min={50}
          max={maxPrice}
          value={filters.maxPrice}
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
            checked={filters.inStockOnly}
            onChange={(event) =>
              setFilters((prev) => ({ ...prev, inStockOnly: event.target.checked }))
            }
          />
          In stock only
        </label>
      </div>

      <button
        className="reset-btn"
        onClick={() =>
          setFilters({ categories: [], brands: [], colors: [], inStockOnly: false, maxPrice })
        }
      >
        Reset filters
      </button>
    </aside>
  );
}

