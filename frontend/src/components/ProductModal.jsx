export default function ProductModal({ product, onClose, onAddToCart }) {
  if (!product) return null;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(event) => event.stopPropagation()} role="dialog" aria-modal="true">
        <button className="close" onClick={onClose} aria-label="Close product preview">
          ?
        </button>

        <div className="modal-image">
          <img src={product.image} alt={product.name} />
        </div>

        <div className="modal-body">
          <p className="brand">{product.category ?? product.brand}</p>
          <h2>{product.name}</h2>
          <p className="price">${product.price}</p>
          {product.description && <p className="description">{product.description}</p>}

          <div className="meta-cluster">
            <div>
              <h4>Color</h4>
              <div className="chip-group">
                {product.color && <span className="chip">{product.color}</span>}
                {product.gender && <span className="chip">{product.gender}</span>}
              </div>
            </div>
            {(product.season || product.year || product.usage) && (
              <div>
                <h4>Details</h4>
                <div className="chip-group">
                  {product.usage && <span className="chip">{product.usage}</span>}
                  {product.season && <span className="chip">{product.season}</span>}
                  {product.year && <span className="chip">{product.year}</span>}
                </div>
              </div>
            )}
          </div>

          {product.match != null && (
            <div className="similarity-box">
              <h4>AI match</h4>
              <div className="meter-row">
                <span>similarity</span>
                <div className="meter">
                  <span style={{ width: `${product.match}%` }} />
                </div>
                <strong>{product.match}%</strong>
              </div>
            </div>
          )}

          <div className="modal-actions">
            <button
              className="primary"
              disabled={product.available === false}
              onClick={() => {
                onAddToCart?.(product.id);
                onClose();
              }}
            >
              {product.available === false ? "Sold out" : "Add to cart"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

