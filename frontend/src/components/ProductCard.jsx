export default function ProductCard({
  product,
  viewMode,
  onOpen,
  onToggleWishlist,
  wished,
  onCompareToggle,
  compared,
}) {
  return (
    <article className={`product-card ${viewMode}`}>
      <button className="wishlist" onClick={() => onToggleWishlist(product.id)} aria-label="Save product">
        {wished ? "?" : "?"}
      </button>
      <button className="preview-btn" onClick={() => onOpen(product)}>Quick preview</button>
      <div className="image-wrap" onClick={() => onOpen(product)}>
        <img src={product.image} alt={product.name} loading="lazy" />
        <span className="match-badge">{product.match}% match</span>
        {!product.available && <span className="stock-badge">Out of stock</span>}
      </div>
      <div className="product-meta">
        <p className="brand">{product.brand}</p>
        <h3>{product.name}</h3>
        <div className="row">
          <span>${product.price}</span>
          <span>? {product.rating} ({product.reviews})</span>
        </div>
        <button className={`compare-btn ${compared ? "active" : ""}`} onClick={() => onCompareToggle(product)}>
          {compared ? "Added" : "Compare"}
        </button>
      </div>
    </article>
  );
}

