import ThemeToggle from "@/components/ThemeToggle";
import { SITE_NAME } from "@/config/site";
import { mapProduct } from "@/data/api";

export default function CartPage({ cart, onSetQuantity, onRemove, onClear, onBack, onCheckout, theme, onToggleTheme }) {
  const items = (cart.items || []).map(mapProduct);

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

      <section className="cart-page">
        <div className="cart-heading">
          <h1>Your cart</h1>
          {items.length > 0 && (
            <button type="button" className="chip" onClick={onClear}>
              Clear cart
            </button>
          )}
        </div>

        {items.length === 0 ? (
          <div className="cart-empty">
            <p>Your cart is empty.</p>
            <button type="button" className="login-submit" onClick={onBack}>
              Browse the catalog
            </button>
          </div>
        ) : (
          <div className="cart-layout">
            <ul className="cart-items">
              {items.map((item) => (
                <li key={item.id} className="cart-item">
                  <img src={item.image} alt={item.name} loading="lazy" />
                  <div className="cart-item-info">
                    <p className="cart-item-name">{item.name}</p>
                    <p className="muted">
                      {item.category} · {item.color}
                    </p>
                    <p className="cart-item-price">${item.price} each</p>
                  </div>
                  <div className="cart-qty">
                    <button
                      type="button"
                      aria-label="Decrease quantity"
                      disabled={item.quantity <= 1}
                      onClick={() => onSetQuantity(item.id, item.quantity - 1)}
                    >
                      −
                    </button>
                    <span>{item.quantity}</span>
                    <button
                      type="button"
                      aria-label="Increase quantity"
                      onClick={() => onSetQuantity(item.id, item.quantity + 1)}
                    >
                      +
                    </button>
                  </div>
                  <div className="cart-item-subtotal">${item.subtotal}</div>
                  <button
                    type="button"
                    className="cart-remove"
                    aria-label="Remove item"
                    onClick={() => onRemove(item.id)}
                  >
                    Remove
                  </button>
                </li>
              ))}
            </ul>

            <aside className="cart-summary">
              <h3>Summary</h3>
              <div className="cart-summary-row">
                <span>Items</span>
                <span>{cart.item_count}</span>
              </div>
              <div className="cart-summary-row total">
                <span>Total</span>
                <span>${cart.total}</span>
              </div>
              <button type="button" className="login-submit" onClick={onCheckout}>
                Checkout
              </button>
            </aside>
          </div>
        )}
      </section>
    </div>
  );
}
