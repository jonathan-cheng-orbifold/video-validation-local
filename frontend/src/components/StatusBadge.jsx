export default function StatusBadge({ status }) {
  const s = (status || "").toLowerCase();
  let cls = "badge";
  if (s === "good") cls += " good";
  else if (s === "bad") cls += " bad";
  else cls += " processing";

  const label = s === "good" ? "GOOD" : s === "bad" ? "BAD" : "PROCESSING";
  return <span className={cls}>{label}</span>;
}
