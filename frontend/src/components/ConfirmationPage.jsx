import { useEffect, useState } from "react";
import ThemeToggle from "@/components/ThemeToggle";
import { SITE_NAME } from "@/config/site";
import { getInvoice } from "@/data/api";

export default function ConfirmationPage({ order, onDone, theme, onToggleTheme }) {
  const [invoice, setInvoice] = useState(null);

  useEffect(() => {
    if (order?.id) getInvoice(order.id).then(setInvoice).catch(() => setInvoice(null));
  }, [order?.id]);

  const money = (n) => `$${Number(n ?? 0).toFixed(2)}`;
  const addr = invoice?.bill_to;

  return (
    <div className="lens-app">
      <header className="top-nav no-print">
        <div className="brand">
          <span className="brand-icon">?</span>
          {SITE_NAME}
        </div>
        <div className="nav-actions">
          <button type="button" className="cart-btn" onClick={onDone}>
            Continue shopping
          </button>
          <ThemeToggle theme={theme} onToggle={onToggleTheme} />
        </div>
      </header>

      <section className="confirmation-page">
        <div className="confirmation-hero no-print">
          <div className="confirm-check" aria-hidden="true">✓</div>
          <h1>Order confirmed</h1>
          <p>
            Thank you! Your order <strong>{order?.order_number}</strong> is paid and being prepared.
          </p>
          <div className="confirm-actions">
            <button type="button" className="login-submit" onClick={() => window.print()}>
              Print invoice
            </button>
            <button type="button" className="chip" onClick={onDone}>
              Continue shopping
            </button>
          </div>
        </div>

        {invoice && (
          <div className="invoice">
            <div className="invoice-head">
              <div>
                <h2>Invoice</h2>
                <p className="muted">{invoice.invoice_number}</p>
                <p className="muted">
                  {invoice.issued_at ? new Date(invoice.issued_at).toLocaleString() : ""}
                </p>
              </div>
              <div className="invoice-seller">
                <strong>{invoice.seller?.name}</strong>
                <p className="muted">{invoice.seller?.email}</p>
                <span className={`invoice-status ${invoice.status}`}>{invoice.status}</span>
              </div>
            </div>

            {addr && (
              <div className="invoice-billto">
                <h4>Bill to</h4>
                <p>{addr.full_name}</p>
                <p className="muted">
                  {addr.line1}
                  {addr.line2 ? `, ${addr.line2}` : ""}, {addr.city}, {addr.state} {addr.postal_code},{" "}
                  {addr.country}
                </p>
                <p className="muted">{addr.phone}</p>
              </div>
            )}

            <table className="invoice-table">
              <thead>
                <tr>
                  <th>Item</th>
                  <th>Qty</th>
                  <th>Unit</th>
                  <th>Amount</th>
                </tr>
              </thead>
              <tbody>
                {invoice.items.map((item, i) => (
                  <tr key={i}>
                    <td>{item.name}</td>
                    <td>{item.quantity}</td>
                    <td>{money(item.unit_price)}</td>
                    <td>{money(item.line_total)}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            <div className="invoice-totals">
              <div className="cart-summary-row"><span>Subtotal</span><span>{money(invoice.totals.subtotal)}</span></div>
              {invoice.totals.discount > 0 && (
                <div className="cart-summary-row">
                  <span>Discount{invoice.coupon_code ? ` (${invoice.coupon_code})` : ""}</span>
                  <span>−{money(invoice.totals.discount)}</span>
                </div>
              )}
              <div className="cart-summary-row"><span>Tax</span><span>{money(invoice.totals.tax)}</span></div>
              <div className="cart-summary-row">
                <span>Shipping</span>
                <span>{invoice.totals.shipping ? money(invoice.totals.shipping) : "Free"}</span>
              </div>
              <div className="cart-summary-row total"><span>Total</span><span>{money(invoice.totals.total)}</span></div>
            </div>

            {invoice.payment && (
              <p className="invoice-payment muted">
                Paid via {invoice.payment.method.toUpperCase()} · {invoice.payment.transaction_ref}
              </p>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
