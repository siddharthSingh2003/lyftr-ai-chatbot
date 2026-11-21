export default function MetadataBar({ meta }) {
  if (!meta) return null;
  const cached = meta.resolution_source === "LLM_CACHE";
  return (
    <div className="meta">
      <span className={`pill ${cached ? "cache" : "live"}`} data-testid="meta-source">
        {meta.resolution_source}
      </span>
      <span className="item">
        <span className="label">model</span> <span data-testid="meta-model">{meta.model}</span>
      </span>
      <span className="item">
        <span className="label">latency</span> <span data-testid="meta-latency">{meta.latency_ms} ms</span>
      </span>
      <span className="item">
        <span className="label">in</span> <span data-testid="meta-input-tokens">{meta.input_tokens}</span>
      </span>
      <span className="item">
        <span className="label">out</span> <span data-testid="meta-output-tokens">{meta.output_tokens}</span>
      </span>
      <span className="item">
        <span className="label">key</span> {meta.key_id ?? "—"}
        {meta.fallback_attempts > 0 && <span className="fallback"> (after {meta.fallback_attempts} failed)</span>}
      </span>
    </div>
  );
}
