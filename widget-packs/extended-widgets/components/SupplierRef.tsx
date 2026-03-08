/**
 * SupplierRef widget — renders a SUPPLIER_REF_ keyword value.
 *
 * Value format: "<supplier name>" or "<supplier name>|<url>"
 * If a URL is present, renders as a clickable link.
 */

interface SupplierRefProps {
  value: string;
}

export function SupplierRef({ value }: SupplierRefProps) {
  const [name, url] = value.split('|').map((s) => s.trim());

  const inner = (
    <span className="inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-medium bg-[var(--ms-surface-el)] text-[var(--ms-text-muted)] border border-[var(--ms-border)]">
      <span className="opacity-60">⬡</span>
      {name || value}
    </span>
  );

  if (url) {
    return (
      <a href={url} target="_blank" rel="noreferrer" className="no-underline hover:opacity-80">
        {inner}
      </a>
    );
  }

  return inner;
}

export default SupplierRef;
