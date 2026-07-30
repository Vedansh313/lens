import { useEffect, useState } from "react";
import {
  analyticsCustomers,
  analyticsFulfilment,
  analyticsOrders,
  analyticsOverview,
  analyticsProducts,
  analyticsRevenue,
} from "@/data/admin";
import {
  BarChart,
  Empty,
  ErrorNote,
  Loading,
  RANGES,
  RangePicker,
  Stat,
  hours,
  lastDays,
  money,
  number,
  orDash,
} from "@/components/admin/shared";

// Bucket by day for short ranges and by month for a year, so a 12-month view
// renders 12 bars instead of 365 unreadable slivers.
const bucketFor = (days) => (days <= 31 ? "day" : days <= 120 ? "week" : "month");

export default function AdminOverview() {
  const [range, setRange] = useState("30");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const days = RANGES.find((r) => r.id === range)?.days ?? 30;
    const window = lastDays(days);
    let cancelled = false;

    setLoading(true);
    setError("");
    // One await for six endpoints: they are independent reads, so issuing them
    // in series would make the dashboard six round-trips slow for no reason.
    Promise.all([
      analyticsOverview(window),
      analyticsRevenue(window, bucketFor(days)),
      analyticsOrders(window),
      analyticsProducts(window, "revenue", 8),
      analyticsFulfilment(window),
      analyticsCustomers(window),
    ])
      .then(([overview, revenue, orders, products, fulfilment, customers]) => {
        if (cancelled) return;
        setData({ overview, revenue, orders, products, fulfilment, customers });
      })
      .catch(() => {
        if (!cancelled) setError("Could not load analytics. Is the backend running?");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    // Guards against a slow response for an abandoned range overwriting the
    // one the admin actually asked for.
    return () => {
      cancelled = true;
    };
  }, [range]);

  return (
    <div className="admin-section">
      <div className="admin-section-head">
        <h2>Overview</h2>
        <RangePicker value={range} onChange={setRange} />
      </div>

      <ErrorNote>{error}</ErrorNote>
      {loading && <Loading what="analytics" />}

      {!loading && !error && data && (
        <>
          <div className="admin-stats">
            <Stat
              label="Revenue"
              value={money(data.overview.current.revenue)}
              delta={data.overview.change_pct.revenue}
            />
            <Stat
              label="Paid orders"
              value={number(data.overview.current.paid_orders)}
              delta={data.overview.change_pct.paid_orders}
              hint={`${number(data.overview.current.orders)} placed in total`}
            />
            <Stat
              label="Average order"
              value={money(data.overview.current.average_order_value)}
              delta={data.overview.change_pct.average_order_value}
              hint="over paid orders only"
            />
            <Stat
              label="Customers"
              value={number(data.overview.current.customers)}
              delta={data.overview.change_pct.customers}
              hint={`${number(data.customers.new_customers)} new, ${number(
                data.customers.returning_customers
              )} returning`}
            />
          </div>

          <div className="admin-stats secondary">
            <Stat label="Conversion to paid" value={`${data.overview.rates.conversion_to_paid_pct}%`} />
            <Stat label="Cancellation rate" value={`${data.overview.rates.cancellation_pct}%`} />
            <Stat label="Return rate" value={`${data.overview.rates.return_pct}%`} />
            <Stat
              label="Awaiting shipment"
              value={number(data.fulfilment.awaiting_shipment)}
              hint="paid, not yet shipped"
            />
          </div>

          <div className="admin-card">
            <h3>Revenue over time</h3>
            <p className="muted">
              By {data.revenue.bucket}. Attributed to when each order was placed, so past
              buckets never change.
            </p>
            <BarChart points={data.revenue.points} valueKey="revenue" />
          </div>

          <div className="admin-two-col">
            <div className="admin-card">
              <h3>Order status</h3>
              <ul className="admin-bars-list">
                {Object.entries(data.orders.by_status).map(([status, count]) => {
                  const total = data.orders.total || 1;
                  return (
                    <li key={status}>
                      <span className={`order-status ${status}`}>{status}</span>
                      <span className="admin-bar-track" aria-hidden="true">
                        <span
                          className="admin-bar-fill"
                          style={{ width: `${(count / total) * 100}%` }}
                        />
                      </span>
                      <span className="admin-bars-count">{number(count)}</span>
                    </li>
                  );
                })}
              </ul>
            </div>

            <div className="admin-card">
              <h3>Fulfilment</h3>
              <dl className="admin-dl">
                <dt>Avg. time to ship</dt>
                <dd>{hours(data.fulfilment.avg_hours_to_ship)}</dd>
                <dt>Avg. ship → deliver</dt>
                <dd>{hours(data.fulfilment.avg_hours_ship_to_deliver)}</dd>
                <dt>Avg. end to end</dt>
                <dd>{hours(data.fulfilment.avg_hours_end_to_end)}</dd>
                <dt>Shipped / delivered</dt>
                <dd>
                  {number(data.fulfilment.shipped_orders)} / {number(data.fulfilment.delivered_orders)}
                </dd>
              </dl>
              <p className="muted">
                A dash means nothing reached that milestone in this range — not that it took
                no time.
              </p>
            </div>
          </div>

          <div className="admin-two-col">
            <div className="admin-card">
              <h3>Top products</h3>
              {data.products.products.length === 0 ? (
                <Empty>Nothing sold in this range.</Empty>
              ) : (
                <table className="admin-table">
                  <thead>
                    <tr>
                      <th>Product</th>
                      <th className="num">Units</th>
                      <th className="num">Revenue</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.products.products.map((p, i) => (
                      <tr key={p.product_id ?? `gone-${i}`}>
                        <td>
                          {p.name}
                          {!p.product_exists && (
                            <span className="admin-flag" title="This product row no longer exists">
                              deleted
                            </span>
                          )}
                        </td>
                        <td className="num">{number(p.units)}</td>
                        <td className="num">{money(p.revenue)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            <div className="admin-card">
              <h3>Payments</h3>
              {data.orders.payments.length === 0 ? (
                <Empty>No payment attempts in this range.</Empty>
              ) : (
                <table className="admin-table">
                  <thead>
                    <tr>
                      <th>Method</th>
                      <th className="num">Attempts</th>
                      <th className="num">Success</th>
                      <th className="num">Collected</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.orders.payments.map((p) => (
                      <tr key={p.method}>
                        <td>{p.method}</td>
                        <td className="num">{number(p.attempts)}</td>
                        <td className="num">{p.success_rate_pct}%</td>
                        <td className="num">{money(p.collected)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>

          <div className="admin-card">
            <h3>Top customers</h3>
            {data.customers.top_customers.length === 0 ? (
              <Empty>No customers ordered in this range.</Empty>
            ) : (
              <table className="admin-table">
                <thead>
                  <tr>
                    <th>Customer</th>
                    <th className="num">Orders</th>
                    <th className="num">Spent</th>
                  </tr>
                </thead>
                <tbody>
                  {data.customers.top_customers.map((c) => (
                    <tr key={c.user_id}>
                      <td>
                        {c.name}
                        <span className="muted admin-sub">{c.email}</span>
                      </td>
                      <td className="num">{number(c.orders)}</td>
                      <td className="num">{money(c.spent)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          <p className="muted admin-footnote">
            {data.overview.window.start} → {data.overview.window.end} ({data.overview.window.days}{" "}
            days). Revenue counts paid, shipped and delivered orders;{" "}
            {orDash(data.overview.current.cancelled, number)} cancelled and{" "}
            {orDash(data.overview.current.returned, number)} returned orders are excluded.
          </p>
        </>
      )}
    </div>
  );
}
