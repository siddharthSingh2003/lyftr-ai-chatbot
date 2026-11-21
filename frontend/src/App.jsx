import { useCallback, useRef, useState } from "react";
import { fetchHistory, sendChat } from "./api.js";
import { loadSessions, removeSession, upsertSession } from "./sessionStore.js";
import MessageList from "./components/MessageList.jsx";
import MessageInput from "./components/MessageInput.jsx";
import Sidebar from "./components/Sidebar.jsx";

const newSessionId = () => `s-${crypto.randomUUID().slice(0, 8)}`;

const SIMULATIONS = [
  { value: "", label: "No simulated failure" },
  { value: "key_1=429", label: "key_1 → 429" },
  { value: "key_1=500", label: "key_1 → 500" },
  { value: "key_1=429,key_2=500", label: "key_1 → 429, key_2 → 500" },
  { value: "*=429", label: "all keys → 429" },
];

export default function App() {
  // A new session on every page load; earlier chats are listed in the sidebar.
  const [sessionId, setSessionId] = useState(newSessionId);
  const [sessions, setSessions] = useState(loadSessions);
  const [messages, setMessages] = useState([]);
  const [systemPrompt, setSystemPrompt] = useState("");
  const [simulate, setSimulate] = useState("");
  const [pending, setPending] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const nextId = useRef(0);
  const loadToken = useRef(0); // ignores a slow history load after the user switched again

  const busy = pending || loadingHistory;
  const withIds = (list) => list.map((m) => ({ id: nextId.current++, ...m }));
  const push = (msg) => setMessages((prev) => [...prev, ...withIds([msg])]);

  const handleSend = useCallback(
    async (text) => {
      if (busy) return;
      push({ role: "user", content: text });
      setPending(true);
      try {
        const data = await sendChat({ sessionId, message: text, systemPrompt, simulateFailure: simulate });
        push({ role: "assistant", content: data.reply, metadata: data.metadata, animate: true });
        // The backend only stores successful turns, so only now is the chat worth listing.
        setSessions((list) => upsertSession(list, sessionId, text));
      } catch (err) {
        push({ role: "error", content: err.message || "Something went wrong." });
      } finally {
        setPending(false);
      }
    },
    [busy, sessionId, systemPrompt, simulate]
  );

  const startNewChat = () => {
    loadToken.current++;
    setSessionId(newSessionId());
    setMessages([]);
    setSystemPrompt("");
    setSidebarOpen(false);
  };

  const openChat = async (id) => {
    setSidebarOpen(false);
    if (id === sessionId) return;
    const token = ++loadToken.current;
    setSessionId(id);
    setMessages([]);
    setSystemPrompt(""); // empty = the backend keeps using this session's saved prompt
    setLoadingHistory(true);
    try {
      const history = await fetchHistory(id);
      if (token !== loadToken.current) return;
      setMessages(withIds(history.map((m) => ({ role: m.role, content: m.content, metadata: m.metadata }))));
    } catch (err) {
      if (token !== loadToken.current) return;
      if (err.status === 404) {
        // e.g. the backend database was reset: drop the stale entry.
        setSessions((list) => removeSession(list, id));
        setMessages(withIds([{ role: "error", content: "This chat no longer exists on the server, so it was removed from the list." }]));
      } else {
        setMessages(withIds([{ role: "error", content: err.message }]));
      }
    } finally {
      if (token === loadToken.current) setLoadingHistory(false);
    }
  };

  const deleteChat = (id) => {
    setSessions((list) => removeSession(list, id));
    if (id === sessionId) startNewChat();
  };

  const activeTitle = sessions.find((s) => s.id === sessionId)?.title || "New chat";

  return (
    <div className="layout">
      <Sidebar
        sessions={sessions}
        activeId={sessionId}
        onSelect={openChat}
        onNew={startNewChat}
        onDelete={deleteChat}
        disabled={busy}
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
      />

      <div className="app">
        <header className="header">
          <button className="menu" onClick={() => setSidebarOpen(true)} aria-label="Open chat history">
            ☰
          </button>
          <div className="header-title">
            <h1>{activeTitle}</h1>
            <p className="session">
              Session <code>{sessionId}</code>
            </p>
          </div>
        </header>

        <details className="settings">
          <summary>Session settings</summary>
          <label>
            System prompt (optional)
            <textarea
              data-testid="system-prompt-input"
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
              placeholder="You are a helpful assistant."
              rows={2}
            />
          </label>
          <label>
            Failover demo (X-Simulate-Failure)
            <select value={simulate} onChange={(e) => setSimulate(e.target.value)}>
              {SIMULATIONS.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
          </label>
        </details>

        <MessageList messages={messages} pending={pending} loading={loadingHistory} />
        <MessageInput onSend={handleSend} disabled={busy} />
      </div>
    </div>
  );
}
