import { useCallback, useEffect, useState } from "react";
import {
  adminCreateProduct,
  adminDeactivateProduct,
  adminListProducts,
  adminUpdateProduct,
} from "@/data/admin";
import { Empty, ErrorNote, Loading, money, number, plural } from "@/components/admin/shared";

const PAGE = 25;

const BLANK = {
  product_display_name: "",
  master_category: "",
  sub_category: "",
  article_type: "",
  gender: "",
  base_colour: "",
  season: "",
  usage: "",
  year: "",
  price: "",
  stock_quantity: "",
};

// Only the fields the create form sends. Optional ones are dropped when blank
// rather than sent as "" — the server types them as nullable strings/ints and
// an empty string is not the same as "not provided".
function payloadFrom(form) {
  const out = {
    product_display_name: form.product_display_name.trim(),
    master_category: form.master_category.trim(),
    sub_category: form.sub_category.trim(),
    article_type: form.article_type.trim(),
    gender: form.gender.trim(),
    price: Number(form.price),
    stock_quantity: Number(form.stock_quantity || 0),
  };
  for (const key of ["base_colour", "season", "usage"]) {
    if (form[key].trim()) out[key] = form[key].trim();
  }
  if (form.year) out.year = Number(form.year);
  return out;
}

export default function AdminProducts() {
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [active, setActive] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState(BLANK);
  const [editing, setEditing] = useState(null); // { id, price, name }
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(() => {
    setLoading(true);
    setError("");
    adminListProducts({
      q: query || undefined,
      active: active === "" ? undefined : active === "true",
      limit: PAGE,
      offset,
    })
      .then((data) => {
        setRows(data.products || []);
        setTotal(data.total || 0);
      })
      .catch(() => setError("Could not load products."))
      .finally(() => setLoading(false));
  }, [query, active, offset]);

  useEffect(load, [load]);

  const create = async (e) => {
    e.preventDefault();
    setBusy(true);
    setActionError("");
    try {
      const made = await adminCreateProduct(payloadFrom(form));
      setCreating(false);
      setForm(BLANK);
      setNotice(
        `Created “${made.name}” (id ${made.id}). It is searchable by text and browsable in the ` +
          "catalog, but image search cannot return it — see below."
      );
      load();
    } catch (err) {
      setActionError(err.message || "Could not create the product.");
    } finally {
      setBusy(false);
    }
  };

  const saveEdit = async (e) => {
    e.preventDefault();
    if (!editing) return;
    setBusy(true);
    setActionError("");
    try {
      await adminUpdateProduct(editing.id, { price: Number(editing.price) });
      setEditing(null);
      load();
    } catch (err) {
      setActionError(err.message || "Could not update the product.");
    } finally {
      setBusy(false);
    }
  };

  const toggleActive = async (p) => {
    setBusy(true);
    setActionError("");
    try {
      if (p.is_active) await adminDeactivateProduct(p.id);
      else await adminUpdateProduct(p.id, { is_active: true });
      load();
    } catch (err) {
      setActionError(err.message || "Could not change the product.");
    } finally {
      setBusy(false);
    }
  };

  const pages = Math.ceil(total / PAGE) || 1;
  const page = Math.floor(offset / PAGE) + 1;

  return (
    <div className="admin-section">
      <div className="admin-section-head">
        <h2>Products</h2>
        <button type="button" className="login-submit narrow" onClick={() => setCreating((v) => !v)}>
          {creating ? "Close" : "New product"}
        </button>
      </div>

      {notice && (
        <p className="admin-notice" role="status">
          {notice}
        </p>
      )}

      {creating && (
        <form className="admin-card admin-form" onSubmit={create}>
          <h3>New product</h3>
          {/* Said up front, not after the fact: a created product has no CLIP
              vector, so image search can never return it. That is a property of
              the pipeline, not a bug to be fixed later. */}
          <p className="admin-warn">
            A product created here has no image embedding. It will be findable by text and
            category, but image search will never return it, and it can only ever be
            deactivated — never hard-deleted.
          </p>
          <div className="admin-form-grid">
            {[
              ["product_display_name", "Name", "text", true],
              ["master_category", "Category", "text", true],
              ["sub_category", "Sub-category", "text", true],
              ["article_type", "Article type", "text", true],
              ["gender", "Gender", "text", true],
              ["price", "Price", "number", true],
              ["stock_quantity", "Opening stock", "number", false],
              ["base_colour", "Colour", "text", false],
              ["season", "Season", "text", false],
              ["usage", "Usage", "text", false],
              ["year", "Year", "number", false],
            ].map(([key, label, type, required]) => (
              <label key={key} className="admin-field">
                <span>
                  {label}
                  {required && <em className="req"> *</em>}
                </span>
                <input
                  type={type}
                  value={form[key]}
                  required={required}
                  step={key === "price" ? "0.01" : type === "number" ? "1" : undefined}
                  min={type === "number" ? "0" : undefined}
                  onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
                />
              </label>
            ))}
          </div>
          <ErrorNote>{actionError}</ErrorNote>
          <div className="admin-actions">
            <button type="submit" className="login-submit" disabled={busy}>
              {busy ? "Creating…" : "Create product"}
            </button>
          </div>
        </form>
      )}

      <div className="admin-filters">
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
        <label className="admin-field">
          <span>Visibility</span>
          <select
            value={active}
            onChange={(e) => {
              setActive(e.target.value);
              setOffset(0);
            }}
          >
            <option value="">All</option>
            <option value="true">Active</option>
            <option value="false">Inactive</option>
          </select>
        </label>
      </div>

      <ErrorNote>{error || actionError}</ErrorNote>
      {loading && <Loading what="products" />}
      {!loading && !error && rows.length === 0 && <Empty>No products match.</Empty>}

      {!loading && !error && rows.length > 0 && (
        <>
          <p className="muted">{plural(total, "product")}</p>
          <table className="admin-table wide">
            <thead>
              <tr>
                <th>Product</th>
                <th>Category</th>
                <th className="num">Price</th>
                <th className="num">Stock</th>
                <th>Image search</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((p) => (
                <tr key={p.id} className={p.is_active ? "" : "inactive-row"}>
                  <td>
                    {p.name}
                    <span className="muted admin-sub">id {p.id}</span>
                    {!p.is_active && <span className="admin-flag">inactive</span>}
                  </td>
                  <td className="muted">{p.article_type}</td>
                  <td className="num">
                    {editing?.id === p.id ? (
                      <form onSubmit={saveEdit} className="inline-edit">
                        <input
                          type="number"
                          step="0.01"
                          min="0"
                          value={editing.price}
                          onChange={(e) => setEditing({ ...editing, price: e.target.value })}
                        />
                        <button type="submit" className="chip" disabled={busy}>
                          Save
                        </button>
                        <button type="button" className="chip" onClick={() => setEditing(null)}>
                          ✕
                        </button>
                      </form>
                    ) : (
                      <button
                        type="button"
                        className="linkish"
                        title="Edit price"
                        onClick={() => setEditing({ id: p.id, price: p.price, name: p.name })}
                      >
                        {money(p.price)}
                      </button>
                    )}
                  </td>
                  <td className="num">{number(p.stock_quantity)}</td>
                  <td>
                    {p.image_searchable ? (
                      <span className="muted">yes</span>
                    ) : (
                      <span className="admin-flag" title="No CLIP vector exists for this product">
                        text only
                      </span>
                    )}
                  </td>
                  <td>
                    <button
                      type="button"
                      className={`chip${p.is_active ? " danger" : ""}`}
                      disabled={busy}
                      onClick={() => toggleActive(p)}
                    >
                      {p.is_active ? "Deactivate" : "Restore"}
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
          <p className="muted admin-footnote">
            Deactivating hides a product from the storefront and from search. The row is kept:
            deleting it would shift every later product&apos;s position in the image-search index
            and stop the server booting.
          </p>
        </>
      )}
    </div>
  );
}
