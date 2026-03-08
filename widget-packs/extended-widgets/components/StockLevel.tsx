/**
 * StockLevel widget — renders a STOCK_LEVEL_ keyword value.
 *
 * Value format: "<quantity> <unit>" (e.g. "3 sides", "500g", "0.5m")
 * Falls red/amber when the value contains "low" or starts with "0".
 */

interface StockLevelProps {
  value: string;
}

export function StockLevel({ value }: StockLevelProps) {
  const isLow =
    value.startsWith('0') ||
    value.toLowerCase().includes('low') ||
    value.toLowerCase().includes('none');

  return (
    <span
      className={`inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-mono font-medium ${
        isLow
          ? 'bg-[var(--ms-danger)]/10 text-[var(--ms-danger)]'
          : 'bg-[var(--ms-success)]/10 text-[var(--ms-success)]'
      }`}
    >
      <span className="opacity-60">▣</span>
      {value || '—'}
    </span>
  );
}

export default StockLevel;
