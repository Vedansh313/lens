import { useEffect, useMemo, useRef, useState } from "react";
import ComparisonTray from "@/components/ComparisonTray";
import ControlsBar from "@/components/ControlsBar";
import FilterSidebar from "@/components/FilterSidebar";
import HeroSection from "@/components/HeroSection";
import HistoryAndSaved from "@/components/HistoryAndSaved";
import HowItWorks from "@/components/HowItWorks";
import InsightsPanel from "@/components/InsightsPanel";
import ProductGrid from "@/components/ProductGrid";
import ProductModal from "@/components/ProductModal";
import RecommendationCarousel from "@/components/RecommendationCarousel";
import ThemeToggle from "@/components/ThemeToggle";
import { SITE_NAME } from "@/config/site";
import {
  fetchAutocomplete,
  fetchCategories,
  fetchProduct,
  fetchProducts,
  hybridSearch,
  mapProduct,
} from "@/data/api";
import { trendingSearches } from "@/data/mockData";
import { useEngagement } from "@/hooks/useEngagement";
import { useLocalStorage } from "@/hooks/useLocalStorage";

const LIMIT = 24;
// UI sort key -> catalog API sort key (browse mode). Search mode sorts client-
// side because the hybrid endpoint returns a relevance-ranked top-K.
const API_SORT = {
  relevance: "id",
  priceLow: "price_asc",
  priceHigh: "price_desc",
  name: "name",
};

export default function Dashboard({ user, theme, onToggleTheme, onLogout, cartCount = 0, onAddToCart, onOpenCart }) {
  const [query, setQuery] = useState("");
  const [selectedImage, setSelectedImage] = useState(null);
  const [selectedImageFile, setSelectedImageFile] = useState(null);

  // "Committed" search inputs — distinct from the live text box so typing does
  // not refetch until the user actually searches.
  const [activeQuery, setActiveQuery] = useState("");
  const [activeImageFile, setActiveImageFile] = useState(null);
  const isSearch = Boolean(activeQuery || activeImageFile);

  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [offset, setOffset] = useState(0);

  const [facets, setFacets] = useState({
    categories: [],
    articleTypes: [],
    colours: [],
    genders: [],
    priceRange: { min: 0, max: 500 },
  });
  const [filters, setFilters] = useState({
    category: null,
    articleType: null,
    colour: null,
    gender: null,
    inStock: false,
    maxPrice: null,
  });
  const [sortBy, setSortBy] = useState("relevance");

  const [suggestions, setSuggestions] = useState([]);
  const acTimer = useRef(null);

  const [selectedProduct, setSelectedProduct] = useState(null);
  const [viewMode, setViewMode] = useState("grid");
  const [searchHistory, setSearchHistory] = useLocalStorage("lens-search-history", []);
  const [savedSearches] = useLocalStorage("lens-saved-searches", ["minimal watches", "olive chinos"]);
  const [compareList, setCompareList] = useState([]);

  // Server-backed wishlist + recently-viewed (per user).
  const { wishlistIds, recentlyViewed, toggleWishlist, recordView } = useEngagement();

  const maxPrice = facets.priceRange?.max ?? 500;

  // ---- Facets (once) -----------------------------------------------------
  useEffect(() => {
    fetchCategories()
      .then((f) => {
        setFacets(f);
        setFilters((prev) => ({ ...prev, maxPrice: prev.maxPrice ?? f.priceRange.max }));
      })
      .catch((err) => console.error("categories:", err));
  }, []);

  // ---- Reset to first page whenever the result set changes ---------------
  useEffect(() => {
    setOffset((prev) => (prev === 0 ? prev : 0));
  }, [filters, sortBy, activeQuery, activeImageFile]);

  // ---- Main loader: catalog browse OR hybrid search ----------------------
  useEffect(() => {
    let cancelled = false;
    const apiFilters = {
      category: filters.category || undefined,
      article_type: filters.articleType || undefined,
      colour: filters.colour || undefined,
      gender: filters.gender || undefined,
      in_stock: filters.inStock ? true : undefined,
      max_price: filters.maxPrice ?? undefined,
    };

    async function load() {
      setLoading(true);
      try {
        if (isSearch) {
          const data = await hybridSearch({
            query: activeQuery,
            imageFile: activeImageFile,
            filters: {
              category: filters.category,
              colour: filters.colour,
              gender: filters.gender,
              inStock: filters.inStock ? true : undefined,
              maxPrice: filters.maxPrice,
            },
            topK: 48,
          });
          if (!cancelled) {
            setItems((data.products || []).map(mapProduct));
            setTotal(data.total || 0);
          }
        } else {
          const data = await fetchProducts({
            ...apiFilters,
            sort: API_SORT[sortBy],
            limit: LIMIT,
            offset,
          });
          if (!cancelled) {
            setItems((data.items || []).map(mapProduct));
            setTotal(data.total || 0);
          }
        }
      } catch (err) {
        if (!cancelled) {
          console.error("load results:", err);
          setItems([]);
          setTotal(0);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [filters, sortBy, offset, activeQuery, activeImageFile, isSearch]);

  // Search results come back relevance-ranked; sort them client-side and apply
  // the one filter the hybrid endpoint doesn't take (article type).
  const displayItems = useMemo(() => {
    if (!isSearch) return items;
    let list = items;
    if (filters.articleType) list = list.filter((p) => p.subCategory === filters.articleType);
    const copy = [...list];
    if (sortBy === "priceLow") copy.sort((a, b) => a.price - b.price);
    else if (sortBy === "priceHigh") copy.sort((a, b) => b.price - a.price);
    else if (sortBy === "name") copy.sort((a, b) => (a.name || "").localeCompare(b.name || ""));
    return copy;
  }, [items, sortBy, isSearch, filters.articleType]);

  const resultCount = isSearch ? displayItems.length : total;
  const pageCount = Math.ceil(total / LIMIT) || 1;
  const page = Math.floor(offset / LIMIT) + 1;
  const completeTheLook = displayItems.slice(3, 9);

  // ---- Search + autocomplete --------------------------------------------
  const handleRunSearch = (newQuery) => {
    const finalQuery = (newQuery ?? query).trim();
    if (newQuery !== undefined) setQuery(newQuery);
    setSuggestions([]);
    if (!finalQuery && !selectedImageFile) {
      setActiveQuery("");
      setActiveImageFile(null);
      return;
    }
    setActiveQuery(finalQuery);
    setActiveImageFile(selectedImageFile);
    if (finalQuery) {
      setSearchHistory((prev) => [finalQuery, ...prev.filter((i) => i !== finalQuery)].slice(0, 8));
    }
  };

  const handleClearSearch = () => {
    setActiveQuery("");
    setActiveImageFile(null);
    setQuery("");
    setSelectedImage(null);
    setSelectedImageFile(null);
    setSuggestions([]);
  };

  const handleQueryChange = (value) => {
    setQuery(value);
    if (acTimer.current) clearTimeout(acTimer.current);
    if (!value || value.trim().length < 2) {
      setSuggestions([]);
      return;
    }
    acTimer.current = setTimeout(async () => {
      try {
        const res = await fetchAutocomplete(value);
        setSuggestions(res.suggestions || []);
      } catch {
        setSuggestions([]);
      }
    }, 180);
  };

  const handlePickSuggestion = (suggestion) => {
    setSuggestions([]);
    handleRunSearch(suggestion);
  };

  const handleImageUpload = (event) => {
    const file = event.target.files?.[0];
    if (file) {
      setSelectedImage(file.name);
      setSelectedImageFile(file);
    }
  };

  // ---- Product interactions ---------------------------------------------
  const handleOpenProduct = async (product) => {
    setSelectedProduct(product); // show card data immediately
    recordView(product.id); // server records the view + refreshes the carousel
    try {
      const detail = await fetchProduct(product.id);
      setSelectedProduct((prev) =>
        prev && prev.id === product.id
          ? { ...prev, season: detail.season, year: detail.year, usage: detail.usage }
          : prev
      );
    } catch {
      /* keep the card-level data if detail fetch fails */
    }
  };

  const toggleCompare = (product) => {
    setCompareList((prev) => {
      if (prev.some((entry) => entry.id === product.id)) {
        return prev.filter((entry) => entry.id !== product.id);
      }
      return [...prev, product].slice(0, 4);
    });
  };

  return (
    <div className="lens-app">
      <header className="top-nav">
        <div className="brand">
          <span className="brand-icon">?</span>
          {SITE_NAME}
        </div>
        <nav>
          <a href="#hero">Discover</a>
          <a href="#catalog">Catalog</a>
          <a href="#saved">Saved</a>
        </nav>
        <div className="nav-actions">
          <span className="user-greeting">Hi, {user.name}</span>
          <button type="button" className="cart-btn" onClick={onOpenCart}>
            Cart{cartCount > 0 ? ` (${cartCount})` : ""}
          </button>
          <button type="button" className="logout-btn" onClick={onLogout}>
            Sign out
          </button>
          <ThemeToggle theme={theme} onToggle={onToggleTheme} />
        </div>
      </header>

      <HeroSection
        query={query}
        onQueryChange={handleQueryChange}
        suggestions={suggestions}
        onPickSuggestion={handlePickSuggestion}
        onImageUpload={handleImageUpload}
        onCameraUpload={() => setSelectedImage("camera-capture.jpg")}
        onRunSearch={() => handleRunSearch()}
        onChipClick={(chip) => handleRunSearch(chip)}
      />

      <HistoryAndSaved
        searchHistory={searchHistory}
        savedSearches={savedSearches.length ? savedSearches : trendingSearches.slice(0, 2)}
        onReuseSearch={(term) => handleRunSearch(term)}
      />

      <section className="catalog-layout" id="catalog">
        <FilterSidebar facets={facets} filters={filters} setFilters={setFilters} maxPrice={maxPrice} />

        <main className="catalog-content">
          {isSearch && (
            <div className="search-banner">
              <span>
                Showing results for{" "}
                <strong>{activeQuery || "your image"}</strong>
                {activeImageFile && activeQuery ? " + image" : ""}
              </span>
              <button type="button" className="chip" onClick={handleClearSearch}>
                Clear search
              </button>
            </div>
          )}

          <ControlsBar
            sortBy={sortBy}
            setSortBy={setSortBy}
            viewMode={viewMode}
            setViewMode={setViewMode}
            count={resultCount}
          />
          <InsightsPanel query={activeQuery} selectedImage={selectedImage} />
          <ProductGrid
            items={displayItems}
            viewMode={viewMode}
            onOpen={handleOpenProduct}
            loading={loading}
            wishlist={wishlistIds}
            onToggleWishlist={toggleWishlist}
            compareList={compareList}
            onCompareToggle={toggleCompare}
            onAddToCart={onAddToCart}
          />

          {!isSearch && total > LIMIT && (
            <div className="pager">
              <button
                type="button"
                disabled={offset === 0}
                onClick={() => setOffset((o) => Math.max(0, o - LIMIT))}
              >
                Previous
              </button>
              <span>
                Page {page} of {pageCount}
              </span>
              <button
                type="button"
                disabled={offset + LIMIT >= total}
                onClick={() => setOffset((o) => o + LIMIT)}
              >
                Next
              </button>
            </div>
          )}
        </main>
      </section>

      <HowItWorks />
      <RecommendationCarousel items={completeTheLook} title="Complete the look" />
      <RecommendationCarousel items={recentlyViewed} title="Recently viewed" />
      <ComparisonTray
        items={compareList}
        onRemove={(id) => setCompareList((prev) => prev.filter((entry) => entry.id !== id))}
      />

      <footer id="saved">Powered by image embeddings and vector similarity.</footer>

      <ProductModal
        product={selectedProduct}
        onClose={() => setSelectedProduct(null)}
        onAddToCart={onAddToCart}
      />
    </div>
  );
}
