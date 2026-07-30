// Small pieces shared by the admin panels (Phase 4, step 10). Kept together so
// five panels format money, dates and errors identically — an admin comparing
// two screens must not see the same number rendered two ways.

export const money = (n) => `$${Number(n ?? 0).toFixed(2)}`;

export const number = (n) => Number(n ?? 0).toLocaleString();

/** "1 unit" / "2 units". Worth a helper: these counts are read at a glance and
 *  "1 units" is the kind of thing that makes a panel look unfinished. */
export const plural = (n, one, many = `${one}s`) => `${number(n)} ${n === 1 ? one : many}`;

export const shortDate = (iso) =>
  iso ? new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" }) : "—";

export const dateTime = (iso) => (iso ? new Date(iso).toLocaleString() : "—");

// Backend returns null (not 0) when a figure has no data behind it — no
// baseline to compare against, or nothing reached the milestone. Rendering
// those as "0" would state a measurement that was never taken.
export const orDash = (v, format = (x) => x) => (v === null || v === undefined ? "—" : format(v));

export const hours = (h) =>
  h === null || h === undefined
    ? "—"
    : h < 48
      ? `${h.toFixed(1)}h`
      : `${(h / 24).toFixed(1)}d`;

export const iso = (d) => d.toISOString().slice(0, 10);

/** A window of the last `days` days, inclusive of today. */
export function lastDays(days) {
  const end = new Date();
  const start = new Date();
  start.setDate(start.getDate() - (days - 1));
  return { start: iso(start), end: iso(end) };
}

export function Loading({ what = "data" }) {
  return <p className="muted">Loading {what}…</p>;
}

export function ErrorNote({ children }) {
  if (!children) return null;
  return (
    <p className="admin-error" role="alert">
      {children}
    </p>
  );
}

export function Empty({ children }) {
  return <p className="admin-empty">{children}</p>;
}

/** A labelled headline figure, optionally with a period-on-period delta. */
export function Stat({ label, value, delta, hint }) {
  return (
    <div className="admin-stat">
      <p className="admin-stat-label">{label}</p>
      <p className="admin-stat-value">{value}</p>
      {delta !== null && delta !== undefined && (
        <p className={`admin-stat-delta ${delta >= 0 ? "up" : "down"}`}>
          {delta >= 0 ? "▲" : "▼"} {Math.abs(delta).toFixed(1)}% vs previous
        </p>
      )}
      {hint && <p className="muted admin-stat-hint">{hint}</p>}
    </div>
  );
}

/** Preset date-range picker. Presets rather than two date inputs: every
 *  question an admin asks here is "recently", and the server caps the span. */
export const RANGES = [
  { id: "7", label: "7 days", days: 7 },
  { id: "30", label: "30 days", days: 30 },
  { id: "90", label: "90 days", days: 90 },
  { id: "365", label: "12 months", days: 365 },
];

export function RangePicker({ value, onChange }) {
  return (
    <div className="admin-range" role="group" aria-label="Date range">
      {RANGES.map((r) => (
        <button
          key={r.id}
          type="button"
          className={`chip${value === r.id ? " active" : ""}`}
          aria-pressed={value === r.id}
          onClick={() => onChange(r.id)}
        >
          {r.label}
        </button>
      ))}
    </div>
  );
}

/** Inline SVG bar chart. No charting library — AGENTS.md rules out frameworks
 *  beyond React, and a bar per bucket is a rect per bucket.
 *
 *  Bars are drawn for every point including zeros, because the series is
 *  gap-filled server-side and a quiet day is a real data point. */
export function BarChart({ points, valueKey = "revenue", labelKey = "bucket", format = money }) {
  const values = points.map((p) => Number(p[valueKey] ?? 0));
  const max = Math.max(...values, 0);
  if (!points.length) return <Empty>No data in this range.</Empty>;

  return (
    <div className="admin-chart">
      <div className="admin-chart-bars">
        {points.map((p, i) => {
          const v = values[i];
          // Zero stays visibly zero: a floor height would make an empty day
          // look like a small sale.
          const pct = max > 0 ? (v / max) * 100 : 0;
          return (
            <div key={p[labelKey] ?? i} className="admin-bar-slot">
              <div
                className={`admin-bar${v === 0 ? " zero" : ""}`}
                style={{ height: `${pct}%` }}
                title={`${p[labelKey]}: ${format(v)}`}
              />
            </div>
          );
        })}
      </div>
      <div className="admin-chart-axis">
        <span>{points[0]?.[labelKey]}</span>
        {points.length > 1 && <span>{points[points.length - 1]?.[labelKey]}</span>}
      </div>
      <p className="muted admin-chart-peak">Peak: {format(max)}</p>
    </div>
  );
}
