import { useEffect, useState } from "react";

const MAX_DURATION_MS = 1500; // long replies speed up so nothing takes longer than this
const MIN_CHARS_PER_FRAME = 2;

const prefersReducedMotion = () =>
  typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

/** Reveals `text` progressively, ChatGPT-style. Returns [visibleText, done, skip]. */
export default function useTypewriter(text, enabled) {
  const animate = enabled && !prefersReducedMotion();
  const [count, setCount] = useState(animate ? 0 : text.length);

  useEffect(() => {
    if (!animate) {
      setCount(text.length);
      return;
    }
    const frames = Math.max(1, Math.round(MAX_DURATION_MS / 16));
    const step = Math.max(MIN_CHARS_PER_FRAME, Math.ceil(text.length / frames));
    let raf;
    const tick = () => {
      setCount((c) => {
        const next = Math.min(text.length, c + step);
        if (next < text.length) raf = requestAnimationFrame(tick);
        return next;
      });
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [text, animate]);

  const done = count >= text.length;
  return [done ? text : text.slice(0, count), done, () => setCount(text.length)];
}
