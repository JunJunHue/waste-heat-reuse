export const fmtInt = (n: number | null | undefined) => (n == null ? "—" : Math.round(n).toLocaleString("en-US"));
export const fmtUsd = (n: number | null | undefined, digits = 1) => {
  if (n == null) return "—";
  const a = Math.abs(n), s = n < 0 ? "−" : "";
  if (a >= 1e6) return `${s}$${(a / 1e6).toFixed(digits)}M`;
  if (a >= 1e3) return `${s}$${(a / 1e3).toFixed(0)}k`;
  return `${s}$${a.toFixed(0)}`;
};
export const fmtPct = (x: number | null | undefined, digits = 0) => (x == null ? "—" : `${(x * 100).toFixed(digits)}%`);
export const fmtNum = (n: number | null | undefined, digits = 1) => (n == null ? "—" : n.toFixed(digits));
export const esc = (s: string | null | undefined) =>
  (s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);
/** LL84 property names are often ALL CAPS ("FULTON"); show them in title case. */
export const nice = (s: string | null | undefined) =>
  !s ? "" : s === s.toUpperCase() ? s.toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase()) : s;
