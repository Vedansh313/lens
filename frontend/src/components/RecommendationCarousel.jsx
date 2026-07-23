export default function RecommendationCarousel({ items, title }) {
  return (
    <section className="carousel-section">
      <h3>{title}</h3>
      <div className="carousel">
        {items.map((product) => (
          <article key={product.id} className="mini-card">
            <img src={product.image} alt={product.name} loading="lazy" />
            <p>{product.name}</p>
            <span>${product.price}</span>
          </article>
        ))}
      </div>
    </section>
  );
}

