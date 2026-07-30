import { useCallback, useEffect, useState } from "react";
import { inventoryAdjust, inventoryHistory, inventoryList, inventorySummary } from "@/data/admin";
import {
  Empty,
  ErrorNote,
  Loading,
  Stat,
  dateTime,
  money,
  number,
  plural,
} from "@/components/admin/shared";

const PAGE = 25;
const DEFAULT_THRESHOLD = 5;

const STATES = [
  { id: "all", label: "All" },
  { id: "out", label: "Out of stock" },
  { id: "low", label: "Low" },
  { id: "ok", label: "Healthy" },
];

// How a ledger row reads to a human. 'sale' and 'restock' rows are written by
// the order flow, not by an admin, so they carry an order rather than a person.
const SOURCE_LABEL = { manual: "Manual", sale: "Sale", restock: "Restock" };

export default function AdminInventory() {
  const [state, setState] = useState("low");
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Adjustment drawer for one product.
  const [target, setTarget] = useState(null);
  const [mode, setMode] = useState("delta");
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState("");
  const [history, setHistory] = useState(null);

  const load = useCallback(() => {
    setLoading(true);
    setError("");
    Promise.all([
      inventoryList({
        state,
        q: query || undefined,
        threshold: DEFAULT_THRESHOLD,
        limit: PAGE,
        offset,
      }),
      inventorySummary(DEFAULT_THRESHOLD),
    ])
      .then(([list, sum]) => {
        setRows(list.products || []);
        setTotal(list.total || 0);
        setSummary(sum);
      })
      .catch(() => setError("Could not load inventory."))
      .finally(() => setLoading(false));
  }, [state, query, offset]);

  useEffect(load, [load]);

  const open = async (product) => {
    setTarget(product);
    setMode("delta");
    setAmount("");
    setReason("");
    setActionError("");
    setHistory(null);
    try {
      setHistory(await inventoryHistory(product.id, 20));
    } catch {
      // The ledger is context, not the point of the drawer — failing to load it
      // must not block the adjustment itself.
      setHistory({ adjustments: [], failed: true });
    }
  };

  const submit = async (e) => {
    e.preventDefault();
    if (!target) return;
    const n = Number(amount);
    if (!Number.isInteger(n)) {
      setActionError("Enter a whole number.");
      return;
    }
    if (mode === "delta" && n === 0) {
      setActionError("A change of zero does nothing.");
      return;
    }
    if (mode === "set" && n < 0) {
      setActionError("Stock cannot be negative.");
      return;
    }
    setBusy(true);
    setActionError("");
    try {
      await inventoryAdjust(target.id, {
        ...(mode === "delta" ? { delta: n } : { setTo: n }),
        reason: reason.trim(),
      });
      setTarget(null);
      load();
    } catch (err) {
      // Server rejects an over-removal with a 409 naming the shortfall.
      setActionError(err.message || "Could not adjust stock.");
    } finally {
      setBusy(false);
    }
  };

  const pages = Math.ceil(total / PAGE) || 1;
  const page = Math.floor(offset / PAGE) + 1;

  return (
    <div className="admin-section">
      <div className="admin-section-head">
        <h2>Inventory</h2>
      </div>

      {summary && (
        <div className="admin-stats">
          <Stat label="Out of stock" value={number(summary.out_of_stock)} />
          <Stat
            label="Low stock"
            value={number(summary.low_stock)}
            hint={`at or below ${summary.threshold} units`}
          />
          <Stat label="Healthy" value={number(summary.healthy)} />
          <Stat label="Units on hand" value={number(summary.total_units)} />
        </div>
      )}

      <div className="admin-filters">
        <div className="admin-range" role="group" aria-label="Stock state">
          {STATES.map((s) => (
            <button
              key={s.id}
              type="button"
              className={`chip${state === s.id ? " active" : ""}`}
              aria-pressed={state === s.id}
              onClick={() => {
                setState(s.id);
                setOffset(0);
              }}
            >
              {s.label}
            </button>
          ))}
        </div>
        <form
          className="admin-search"
          onSubmit={(e) => {
            e.preventDefault();
            setQuery(q.trim());
            setOffset(0);
          }}
        >
          <input
            type="search"
            value={q}
            placeholder="Search products…"
            onChange={(e) => setQ(e.target.value)}
          />
          <button type="submit" className="chip">
            Search
          </button>
        </form>
      </div>

      <ErrorNote>{error}</ErrorNote>
      {loading && <Loading what="inventory" />}
      {!loading && !error && rows.length === 0 && (
        <Empty>
          Nothing here{state === "out" ? " — nothing is out of stock" : ""}
          {state === "low" ? " — nothing is running low" : ""}.
        </Empty>
      )}

      {!loading && !error && rows.length > 0 && (
        <>
          <p className="muted">{plural(total, "product")}, most urgent first</p>
          <table className="admin-table wide">
            <thead>
              <tr>
                <th>Product</th>
                <th>Category</th>
                <th className="num">Price</th>
                <th className="num">Stock</th>
                <th>State</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((p) => (
                <tr key={p.id} className={p.is_active ? "" : "inactive-row"}>
                  <td>
                    {p.name}
                    {!p.is_active && <span className="admin-flag">inactive</span>}
                  </td>
                  <td className="muted">{p.article_type}</td>
                  <td className="num">{money(p.price)}</td>
                  <td className="num strong">{number(p.stock_quantity)}</td>
                  <td>
                    <span className={`stock-state ${p.stock_state}`}>{p.stock_state}</span>
                  </td>
                  <td>
                    <button type="button" className="chip" onClick={() => open(p)}>
                      Adjust
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {pages > 1 && (
            <div className="pager">
              <button
                type="button"
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - PAGE))}
              >
                ← Previous
              </button>
              <span>
                Page {page} of {pages}
              </span>
              <button
                type="button"
                disabled={offset + PAGE >= total}
                onClick={() => setOffset(offset + PAGE)}
              >
                Next →
              </button>
            </div>
          )}
        </>
      )}

      {target && (
        <div className="admin-confirm wide" role="dialog" aria-label="Adjust stock">
          <h4>{target.name}</h4>
          <p className="muted">Currently {plural(target.stock_quantity, "unit")}.</p>

          <form onSubmit={submit}>
            <div className="admin-range" role="group" aria-label="Adjustment mode">
              <button
                type="button"
                className={`chip${mode === "delta" ? " active" : ""}`}
                aria-pressed={mode === "delta"}
                onClick={() => setMode("delta")}
              >
                Add / remove
              </button>
              <button
                type="button"
                className={`chip${mode === "set" ? " active" : ""}`}
                aria-pressed={mode === "set"}
                onClick={() => setMode("set")}
              >
                Set exact
              </button>
            </div>
            <p className="muted admin-hint">
              {mode === "delta"
                ? "A relative change survives a sale happening while you type. Prefer it."
                : "Overwrites whatever the number is now, including any sale since this page loaded."}
            </p>

            <label className="admin-field">
              <span>{mode === "delta" ? "Change by (e.g. 20 or -3)" : "Set to"}</span>
              <input
                type="number"
                step="1"
                value={amount}
                required
                onChange={(e) => setAmount(e.target.value)}
              />
            </label>
            <label className="admin-field">
              <span>Reason (required — recorded in the stock ledger)</span>
              <input
                type="text"
                value={reason}
                required
                maxLength={255}
                placeholder="e.g. Delivery received, damaged units written off"
                onChange={(e) => setReason(e.target.value)}
              />
            </label>

            <ErrorNote>{actionError}</ErrorNote>
            <div className="admin-actions">
              <button type="submit" className="login-submit" disabled={busy}>
                {busy ? "Saving…" : "Apply adjustment"}
              </button>
              <button
                type="button"
                className="chip"
                disabled={busy}
                onClick={() => setTarget(null)}
              >
                Cancel
              </button>
            </div>
          </form>

          <div className="admin-history">
            <h5>Recent stock movements</h5>
            {!history && <Loading what="history" />}
            {history?.failed && <p className="muted">Could not load the ledger.</p>}
            {history && !history.failed && history.adjustments.length === 0 && (
              <p className="muted">
                No recorded movements. Seeded stock predates the ledger, so a product only
                appears here once something changes it.
              </p>
            )}
            {history && !history.failed && history.adjustments.length > 0 && (
              <table className="admin-table">
                <thead>
                  <tr>
                    <th>When</th>
                    <th>Source</th>
                    <th className="num">Change</th>
                    <th className="num">After</th>
                    <th>Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {history.adjustments.map((a) => (
                    <tr key={a.id}>
                      <td className="muted">{dateTime(a.created_at)}</td>
                      <td>{SOURCE_LABEL[a.source] ?? a.source}</td>
                      <td className={`num ${a.delta >= 0 ? "up" : "down"}`}>
                        {a.delta > 0 ? `+${a.delta}` : a.delta}
                      </td>
                      <td className="num">{a.quantity_after}</td>
                      <td className="muted">
                        {a.reason ?? "—"}
                        {a.order_id && <span className="admin-sub">order #{a.order_id}</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
