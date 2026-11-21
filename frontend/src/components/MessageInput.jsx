import { useState } from "react";

const MAX_CHARS = 4000;

export default function MessageInput({ onSend, disabled }) {
  const [text, setText] = useState("");
  const trimmed = text.trim();
  const tooLong = trimmed.length > MAX_CHARS;
  const canSend = !disabled && trimmed.length > 0 && !tooLong;

  const submit = () => {
    if (!canSend) return;
    onSend(trimmed);
    setText("");
  };

  const onKeyDown = (e) => {
    // Enter sends, Shift+Enter inserts a newline.
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <form
      className="composer"
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <textarea
        data-testid="chat-input"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={onKeyDown}
        placeholder="Type a message… (Enter to send, Shift+Enter for a newline)"
        rows={2}
        aria-label="Message"
      />
      <div className="composer-side">
        <span className={`count ${tooLong ? "over" : ""}`}>
          {trimmed.length}/{MAX_CHARS}
        </span>
        <button type="submit" data-testid="send-button" disabled={!canSend}>
          {disabled ? "Sending…" : "Send"}
        </button>
      </div>
    </form>
  );
}
