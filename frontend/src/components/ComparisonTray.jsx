export default function ComparisonTray({ items, onRemove }) {
  if (!items.length) return null;

  return (
    <section className="comparison-tray">
      <h4>Comparison ({items.length})</h4>
      <div className="compare-scroll">
        {items.map((product) => (
          <article key={product.id}>
            <img src={product.image} alt={product.name} />
            <div>
              <p>{product.name}</p>
              <small>${product.price} • {product.rating}?</small>
            </div>
            <button onClick={() => onRemove(product.id)}>Remove</button>
          </article>
        ))}
      </div>
    </section>
  );
}

