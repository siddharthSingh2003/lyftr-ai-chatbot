import { useCallback, useEffect, useRef } from "react";
import AssistantMessage from "./AssistantMessage.jsx";

export default function MessageList({ messages, pending, loading }) {
  const listRef = useRef(null);
  const stickToBottom = useRef(true);

  const scrollToBottom = useCallback(() => {
    const el = listRef.current;
    if (el && stickToBottom.current) el.scrollTop = el.scrollHeight;
  }, []);

  // Only auto-scroll while the user is near the bottom, so reading earlier
  // messages isn't interrupted by a reply being typed out.
  const onScroll = () => {
    const el = listRef.current;
    stickToBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
  };

  useEffect(() => {
    stickToBottom.current = true;
    scrollToBottom();
  }, [messages, pending, scrollToBottom]);

  const lastId = messages.length ? messages[messages.length - 1].id : null;

  return (
    <main className="messages" ref={listRef} onScroll={onScroll} aria-live="polite">
      {loading && <p className="empty">Loading chat…</p>}
      {!loading && messages.length === 0 && (
        <p className="empty">Send a message to start. Each reply shows its cache source, model, latency and tokens.</p>
      )}

      {messages.map((m) => {
        if (m.role === "assistant") {
          return (
            <AssistantMessage
              key={m.id}
              message={m}
              animate={m.id === lastId && m.animate}
              onProgress={scrollToBottom}
            />
          );
        }
        if (m.role === "error") {
          return (
            <div key={m.id} className="bubble error" role="alert">
              <strong>Request failed.</strong> {m.content}
            </div>
          );
        }
        return (
          <div key={m.id} className="bubble user">
            <div className="text">{m.content}</div>
          </div>
        );
      })}

      {pending && (
        <div className="bubble assistant thinking" aria-label="Assistant is thinking">
          <span className="dot" />
          <span className="dot" />
          <span className="dot" />
        </div>
      )}
    </main>
  );
}
