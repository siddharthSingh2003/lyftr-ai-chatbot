import { groupSessions } from "../sessionStore.js";

export default function Sidebar({ sessions, activeId, onSelect, onNew, onDelete, disabled, open, onClose }) {
  const groups = groupSessions(sessions);

  return (
    <>
      <div className={`sidebar-backdrop ${open ? "show" : ""}`} onClick={onClose} aria-hidden="true" />
      <aside className={`sidebar ${open ? "open" : ""}`} aria-label="Chat history">
        <button className="new-chat" onClick={onNew} disabled={disabled}>
          <span aria-hidden="true">＋</span> New chat
        </button>

        <nav className="history">
          {groups.length === 0 && <p className="history-empty">Your chats will appear here.</p>}
          {groups.map((g) => (
            <section key={g.label}>
              <h2 className="history-label">{g.label}</h2>
              <ul>
                {g.items.map((s) => (
                  <li key={s.id} className={`history-item ${s.id === activeId ? "active" : ""}`}>
                    <button
                      className="history-open"
                      onClick={() => onSelect(s.id)}
                      disabled={disabled}
                      title={s.title}
                      aria-current={s.id === activeId ? "true" : undefined}
                    >
                      {s.title || "Untitled chat"}
                    </button>
                    <button
                      className="history-delete"
                      onClick={() => onDelete(s.id)}
                      disabled={disabled}
                      aria-label={`Remove "${s.title}" from the list`}
                      title="Remove from list"
                    >
                      ×
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </nav>
      </aside>
    </>
  );
}
