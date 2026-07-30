import { useCallback, useEffect, useState } from "react";
import { adminGetUser, adminListUsers, adminSetUserActive, adminUsersSummary } from "@/data/admin";
import {
  Empty,
  ErrorNote,
  Loading,
  Stat,
  dateTime,
  money,
  number,
  plural,
  shortDate,
} from "@/components/admin/shared";

const PAGE = 25;

const SORTS = [
  { id: "created", label: "Newest" },
  { id: "spent", label: "Top spenders" },
  { id: "orders", label: "Most orders" },
  { id: "email", label: "Email A–Z" },
];

export default function AdminUsers({ currentUser }) {
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState("created");
  const [activeFilter, setActiveFilter] = useState("");
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [detail, setDetail] = useState(null);
  const [pending, setPending] = useState(null); // user about to be disabled
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState("");

  const load = useCallback(() => {
    setLoading(true);
    setError("");
    Promise.all([
      adminListUsers({
        q: query || undefined,
        sort,
        active: activeFilter === "" ? undefined : activeFilter === "true",
        limit: PAGE,
        offset,
      }),
      adminUsersSummary(),
    ])
      .then(([list, sum]) => {
        setRows(list.users || []);
        setTotal(list.total || 0);
        setSummary(sum);
      })
      .catch(() => setError("Could not load users."))
      .finally(() => setLoading(false));
  }, [query, sort, activeFilter, offset]);

  useEffect(load, [load]);

  const openDetail = async (id) => {
    setDetail({ loading: true });
    try {
      setDetail(await adminGetUser(id));
    } catch {
      setDetail({ failed: true });
    }
  };

  const enable = async (user) => {
    setBusy(true);
    setActionError("");
    try {
      await adminSetUserActive(user.id, true);
      load();
    } catch (err) {
      setActionError(err.message || "Could not re-enable the account.");
    } finally {
      setBusy(false);
    }
  };

  const confirmDisable = async () => {
    if (!pending) return;
    setBusy(true);
    setActionError("");
    try {
      await adminSetUserActive(pending.id, false, reason.trim());
      setPending(null);
      setReason("");
      load();
    } catch (err) {
      // The server refuses self-disable and last-active-admin with a 409 that
      // explains which; show it rather than a generic failure.
      setActionError(err.message || "Could not disable the account.");
    } finally {
      setBusy(false);
    }
  };

  const pages = Math.ceil(total / PAGE) || 1;
  const page = Math.floor(offset / PAGE) + 1;

  return (
    <div className="admin-section">
      <div className="admin-section-head">
        <h2>Users</h2>
      </div>

      {summary && (
        <div className="admin-stats">
          <Stat label="Accounts" value={number(summary.total_users)} />
          <Stat label="Admins" value={number(summary.admins)} />
          <Stat label="Disabled" value={number(summary.disabled)} />
          <Stat label="Have ordered" value={number(summary.with_orders)} />
        </div>
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
            placeholder="Search name or email…"
            onChange={(e) => setQ(e.target.value)}
          />
          <button type="submit" className="chip">
            Search
          </button>
        </form>
        <label className="admin-field">
          <span>Sort</span>
          <select
            value={sort}
            onChange={(e) => {
              setSort(e.target.value);
              setOffset(0);
            }}
          >
            {SORTS.map((s) => (
              <option key={s.id} value={s.id}>
                {s.label}
              </option>
            ))}
          </select>
        </label>
        <label className="admin-field">
          <span>Status</span>
          <select
            value={activeFilter}
            onChange={(e) => {
              setActiveFilter(e.target.value);
              setOffset(0);
            }}
          >
            <option value="">All</option>
            <option value="true">Active</option>
            <option value="false">Disabled</option>
          </select>
        </label>
      </div>

      <ErrorNote>{error || actionError}</ErrorNote>
      {loading && <Loading what="users" />}
      {!loading && !error && rows.length === 0 && <Empty>No accounts match.</Empty>}

      {!loading && !error && rows.length > 0 && (
        <>
          <p className="muted">{plural(total, "account")}</p>
          <table className="admin-table wide">
            <thead>
              <tr>
                <th>Account</th>
                <th>Joined</th>
                <th className="num">Orders</th>
                <th className="num">Spent</th>
                <th>Last order</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((u) => (
                <tr key={u.id} className={u.is_active ? "" : "inactive-row"}>
                  <td>
                    {u.name}
                    <span className="muted admin-sub">{u.email}</span>
                    {u.is_admin && <span className="admin-flag admin">admin</span>}
                    {!u.is_active && (
                      <span className="admin-flag" title={u.deactivation_reason ?? undefined}>
                        disabled
                      </span>
                    )}
                  </td>
                  <td className="muted">{shortDate(u.created_at)}</td>
                  <td className="num">{number(u.order_count)}</td>
                  <td className="num">{money(u.total_spent)}</td>
                  <td className="muted">{shortDate(u.last_order_at)}</td>
                  <td>
                    <div className="admin-actions">
                      <button type="button" className="chip" onClick={() => openDetail(u.id)}>
                        View
                      </button>
                      {u.is_active ? (
                        <button
                          type="button"
                          className="chip danger"
                          disabled={busy || u.id === currentUser?.id}
                          title={
                            u.id === currentUser?.id
                              ? "You cannot disable your own account"
                              : undefined
                          }
                          onClick={() => {
                            setPending(u);
                            setReason("");
                            setActionError("");
                          }}
                        >
                          Disable
                        </button>
                      ) : (
                        <button
                          type="button"
                          className="chip"
                          disabled={busy}
                          onClick={() => enable(u)}
                        >
                          Enable
                        </button>
                      )}
                    </div>
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
            Admin rights are granted from the server console only
            (<code>promote_admin.py</code>), never from this panel — a route that hands out
            privileges is the one thing that must not be reachable over the network.
          </p>
        </>
      )}

      {pending && (
        <div className="admin-confirm" role="dialog" aria-label="Confirm disable">
          <h4>Disable {pending.email}?</h4>
          <p className="muted">
            They are signed out on their next request and cannot log in again. Their orders and
            history are kept, and you can re-enable the account at any time.
          </p>
          <label className="admin-field">
            <span>Reason (optional, stored on the account)</span>
            <input
              type="text"
              value={reason}
              maxLength={255}
              placeholder="e.g. Fraudulent activity"
              onChange={(e) => setReason(e.target.value)}
            />
          </label>
          <ErrorNote>{actionError}</ErrorNote>
          <div className="admin-actions">
            <button type="button" className="login-submit" disabled={busy} onClick={confirmDisable}>
              {busy ? "Working…" : "Disable account"}
            </button>
            <button type="button" className="chip" disabled={busy} onClick={() => setPending(null)}>
              Cancel
            </button>
          </div>
        </div>
      )}

      {detail && (
        <div className="admin-confirm wide" role="dialog" aria-label="Account detail">
          {detail.loading && <Loading what="account" />}
          {detail.failed && <p className="admin-error">Could not load this account.</p>}
          {!detail.loading && !detail.failed && (
            <>
              <h4>
                {detail.name}
                <span className="muted admin-sub">{detail.email}</span>
              </h4>
              {!detail.is_active && (
                <p className="admin-warn">
                  Disabled {dateTime(detail.deactivated_at)}
                  {detail.deactivation_reason ? ` — ${detail.deactivation_reason}` : ""}
                </p>
              )}
              <div className="admin-stats secondary">
                <Stat label="Orders" value={number(detail.order_count)} />
                <Stat label="Spent" value={money(detail.total_spent)} />
                <Stat label="Cart" value={number(detail.saved.cart_items)} />
                <Stat label="Wishlist" value={number(detail.saved.wishlist_items)} />
              </div>

              {detail.recent_orders.length > 0 && (
                <>
                  <h5>Recent orders</h5>
                  <table className="admin-table">
                    <thead>
                      <tr>
                        <th>Order</th>
                        <th>Status</th>
                        <th className="num">Total</th>
                        <th>Placed</th>
                      </tr>
                    </thead>
                    <tbody>
                      {detail.recent_orders.map((o) => (
                        <tr key={o.id}>
                          <td className="mono">{o.order_number}</td>
                          <td>
                            <span className={`order-status ${o.status}`}>{o.status}</span>
                          </td>
                          <td className="num">{money(o.total)}</td>
                          <td className="muted">{shortDate(o.created_at)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </>
              )}

              <div className="admin-actions">
                <button type="button" className="chip" onClick={() => setDetail(null)}>
                  Close
                </button>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
