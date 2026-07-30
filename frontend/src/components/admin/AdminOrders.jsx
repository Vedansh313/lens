import { useCallback, useEffect, useState } from "react";
import { adminListOrders, adminSetOrderStatus } from "@/data/admin";
import { Empty, ErrorNote, Loading, dateTime, money, plural } from "@/components/admin/shared";

const STATUSES = [
  "pending",
  "paid",
  "shipped",
  "delivered",
  "cancelled",
  "returned",
  "refunded",
];

const PAGE = 25;

// Moves that give the customer their money back. The server does the refund
// and the restock either way; this only decides whether the admin is warned
// first, because these are the ones that cannot be walked back.
const UNWINDING = new Set(["cancelled", "returned"]);

export default function AdminOrders() {
  const [orders, setOrders] = useState([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [status, setStatus] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  // { orderId, to } — the transition awaiting confirmation.
  const [pending, setPending] = useState(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState("");

  const load = useCallback(() => {
    setLoading(true);
    setError("");
    adminListOrders({ status: status || undefined, limit: PAGE, offset })
      .then((data) => {
        setOrders(data.orders || []);
        setTotal(data.total || 0);
      })
      .catch(() => setError("Could not load orders."))
      .finally(() => setLoading(false));
  }, [status, offset]);

  useEffect(load, [load]);

  const start = (orderId, to) => {
    setPending({ orderId, to });
    setNote("");
    setActionError("");
  };

  const confirm = async () => {
    if (!pending) return;
    setBusy(true);
    setActionError("");
    try {
      await adminSetOrderStatus(pending.orderId, pending.to, note);
      setPending(null);
      setNote("");
      load();
    } catch (err) {
      // The server rejects illegal moves with a 409 that names the legal ones;
      // show that rather than a generic failure.
      setActionError(err.message || "Could not change the status.");
    } finally {
      setBusy(false);
    }
  };

  const pages = Math.ceil(total / PAGE) || 1;
  const page = Math.floor(offset / PAGE) + 1;

  return (
    <div className="admin-section">
      <div className="admin-section-head">
        <h2>Orders</h2>
        <div className="admin-filters">
          <label className="admin-field">
            <span>Status</span>
            <select
              value={status}
              onChange={(e) => {
                setStatus(e.target.value);
                setOffset(0);
              }}
            >
              <option value="">All</option>
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>

      <ErrorNote>{error}</ErrorNote>
      {loading && <Loading what="orders" />}
      {!loading && !error && orders.length === 0 && (
        <Empty>No orders{status ? ` with status “${status}”` : ""}.</Empty>
      )}

      {!loading && !error && orders.length > 0 && (
        <>
          <p className="muted">{plural(total, "order")}</p>
          <table className="admin-table wide">
            <thead>
              <tr>
                <th>Order</th>
                <th>Customer</th>
                <th>Status</th>
                <th className="num">Items</th>
                <th className="num">Total</th>
                <th>Placed</th>
                <th>Move to</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((o) => (
                <tr key={o.id}>
                  <td className="mono">{o.order_number}</td>
                  <td>
                    {o.user.name}
                    <span className="muted admin-sub">{o.user.email}</span>
                  </td>
                  <td>
                    <span className={`order-status ${o.status}`}>{o.status}</span>
                  </td>
                  <td className="num">{o.item_count}</td>
                  <td className="num">{money(o.total)}</td>
                  <td className="muted">{dateTime(o.created_at)}</td>
                  <td>
                    {/* Only the moves the server says are legal from here, so
                        the UI cannot offer a transition that 409s. */}
                    {o.next_statuses.length === 0 ? (
                      <span className="muted">final</span>
                    ) : (
                      <div className="admin-actions">
                        {o.next_statuses.map((s) => (
                          <button
                            key={s}
                            type="button"
                            className={`chip${UNWINDING.has(s) ? " danger" : ""}`}
                            onClick={() => start(o.id, s)}
                          >
                            {s}
                          </button>
                        ))}
                      </div>
                    )}
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

      {/* Inline confirmation rather than window.confirm: a native dialog blocks
          the page and gives nowhere to type the note that lands in the order's
          history. */}
      {pending && (
        <div className="admin-confirm" role="dialog" aria-label="Confirm status change">
          <h4>
            Move order to <span className={`order-status ${pending.to}`}>{pending.to}</span>?
          </h4>
          {UNWINDING.has(pending.to) && (
            <p className="admin-warn">
              This refunds the payment and returns the items to stock. It cannot be undone.
            </p>
          )}
          <label className="admin-field">
            <span>Note (optional, recorded in the order history)</span>
            <input
              type="text"
              value={note}
              maxLength={255}
              onChange={(e) => setNote(e.target.value)}
              placeholder="e.g. Dispatched via courier"
            />
          </label>
          <ErrorNote>{actionError}</ErrorNote>
          <div className="admin-actions">
            <button type="button" className="login-submit" disabled={busy} onClick={confirm}>
              {busy ? "Working…" : `Confirm ${pending.to}`}
            </button>
            <button
              type="button"
              className="chip"
              disabled={busy}
              onClick={() => setPending(null)}
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
