import { useMemo, useState } from "react";
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
import { products, trendingSearches } from "@/data/mockData";
import { useLocalStorage } from "@/hooks/useLocalStorage";

// Set VITE_API_URL in .env (or .env.local) to flip between local and ngrok.
const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export default function Dashboard({ user, theme, onToggleTheme, onLogout }) {
  const maxPrice = Math.max(...products.map((item) => item.price));
  const [query, setQuery] = useState("");
  const [selectedImage, setSelectedImage] = useState(null);
  const [selectedImageFile, setSelectedImageFile] = useState(null); // actual File object for API
  const [loading, setLoading] = useState(false);
  const [selectedProduct, setSelectedProduct] = useState(null);
  const [sortBy, setSortBy] = useState("similarity");
  const [viewMode, setViewMode] = useState("grid");
  const [searchResults, setSearchResults] = useState([]); // real API results
  const [searchHistory, setSearchHistory] = useLocalStorage("lens-search-history", []);
  const [savedSearches, setSavedSearches] = useLocalStorage("lens-saved-searches", [
    "minimal watches",
    "olive chinos",
  ]);
  const [wishlist, setWishlist] = useLocalStorage("lens-wishlist", []);
  const [recentlyViewed, setRecentlyViewed] = useLocalStorage("lens-recently-viewed", []);
  const [compareList, setCompareList] = useState([]);
  const [filters, setFilters] = useState({
    categories: [],
    brands: [],
    colors: [],
    inStockOnly: false,
    maxPrice,
  });

  const handleRunSearch = async (newQuery) => {
    const finalQuery = (newQuery ?? query).trim();
    if (newQuery) setQuery(newQuery);
    if (!finalQuery && !selectedImageFile) return;

    setLoading(true);
    try {
      const formData = new FormData();
      if (selectedImageFile) formData.append("image", selectedImageFile);
      if (finalQuery) formData.append("query", finalQuery);
      formData.append("alpha", "0.7");
      formData.append("top_k", "10");

      const res = await fetch(`${API_URL}/api/v1/search`, {
        method: "POST",
        body: formData,
        headers: {
          "ngrok-skip-browser-warning": "true",
        },
      });

      if (!res.ok) throw new Error(`API error: ${res.status}`);

      const data = await res.json();

      // Map API results to the shape ProductCard expects
      const mapped = data.products.map((p) => ({
        id: p.id,
        name: p.name,
        brand: p.name.split(" ")[0], // extract brand from name
        category: p.category,
        color: p.colour,
        price: Math.floor(Math.random() * 5000) + 500, // placeholder until pricing data is added
        rating: parseFloat((3.5 + Math.random() * 1.5).toFixed(1)),
        match: Math.round(p.score * 100),
        available: true,
        image: p.image_url,
        style: p.subCategory,
        texture: "",
      }));

      setSearchResults(mapped);
      setSearchHistory((prev) =>
        [finalQuery, ...prev.filter((item) => item !== finalQuery)].slice(0, 8)
      );
      if (Math.random() > 0.5) {
        setSavedSearches((prev) =>
          [finalQuery, ...prev.filter((item) => item !== finalQuery)].slice(0, 6)
        );
      }
    } catch (err) {
      console.error("Search failed:", err);
      // Fall back to mock data on error so UI doesn't break
      setSearchResults([]);
    } finally {
      setLoading(false);
    }
  };

  const filteredProducts = useMemo(() => {
    // Use real API results if available, otherwise fall back to mock data
    let results =
      searchResults.length > 0
        ? searchResults
        : products.filter((item) => {
            const q = query.toLowerCase();
            const queryMatch =
              !q ||
              [item.name, item.category, item.brand, item.color, item.style, item.texture]
                .join(" ")
                .toLowerCase()
                .includes(q);
            const categoryMatch =
              !filters.categories.length || filters.categories.includes(item.category);
            const brandMatch =
              !filters.brands.length || filters.brands.includes(item.brand);
            const colorMatch =
              !filters.colors.length || filters.colors.includes(item.color);
            const stockMatch = !filters.inStockOnly || item.available;
            const priceMatch = item.price <= filters.maxPrice;

            return queryMatch && categoryMatch && brandMatch && colorMatch && stockMatch && priceMatch;
          });

    if (sortBy === "similarity") results = results.sort((a, b) => b.match - a.match);
    if (sortBy === "rating") results = results.sort((a, b) => b.rating - a.rating);
    if (sortBy === "priceLow") results = results.sort((a, b) => a.price - b.price);
    if (sortBy === "priceHigh") results = results.sort((a, b) => b.price - a.price);

    return results;
  }, [query, filters, sortBy, searchResults]);

  const completeTheLook = filteredProducts.slice(3, 9);

  const handleOpenProduct = (product) => {
    setSelectedProduct(product);
    setRecentlyViewed((prev) =>
      [product, ...prev.filter((entry) => entry.id !== product.id)].slice(0, 6)
    );
  };

  const toggleWishlist = (id) => {
    setWishlist((prev) =>
      prev.includes(id) ? prev.filter((productId) => productId !== id) : [...prev, id]
    );
  };

  const toggleCompare = (product) => {
    setCompareList((prev) => {
      if (prev.some((entry) => entry.id === product.id)) {
        return prev.filter((entry) => entry.id !== product.id);
      }
      return [...prev, product].slice(0, 4);
    });
  };

  const handleImageUpload = (event) => {
    const file = event.target.files?.[0];
    if (file) {
      setSelectedImage(file.name);
      setSelectedImageFile(file); // store actual File for FormData
    }
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
          <button type="button" className="logout-btn" onClick={onLogout}>
            Sign out
          </button>
          <ThemeToggle theme={theme} onToggle={onToggleTheme} />
        </div>
      </header>

      <HeroSection
        query={query}
        setQuery={setQuery}
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
        <FilterSidebar filters={filters} setFilters={setFilters} maxPrice={maxPrice} />

        <main className="catalog-content">
          <ControlsBar
            sortBy={sortBy}
            setSortBy={setSortBy}
            viewMode={viewMode}
            setViewMode={setViewMode}
            count={filteredProducts.length}
          />
          <InsightsPanel query={query} selectedImage={selectedImage} />
          <ProductGrid
            items={filteredProducts}
            viewMode={viewMode}
            onOpen={handleOpenProduct}
            loading={loading}
            wishlist={wishlist}
            onToggleWishlist={toggleWishlist}
            compareList={compareList}
            onCompareToggle={toggleCompare}
          />
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

      <ProductModal product={selectedProduct} onClose={() => setSelectedProduct(null)} />
    </div>
  );
}