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
          <p className="brand">{product.brand}</p>
          <h2>{product.name}</h2>
          <p className="price">${product.price}</p>
          <p className="description">{product.description}</p>

          <div className="meta-cluster">
            <div>
              <h4>Sizes</h4>
              <div className="chip-group">{product.sizes.map((size) => <span key={size} className="chip">{size}</span>)}</div>
            </div>
            <div>
              <h4>Color swatches</h4>
              <div className="swatches">
                {product.palette.map((hex) => (
                  <span key={hex} className="swatch" style={{ backgroundColor: hex }} title={hex} />
                ))}
              </div>
            </div>
          </div>

          <div className="similarity-box">
            <h4>AI similarity breakdown</h4>
            {Object.entries(product.similarity).map(([key, value]) => (
              <div key={key} className="meter-row">
                <span>{key}</span>
                <div className="meter">
                  <span style={{ width: `${value}%` }} />
                </div>
                <strong>{value}%</strong>
              </div>
            ))}
          </div>

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

