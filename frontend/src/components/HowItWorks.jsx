import { howItWorks } from "@/data/mockData";

export default function HowItWorks() {
  return (
    <section className="how-it-works">
      <h3>How it works</h3>
      <div className="steps">
        {howItWorks.map((step) => (
          <article key={step.title}>
            <span className="icon">{step.icon}</span>
            <h4>{step.title}</h4>
            <p>{step.text}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

