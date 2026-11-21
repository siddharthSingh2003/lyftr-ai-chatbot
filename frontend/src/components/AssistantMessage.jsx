import { useEffect } from "react";
import useTypewriter from "../useTypewriter.js";
import Markdown from "./Markdown.jsx";
import MetadataBar from "./MetadataBar.jsx";

export default function AssistantMessage({ message, animate, onProgress }) {
  const [visible, done, skip] = useTypewriter(message.content, animate);

  // Keep the list scrolled to the bottom while text is being revealed.
  useEffect(() => {
    onProgress?.();
  }, [visible, onProgress]);

  return (
    <div
      className={`bubble assistant ${done ? "" : "typing-active"}`}
      data-testid="assistant-message"
      onClick={done ? undefined : skip}
      title={done ? undefined : "Click to show the full reply"}
    >
      <Markdown>{visible}</Markdown>
      <MetadataBar meta={message.metadata} />
    </div>
  );
}
