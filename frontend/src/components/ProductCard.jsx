export default function ProductCard({
  product,
  viewMode,
  onOpen,
  onToggleWishlist,
  wished,
  onCompareToggle,
  compared,
  onAddToCart,
}) {
  return (
    <article className={`product-card ${viewMode}`}>
      <button className="wishlist" onClick={() => onToggleWishlist(product.id)} aria-label="Save product">
        {wished ? "?" : "?"}
      </button>
      <button className="preview-btn" onClick={() => onOpen(product)}>Quick preview</button>
      <div className="image-wrap" onClick={() => onOpen(product)}>
        <img src={product.image} alt={product.name} loading="lazy" />
        {product.match != null && <span className="match-badge">{product.match}% match</span>}
        {!product.available && <span className="stock-badge">Out of stock</span>}
      </div>
      <div className="product-meta">
        <p className="brand">{product.category}</p>
        <h3>{product.name}</h3>
        <div className="row">
          <span>${product.price}</span>
          <span className="muted">{product.color}</span>
        </div>
        <div className="card-actions">
          <button
            className="add-cart-btn"
            disabled={!product.available}
            onClick={() => onAddToCart?.(product.id)}
          >
            {product.available ? "Add to cart" : "Sold out"}
          </button>
          <button className={`compare-btn ${compared ? "active" : ""}`} onClick={() => onCompareToggle(product)}>
            {compared ? "Added" : "Compare"}
          </button>
        </div>
      </div>
    </article>
  );
}

