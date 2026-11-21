// Vite inlines VITE_* at build time; fall back to the local backend for dev.
const BASE = (import.meta.env.VITE_API_BASE_URL || "http://localhost:8000").replace(/\/+$/, "");

// FastAPI's 422 detail is an array of objects; the 503/404 detail is a string.
export function formatDetail(detail) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) => {
        const field = Array.isArray(d?.loc) ? d.loc.filter((p) => p !== "body").join(".") : "";
        const msg = d?.msg || JSON.stringify(d);
        return field ? `${field}: ${msg}` : msg;
      })
      .join("; ");
  }
  if (detail == null) return "unexpected error";
  return JSON.stringify(detail);
}

export async function fetchHistory(sessionId) {
  let res;
  try {
    res = await fetch(`${BASE}/sessions/${encodeURIComponent(sessionId)}/messages`);
  } catch {
    throw new Error("Cannot reach the backend. Check that it is running and allows this origin.");
  }
  const data = await res.json().catch(() => ({ detail: `unexpected response (HTTP ${res.status})` }));
  if (!res.ok) {
    const err = new Error(`${res.status}: ${formatDetail(data.detail)}`);
    err.status = res.status;
    throw err;
  }
  return data.messages || [];
}

export async function sendChat({ sessionId, message, systemPrompt, simulateFailure }) {
  const headers = { "Content-Type": "application/json" };
  if (simulateFailure) headers["X-Simulate-Failure"] = simulateFailure;
  const body = { session_id: sessionId, message };
  if (systemPrompt && systemPrompt.trim()) body.system_prompt = systemPrompt;

  let res;
  try {
    res = await fetch(`${BASE}/chat`, { method: "POST", headers, body: JSON.stringify(body) });
  } catch {
    throw new Error("Cannot reach the backend. Check that it is running and allows this origin.");
  }
  const data = await res.json().catch(() => ({ detail: `unexpected response (HTTP ${res.status})` }));
  if (!res.ok) throw new Error(`${res.status}: ${formatDetail(data.detail)}`);
  return data;
}
