/**
 * CostBadge widget — renders a COST_ keyword value.
 *
 * Value format: "<amount> <currency>/<unit>" (e.g. "£12.50/side", "$4.99", "€0.80/metre")
 */

interface CostBadgeProps {
  value: string;
}

export function CostBadge({ value }: CostBadgeProps) {
  return (
    <span className="inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-mono font-medium bg-[var(--ms-accent-dim)] text-[var(--ms-accent)]">
      <span className="opacity-60">£</span>
      {value || '—'}
    </span>
  );
}

export default CostBadge;
