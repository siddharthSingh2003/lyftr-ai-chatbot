// The chat list (ids, titles, timestamps) lives in this browser only. The
// messages themselves stay in the backend's SQLite and are loaded through
// GET /sessions/{id}/messages, so the API contract is unchanged.
const STORAGE_KEY = "lyftr-chat-sessions";
const MAX_SESSIONS = 100;
const TITLE_CHARS = 60;

export function loadSessions() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    const list = raw ? JSON.parse(raw) : [];
    return Array.isArray(list) ? list.filter((s) => s && typeof s.id === "string") : [];
  } catch {
    return []; // private mode, blocked storage or corrupt data: start empty
  }
}

function save(list) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(list.slice(0, MAX_SESSIONS)));
  } catch {
    /* storage unavailable: the sidebar just won't persist */
  }
}

export function makeTitle(text) {
  const oneLine = text.replace(/\s+/g, " ").trim();
  return oneLine.length > TITLE_CHARS ? `${oneLine.slice(0, TITLE_CHARS - 1)}…` : oneLine;
}

/** Add or refresh a session and move it to the top. Returns the new list. */
export function upsertSession(list, id, firstMessage) {
  const existing = list.find((s) => s.id === id);
  const entry = existing
    ? { ...existing, updatedAt: Date.now() }
    : { id, title: makeTitle(firstMessage), createdAt: Date.now(), updatedAt: Date.now() };
  const next = [entry, ...list.filter((s) => s.id !== id)];
  save(next);
  return next;
}

export function removeSession(list, id) {
  const next = list.filter((s) => s.id !== id);
  save(next);
  return next;
}

/** Group for display: Today / Yesterday / Previous 7 days / Older. */
export function groupSessions(list) {
  const startOfToday = new Date().setHours(0, 0, 0, 0);
  const day = 86400000;
  const groups = [
    { label: "Today", from: startOfToday, items: [] },
    { label: "Yesterday", from: startOfToday - day, items: [] },
    { label: "Previous 7 days", from: startOfToday - 7 * day, items: [] },
    { label: "Older", from: -Infinity, items: [] },
  ];
  for (const s of [...list].sort((a, b) => b.updatedAt - a.updatedAt)) {
    groups.find((g) => (s.updatedAt || 0) >= g.from).items.push(s);
  }
  return groups.filter((g) => g.items.length);
}
