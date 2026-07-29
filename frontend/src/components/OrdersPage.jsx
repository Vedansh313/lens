import { useEffect, useState } from "react";
import ThemeToggle from "@/components/ThemeToggle";
import { SITE_NAME } from "@/config/site";
import { getOrder, listOrders } from "@/data/api";

const money = (n) => `$${Number(n ?? 0).toFixed(2)}`;

const formatDate = (iso) =>
  iso
    ? new Date(iso).toLocaleDateString(undefined, {
        year: "numeric",
        month: "short",
        day: "numeric",
      })
    : "";

// Payment status is derived server-side from the order's payment rows
// (orders.py:_latest_payment_status): "success" once any payment succeeded,
// otherwise the last attempt's status, or "unpaid" when none was attempted.
const PAYMENT_LABEL = {
  success: "Paid",
  failed: "Payment failed",
  unpaid: "Unpaid",
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
    if (details[id]) return;
    try {
      const full = await getOrder(id);
      setDetails((prev) => ({ ...prev, [id]: full }));
    } catch {
      setDetailError("Could not load the details for this order.");
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
                                </p>
                              ))}
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
