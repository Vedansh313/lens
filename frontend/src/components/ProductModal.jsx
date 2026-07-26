export default function ProductModal({ product, onClose }) {
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
            {Array.isArray(product.sizes) && product.sizes.length > 0 && (
              <div>
                <h4>Sizes</h4>
                <div className="chip-group">
                  {product.sizes.map((size) => (
                    <span key={size} className="chip">{size}</span>
                  ))}
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
            <button>Save</button>
            <button>Compare</button>
            <button className="primary">View details</button>
          </div>
        </div>
      </div>
    </div>
  );
}

