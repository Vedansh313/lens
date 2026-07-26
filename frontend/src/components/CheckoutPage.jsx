import { useEffect, useMemo, useState } from "react";
import ThemeToggle from "@/components/ThemeToggle";
import { SITE_NAME } from "@/config/site";
import { createAddress, createOrder, getAddresses, getQuote, payOrder } from "@/data/api";

const EMPTY_ADDRESS = {
  full_name: "",
  phone: "",
  line1: "",
  line2: "",
  city: "",
  state: "",
  postal_code: "",
  country: "US",
};

export default function CheckoutPage({ onPlaced, onBack, theme, onToggleTheme }) {
  const [addresses, setAddresses] = useState([]);
  const [selectedAddressId, setSelectedAddressId] = useState(null);
  const [usingNew, setUsingNew] = useState(false);
  const [newAddress, setNewAddress] = useState(EMPTY_ADDRESS);

  const [couponInput, setCouponInput] = useState("");
  const [appliedCoupon, setAppliedCoupon] = useState("");
  const [quote, setQuote] = useState(null);

  const [method, setMethod] = useState("card");
  const [card, setCard] = useState({ card_number: "", expiry: "", cvv: "", card_name: "" });
  const [upiId, setUpiId] = useState("");
  const [wallet, setWallet] = useState("Paytm");

  const [pendingOrderId, setPendingOrderId] = useState(null);
  const [placing, setPlacing] = useState(false);
  const [error, setError] = useState("");

  // Load saved addresses once; default-select one.
  useEffect(() => {
    getAddresses()
      .then((list) => {
        setAddresses(list);
        if (list.length) {
          setSelectedAddressId((list.find((a) => a.is_default) || list[0]).id);
        } else {
          setUsingNew(true);
        }
      })
      .catch(() => setUsingNew(true));
  }, []);

  // Re-quote whenever the applied coupon changes.
  useEffect(() => {
    getQuote(appliedCoupon)
      .then(setQuote)
      .catch(() => setQuote(null));
  }, [appliedCoupon]);

  // Changing address/coupon invalidates any already-created pending order so we
  // don't pay for a stale order.
  useEffect(() => {
    setPendingOrderId(null);
  }, [selectedAddressId, usingNew, appliedCoupon, JSON.stringify(newAddress)]);

  const money = (n) => `$${Number(n ?? 0).toFixed(2)}`;
  const cartEmpty = quote && quote.item_count === 0;

  const buildPayment = () => {
    if (method === "card") return { method: "card", ...card };
    if (method === "upi") return { method: "upi", upi_id: upiId };
    return { method: "wallet", wallet };
  };

  const applyCoupon = () => setAppliedCoupon(couponInput.trim());

  const placeOrder = async () => {
    setError("");
    setPlacing(true);
    try {
      // Resolve the shipping address.
      let addressId = selectedAddressId;
      if (usingNew) {
        const saved = await createAddress(newAddress);
        setAddresses((prev) => [...prev, saved]);
        addressId = saved.id;
        setSelectedAddressId(saved.id);
        setUsingNew(false);
      }
      if (!addressId) {
        setError("Please choose or add a shipping address.");
        return;
      }

      // Create the order once; reuse it on a payment retry.
      let orderId = pendingOrderId;
      if (!orderId) {
        const order = await createOrder({
          address_id: addressId,
          coupon_code: appliedCoupon || null,
        });
        orderId = order.id;
        setPendingOrderId(orderId);
      }

      const result = await payOrder(orderId, buildPayment());
      onPlaced(result.order); // success -> confirmation
    } catch (err) {
      setError(err.message || "Something went wrong. Please try again.");
    } finally {
      setPlacing(false);
    }
  };

  const field = (obj, setObj, key, label, extra = {}) => (
    <label className="checkout-field">
      {label}
      <input
        value={obj[key]}
        onChange={(e) => setObj({ ...obj, [key]: e.target.value })}
        {...extra}
      />
    </label>
  );

  return (
    <div className="lens-app">
      <header className="top-nav">
        <div className="brand">
          <span className="brand-icon">?</span>
          {SITE_NAME}
        </div>
        <div className="nav-actions">
          <button type="button" className="cart-btn" onClick={onBack}>
            ← Back to cart
          </button>
          <ThemeToggle theme={theme} onToggle={onToggleTheme} />
        </div>
      </header>

      <section className="checkout-page">
        <h1>Checkout</h1>

        {cartEmpty ? (
          <div className="cart-empty">
            <p>Your cart is empty.</p>
            <button type="button" className="login-submit" onClick={onBack}>
              Back to cart
            </button>
          </div>
        ) : (
          <div className="checkout-layout">
            <div className="checkout-main">
              {/* Address */}
              <div className="checkout-block">
                <h3>Shipping address</h3>
                {addresses.map((a) => (
                  <label key={a.id} className="radio-row">
                    <input
                      type="radio"
                      name="address"
                      checked={!usingNew && selectedAddressId === a.id}
                      onChange={() => {
                        setUsingNew(false);
                        setSelectedAddressId(a.id);
                      }}
                    />
                    <span>
                      {a.full_name}, {a.line1}, {a.city}, {a.state} {a.postal_code}
                      {a.is_default ? " (default)" : ""}
                    </span>
                  </label>
                ))}
                <label className="radio-row">
                  <input type="radio" name="address" checked={usingNew} onChange={() => setUsingNew(true)} />
                  <span>Use a new address</span>
                </label>

                {usingNew && (
                  <div className="address-form">
                    {field(newAddress, setNewAddress, "full_name", "Full name")}
                    {field(newAddress, setNewAddress, "phone", "Phone")}
                    {field(newAddress, setNewAddress, "line1", "Address line 1")}
                    {field(newAddress, setNewAddress, "line2", "Address line 2 (optional)")}
                    {field(newAddress, setNewAddress, "city", "City")}
                    {field(newAddress, setNewAddress, "state", "State")}
                    {field(newAddress, setNewAddress, "postal_code", "Postal code")}
                    {field(newAddress, setNewAddress, "country", "Country")}
                  </div>
                )}
              </div>

              {/* Payment */}
              <div className="checkout-block">
                <h3>Payment</h3>
                <div className="method-tabs">
                  {["card", "upi", "wallet"].map((m) => (
                    <button
                      key={m}
                      type="button"
                      className={`method-tab ${method === m ? "active" : ""}`}
                      onClick={() => setMethod(m)}
                    >
                      {m === "upi" ? "UPI" : m[0].toUpperCase() + m.slice(1)}
                    </button>
                  ))}
                </div>

                {method === "card" && (
                  <div className="address-form">
                    {field(card, setCard, "card_number", "Card number", { placeholder: "4242 4242 4242 4242", inputMode: "numeric" })}
                    {field(card, setCard, "expiry", "Expiry (MM/YY)", { placeholder: "12/29" })}
                    {field(card, setCard, "cvv", "CVV", { placeholder: "123", inputMode: "numeric" })}
                    {field(card, setCard, "card_name", "Name on card")}
                    <p className="test-hint">Test: 4242 4242 4242 4242 succeeds · a number ending 0002 is declined.</p>
                  </div>
                )}
                {method === "upi" && (
                  <div className="address-form">
                    <label className="checkout-field">
                      UPI ID
                      <input value={upiId} onChange={(e) => setUpiId(e.target.value)} placeholder="name@bank" />
                    </label>
                    <p className="test-hint">Test: any name@bank succeeds · fail@test is declined.</p>
                  </div>
                )}
                {method === "wallet" && (
                  <div className="address-form">
                    <label className="checkout-field">
                      Wallet
                      <select value={wallet} onChange={(e) => setWallet(e.target.value)}>
                        <option>Paytm</option>
                        <option>GPay</option>
                        <option>PhonePe</option>
                      </select>
                    </label>
                  </div>
                )}
              </div>
            </div>

            {/* Summary */}
            <aside className="checkout-summary">
              <h3>Order summary</h3>
              <div className="coupon-row">
                <input
                  value={couponInput}
                  onChange={(e) => setCouponInput(e.target.value)}
                  placeholder="Coupon code"
                />
                <button type="button" onClick={applyCoupon}>Apply</button>
              </div>
              {quote?.coupon_error && <p className="login-error">{quote.coupon_error}</p>}
              {quote?.coupon_code && <p className="coupon-ok">Applied: {quote.coupon_code}</p>}

              <div className="cart-summary-row"><span>Subtotal ({quote?.item_count ?? 0})</span><span>{money(quote?.subtotal)}</span></div>
              {quote?.discount > 0 && (
                <div className="cart-summary-row"><span>Discount</span><span>−{money(quote?.discount)}</span></div>
              )}
              <div className="cart-summary-row"><span>Tax</span><span>{money(quote?.tax)}</span></div>
              <div className="cart-summary-row"><span>Shipping</span><span>{quote?.shipping ? money(quote?.shipping) : "Free"}</span></div>
              <div className="cart-summary-row total"><span>Total</span><span>{money(quote?.total)}</span></div>

              {error && <p className="login-error" role="alert">{error}</p>}

              <button type="button" className="login-submit" onClick={placeOrder} disabled={placing}>
                {placing ? "Placing order…" : `Pay ${money(quote?.total)}`}
              </button>
              <p className="test-hint">Simulated payment — no real charge is made.</p>
            </aside>
          </div>
        )}
      </section>
    </div>
  );
}
