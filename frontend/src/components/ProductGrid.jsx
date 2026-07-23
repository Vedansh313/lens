import ProductCard from "./ProductCard";

function Skeleton() {
  return (
    <div className="product-card skeleton">
      <div className="skeleton-box" />
      <div className="skeleton-line" />
      <div className="skeleton-line short" />
    </div>
  );
}

export default function ProductGrid(props) {
  const {
    items,
    viewMode,
    onOpen,
    loading,
    wishlist,
    onToggleWishlist,
    compareList,
    onCompareToggle,
  } = props;

  if (loading) {
    return (
      <div className={`product-grid ${viewMode}`}>
        {Array.from({ length: 6 }).map((_, index) => (
          <Skeleton key={index} />
        ))}
      </div>
    );
  }

  if (!items.length) {
    return <p className="empty">No products match your search yet.</p>;
  }

  return (
    <div className={`product-grid ${viewMode}`}>
      {items.map((product) => (
        <ProductCard
          key={product.id}
          product={product}
          viewMode={viewMode}
          onOpen={onOpen}
          wished={wishlist.includes(product.id)}
          onToggleWishlist={onToggleWishlist}
          compared={compareList.some((entry) => entry.id === product.id)}
          onCompareToggle={onCompareToggle}
        />
      ))}
    </div>
  );
}

