import { ArrowUp, Mic } from "lucide-react";
import { useState } from "react";
import { useChatStore } from "@/stores/chatStore";

type InputBarProps = {
  disabled?: boolean;
  onSend: (text: string) => void;
};

export function InputBar({ disabled = false, onSend }: InputBarProps) {
  const [value, setValue] = useState("");
  const addMessage = useChatStore((state) => state.addMessage);

  function submit() {
    const text = value.trim();
    if (!text || disabled) return;
    addMessage({ id: crypto.randomUUID(), role: "user", text });
    onSend(text);
    setValue("");
  }

  return (
    <footer
      className="shrink-0 flex justify-center px-4 pb-5 pt-8"
      style={{ background: "linear-gradient(to top, var(--color-kibo-bg) 60%, transparent)" }}
    >
      <form
        className="flex w-full items-center gap-3 rounded-full border border-kibo-border bg-white py-2 pl-6 pr-2 shadow-[0_8px_32px_oklch(0%_0_0_/_0.06),_0_2px_8px_oklch(0%_0_0_/_0.03)] transition-all duration-300 focus-within:-translate-y-0.5 focus-within:border-kibo-accent-soft focus-within:shadow-[0_12px_48px_oklch(0%_0_0_/_0.08),_0_0_0_4px_var(--color-kibo-accent-dim)]"
        onSubmit={(e) => { e.preventDefault(); submit(); }}
      >
        <input
          className="min-w-0 flex-1 bg-transparent text-[1.05rem] text-kibo-text outline-none placeholder:text-kibo-dim/70"
          value={value}
          disabled={disabled}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !disabled) submit(); }}
          placeholder={disabled ? "KIBO is connecting…" : "Ask anything…"}
          autoFocus
        />
        <button
          className="grid h-11 w-11 shrink-0 place-items-center rounded-full text-kibo-dim transition-all hover:bg-kibo-bg hover:text-kibo-text"
          type="button"
          aria-label="Voice input"
        >
          <Mic size={20} />
        </button>
        <button
          className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-kibo-accent text-white shadow-[0_4px_12px_var(--color-kibo-accent-glow)] transition-all hover:scale-105 hover:brightness-105 active:scale-95 disabled:cursor-not-allowed disabled:border disabled:border-kibo-border disabled:bg-kibo-surface disabled:text-kibo-dim disabled:shadow-none"
          type="submit"
          aria-label="Send"
          disabled={disabled || !value.trim()}
        >
          <ArrowUp size={20} />
        </button>
      </form>
    </footer>
  );
}
