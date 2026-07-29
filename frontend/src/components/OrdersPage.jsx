import { useEffect, useState } from "react";
import ThemeToggle from "@/components/ThemeToggle";
import { SITE_NAME } from "@/config/site";
import { cancelOrder, getOrder, listOrders, requestReturn } from "@/data/api";

const money = (n) => `$${Number(n ?? 0).toFixed(2)}`;

const formatDate = (iso) =>
  iso
    ? new Date(iso).toLocaleDateString(undefined, {
        year: "numeric",
        month: "short",
        day: "numeric",
      })
    : "";

const formatDateTime = (iso) => (iso ? new Date(iso).toLocaleString() : "");

// Payment status is derived server-side from the order's payment rows
// (orders.py:_latest_payment_status): a refund supersedes the success it
// reverses, a success supersedes earlier declines, else the last attempt.
const PAYMENT_LABEL = {
  success: "Paid",
  failed: "Payment failed",
  refunded: "Refunded",
  unpaid: "Unpaid",
};

// What each status means to a customer, shown under the timeline entry.
const STATUS_BLURB = {
  pending: "Order placed, awaiting payment",
  paid: "Payment received",
  shipped: "On its way",
  delivered: "Delivered",
  cancelled: "Cancelled",
  returned: "Return requested",
  refunded: "Refunded",
};

const ACTION_COPY = {
  cancel: {
    title: "Cancel this order?",
    // Set per-order below — a paid order also gets its money back.
    button: "Cancel order",
    confirm: "Confirm cancellation",
  },
  return: {
    title: "Request a return?",
    body: "We'll refund this order and return the items to stock.",
    button: "Request return",
    confirm: "Confirm return",
  },
};

export default function OrdersPage({ onBack, theme, onToggleTheme }) {
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  // id of the expanded order, plus a cache of full orders already fetched so
  // collapsing and re-expanding doesn't re-hit the API.
  const [openId, setOpenId] = useState(null);
  const [details, setDetails] = useState({});
  const [detailError, setDetailError] = useState("");
  // The cancel/return confirmation is inline rather than window.confirm: a
  // native dialog blocks the page and gives nowhere to type a reason.
  const [pending, setPending] = useState(null); // { orderId, type }
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState("");

  useEffect(() => {
    listOrders()
      .then((data) => setOrders(data.orders || []))
      .catch(() => setError("Could not load your orders. Please try again."))
      .finally(() => setLoading(false));
  }, []);

  const toggle = async (id) => {
    if (openId === id) {
      setOpenId(null);
      return;
    }
    setOpenId(id);
    setDetailError("");
    setPending(null);
    if (details[id]) return;
    try {
      const full = await getOrder(id);
      setDetails((prev) => ({ ...prev, [id]: full }));
    } catch {
      setDetailError("Could not load the details for this order.");
    }
  };

  const startAction = (orderId, type) => {
    setPending({ orderId, type });
    setReason("");
    setActionError("");
  };

  const runAction = async () => {
    if (!pending) return;
    setBusy(true);
    setActionError("");
    try {
      const fn = pending.type === "cancel" ? cancelOrder : requestReturn;
      const updated = await fn(pending.orderId, reason.trim());
      // The response is the full updated order, so it can go straight into the
      // detail cache. The summary rows are re-fetched rather than patched by
      // hand — status, payment status and the action flags all move together,
      // and the server is the one that decides them.
      setDetails((prev) => ({ ...prev, [pending.orderId]: updated }));
      const fresh = await listOrders();
      setOrders(fresh.orders || []);
      setPending(null);
    } catch (err) {
      setActionError(err.message || "That didn't work. Please try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="lens-app">
      <header className="top-nav">
        <div className="brand">
          <span className="brand-icon">?</span>
          {SITE_NAME}
        </div>
        <div className="nav-actions">
          <button type="button" className="cart-btn" onClick={onBack}>
            ← Continue shopping
          </button>
          <ThemeToggle theme={theme} onToggle={onToggleTheme} />
        </div>
      </header>

      <section className="orders-page">
        <div className="cart-heading">
          <h1>Your orders</h1>
        </div>

        {loading && <p className="muted">Loading your orders…</p>}
        {error && !loading && <p className="orders-error">{error}</p>}

        {!loading && !error && orders.length === 0 && (
          <div className="cart-empty">
            <p>You haven&apos;t placed any orders yet.</p>
            <button type="button" className="login-submit" onClick={onBack}>
              Browse the catalog
            </button>
          </div>
        )}

        {!loading && !error && orders.length > 0 && (
          <ul className="orders-list">
            {orders.map((order) => {
              const open = openId === order.id;
              const detail = details[order.id];
              const acting = pending?.orderId === order.id ? pending.type : null;
              return (
                <li key={order.id} className="order-card">
                  <div className="order-card-head">
                    <div className="order-card-id">
                      <p className="order-number">{order.order_number}</p>
                      <p className="muted">{formatDate(order.created_at)}</p>
                    </div>
                    <div className="order-card-meta">
                      <span className={`order-status ${order.status}`}>{order.status}</span>
                      <span className="muted">
                        {order.item_count} {order.item_count === 1 ? "item" : "items"}
                      </span>
                      <span className="muted">
                        {PAYMENT_LABEL[order.payment_status] ?? order.payment_status}
                      </span>
                    </div>
                    <div className="order-card-total">{money(order.total)}</div>
                    <button
                      type="button"
                      className="chip"
                      aria-expanded={open}
                      onClick={() => toggle(order.id)}
                    >
                      {open ? "Hide details" : "View details"}
                    </button>
                  </div>

                  {open && (
                    <div className="order-detail">
                      {!detail && !detailError && <p className="muted">Loading details…</p>}
                      {detailError && <p className="orders-error">{detailError}</p>}
                      {detail && (
                        <>
                          {detail.history?.length > 0 && (
                            <div className="order-timeline-wrap">
                              <h4>Timeline</h4>
                              <ol className="order-timeline">
                                {detail.history.map((h, i) => (
                                  <li key={i} className={`timeline-step ${h.to_status}`}>
                                    <span className="timeline-dot" aria-hidden="true" />
                                    <div>
                                      <p className="timeline-status">
                                        {STATUS_BLURB[h.to_status] ?? h.to_status}
                                      </p>
                                      <p className="muted">{formatDateTime(h.created_at)}</p>
                                      {h.note && <p className="muted timeline-note">{h.note}</p>}
                                    </div>
                                  </li>
                                ))}
                              </ol>
                            </div>
                          )}

                          <ul className="order-items">
                            {detail.items.map((item, i) => (
                              <li key={i} className="order-item">
                                <span className="order-item-name">{item.name}</span>
                                <span className="muted">
                                  {money(item.unit_price)} × {item.quantity}
                                </span>
                                <span>{money(item.line_total)}</span>
                              </li>
                            ))}
                          </ul>

                          <div className="order-detail-cols">
                            <div>
                              <h4>Shipping to</h4>
                              {detail.shipping_address && (
                                <p className="muted">
                                  {detail.shipping_address.full_name}
                                  <br />
                                  {detail.shipping_address.line1}
                                  {detail.shipping_address.line2 && (
                                    <>
                                      <br />
                                      {detail.shipping_address.line2}
                                    </>
                                  )}
                                  <br />
                                  {detail.shipping_address.city}, {detail.shipping_address.state}{" "}
                                  {detail.shipping_address.postal_code}
                                  <br />
                                  {detail.shipping_address.country}
                                </p>
                              )}
                            </div>

                            <div className="order-totals">
                              <div className="cart-summary-row">
                                <span>Subtotal</span>
                                <span>{money(detail.subtotal)}</span>
                              </div>
                              {Number(detail.discount) > 0 && (
                                <div className="cart-summary-row">
                                  <span>
                                    Discount
                                    {detail.coupon_code ? ` (${detail.coupon_code})` : ""}
                                  </span>
                                  <span>−{money(detail.discount)}</span>
                                </div>
                              )}
                              <div className="cart-summary-row">
                                <span>Tax</span>
                                <span>{money(detail.tax)}</span>
                              </div>
                              <div className="cart-summary-row">
                                <span>Shipping</span>
                                <span>{money(detail.shipping)}</span>
                              </div>
                              <div className="cart-summary-row total">
                                <span>Total</span>
                                <span>{money(detail.total)}</span>
                              </div>
                            </div>
                          </div>

                          {detail.payments?.length > 0 && (
                            <div className="order-payments">
                              <h4>Payments</h4>
                              {detail.payments.map((p) => (
                                <p key={p.id} className="muted">
                                  {p.method.toUpperCase()} · {p.status} · {money(p.amount)} ·{" "}
                                  <span className="order-txn">{p.transaction_ref}</span>
                                  {p.status === "refunded" && p.refund_ref && (
                                    <>
                                      <br />
                                      Refunded {formatDateTime(p.refunded_at)} ·{" "}
                                      <span className="order-txn">{p.refund_ref}</span>
                                    </>
                                  )}
                                </p>
                              ))}
                            </div>
                          )}

                          {detail.cancel_reason && (
                            <p className="muted order-reason">
                              Cancellation reason: {detail.cancel_reason}
                            </p>
                          )}
                          {detail.return_reason && (
                            <p className="muted order-reason">
                              Return reason: {detail.return_reason}
                            </p>
                          )}

                          {/* can_cancel / can_return come from the server so the
                              transition rules live in exactly one place. */}
                          {(detail.can_cancel || detail.can_return) && !acting && (
                            <div className="order-actions">
                              {detail.can_cancel && (
                                <button
                                  type="button"
                                  className="chip danger"
                                  onClick={() => startAction(order.id, "cancel")}
                                >
                                  {ACTION_COPY.cancel.button}
                                </button>
                              )}
                              {detail.can_return && (
                                <button
                                  type="button"
                                  className="chip"
                                  onClick={() => startAction(order.id, "return")}
                                >
                                  {ACTION_COPY.return.button}
                                </button>
                              )}
                            </div>
                          )}

                          {acting && (
                            <div className="order-confirm">
                              <h4>{ACTION_COPY[acting].title}</h4>
                              {/* The detail response has no payment_status
                                  (that is a summary-row field), so read the
                                  payment rows directly. */}
                              <p className="muted">
                                {acting === "cancel"
                                  ? detail.payments?.some((p) => p.status === "success")
                                    ? "We'll refund your payment and return the items to stock."
                                    : "Nothing has been charged for this order."
                                  : ACTION_COPY.return.body}
                              </p>
                              <label className="order-reason-label" htmlFor={`reason-${order.id}`}>
                                Reason (optional)
                              </label>
                              <input
                                id={`reason-${order.id}`}
                                type="text"
                                maxLength={255}
                                value={reason}
                                placeholder="Tell us why, if you'd like"
                                onChange={(e) => setReason(e.target.value)}
                              />
                              {actionError && <p className="orders-error">{actionError}</p>}
                              <div className="order-actions">
                                <button
                                  type="button"
                                  className="login-submit"
                                  disabled={busy}
                                  onClick={runAction}
                                >
                                  {busy ? "Working…" : ACTION_COPY[acting].confirm}
                                </button>
                                <button
                                  type="button"
                                  className="chip"
                                  disabled={busy}
                                  onClick={() => setPending(null)}
                                >
                                  Keep order
                                </button>
                              </div>
                            </div>
                          )}
                        </>
                      )}
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}
