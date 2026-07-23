export default function InsightsPanel({ query, selectedImage }) {
  const prompt = query.toLowerCase();
  const insights = {
    color: prompt.includes("olive") ? "Olive" : prompt.includes("white") ? "White" : "Warm neutral",
    texture: prompt.includes("rib") ? "Ribbed" : prompt.includes("leather") ? "Leather" : "Soft knit",
    style: prompt.includes("minimal") ? "Minimal" : "Contemporary",
    category: prompt.includes("bag") ? "Bag" : prompt.includes("shoe") ? "Shoes" : "Mixed apparel",
  };

  return (
    <section className="insights">
      <h3>AI Search Insights</h3>
      <p>{selectedImage ? "Image features extracted" : "Text prompt analysis"}</p>
      <div className="insight-grid">
        {Object.entries(insights).map(([key, value]) => (
          <article key={key}>
            <h4>{key}</h4>
            <p>{value}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

