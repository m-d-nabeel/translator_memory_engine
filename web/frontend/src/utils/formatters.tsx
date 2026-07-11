
export function isIdentityPolicy(actionStr: string, triggerStr?: string): boolean {
  if (!actionStr || !triggerStr) return false;
  try {
    const data = JSON.parse(actionStr);
    if (data.render_as && data.render_as.trim().toLowerCase() === triggerStr.trim().toLowerCase()) {
      return true;
    }
  } catch {
    // ignore
  }
  return false;
}

export function formatPolicyAction(actionStr: string, triggerStr?: string) {
  if (!actionStr) return <span className="opacity-60 italic text-xs">No action specified</span>;
  try {
    const data = JSON.parse(actionStr);
    if (data.render_as) {
      if (triggerStr && data.render_as.trim().toLowerCase() === triggerStr.trim().toLowerCase()) {
        return (
          <span className="text-xs font-medium opacity-85" style={{ color: "var(--color-text)" }}>
            Protected exact canonical name: <strong className="font-mono text-[var(--color-accent)]">{data.render_as}</strong>
          </span>
        );
      }
      return (
        <div className="flex items-center gap-2 mt-1">
          <span className="text-xs opacity-80" style={{ color: "var(--color-text)" }}>Enforce canonical spelling:</span>
          <span className="font-mono text-xs font-bold px-2 py-0.5 rounded border" style={{ backgroundColor: "var(--color-accent-glow)", color: "var(--color-accent)", borderColor: "var(--color-accent)" }}>
            {data.render_as}
          </span>
        </div>
      );
    }
    if (data.pattern || data.replacement) {
      return (
        <div className="flex flex-wrap items-center gap-1.5 mt-1 text-xs">
          <span className="opacity-80" style={{ color: "var(--color-text)" }}>Replace</span>
          <code className="px-1.5 py-0.5 rounded font-mono border" style={{ backgroundColor: "var(--color-box-bg)", borderColor: "var(--color-border)", color: "var(--color-error)" }}>
            {data.pattern || "*"}
          </code>
          <span className="opacity-60" style={{ color: "var(--color-text)" }}>→</span>
          <code className="px-1.5 py-0.5 rounded font-mono border" style={{ backgroundColor: "var(--color-box-bg)", borderColor: "var(--color-border)", color: "var(--color-success)" }}>
            {data.replacement || "*"}
          </code>
        </div>
      );
    }
    return <pre className="font-mono text-[11px] overflow-x-auto mt-1" style={{ color: "var(--color-text)" }}>{JSON.stringify(data, null, 2)}</pre>;
  } catch {
    return <span className="font-mono text-xs mt-1 block" style={{ color: "var(--color-text)" }}>{actionStr}</span>;
  }
}

export function formatAliasesList(aliasesStr: string | null | undefined, canonical?: string) {
  if (!aliasesStr) return null;
  try {
    const arr = JSON.parse(aliasesStr);
    if (!Array.isArray(arr) || arr.length === 0) return null;
    
    // Filter out aliases that are exact matches of canonical
    const filtered = canonical ? arr.filter((a: string) => a.trim().toLowerCase() !== canonical.trim().toLowerCase()) : arr;
    if (filtered.length === 0) return null;

    return (
      <div className="mt-2 pt-2 border-t" style={{ borderColor: "var(--color-border)" }}>
        <span className="text-[10px] uppercase font-bold opacity-65 block mb-1.5" style={{ color: "var(--color-text-muted)" }}>
          Detected Variants & Aliases
        </span>
        <div className="flex flex-wrap gap-1.5">
          {filtered.map((alias: string, idx: number) => (
            <span
              key={idx}
              className="text-[11px] px-2 py-0.5 rounded-md font-mono border"
              style={{
                backgroundColor: "var(--color-box-bg)",
                borderColor: "var(--color-border)",
                color: "var(--color-text)",
              }}
            >
              {alias}
            </span>
          ))}
        </div>
      </div>
    );
  } catch {
    if (aliasesStr === "[]" || aliasesStr.trim() === "") return null;
    return (
      <div className="mt-2 pt-2 border-t" style={{ borderColor: "var(--color-border)" }}>
        <span className="text-[10px] uppercase font-bold opacity-65 block mb-1" style={{ color: "var(--color-text-muted)" }}>
          Variants & Aliases
        </span>
        <span className="font-mono text-xs opacity-80 block">{aliasesStr}</span>
      </div>
    );
  }
}
