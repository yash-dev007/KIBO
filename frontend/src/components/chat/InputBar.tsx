import { Mic } from "lucide-react";
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
    if (!text) return;
    addMessage({ id: crypto.randomUUID(), role: "user", text });
    onSend(text);
    setValue("");
  }

  return (
    <footer className="border-t border-white/5 p-3">
      <div className="flex items-center gap-2 rounded border border-white/8 bg-black/40 px-3 py-2.5 transition-colors focus-within:border-kibo-accent/40 focus-within:bg-black/60">
        <span className="select-none font-mono text-sm text-kibo-accent/70">›</span>
        <input
          className="min-w-0 flex-1 bg-transparent font-mono text-sm text-kibo-text outline-none placeholder:text-kibo-dim"
          value={value}
          disabled={disabled}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") submit(); }}
          placeholder={disabled ? "connecting..." : "ask anything"}
          autoFocus
        />
        <button
          className="grid h-6 w-6 place-items-center text-kibo-dim transition-colors hover:text-kibo-accent"
          type="button"
          aria-label="Voice input"
        >
          <Mic size={14} />
        </button>
      </div>
      <p className="mt-1.5 text-center font-mono text-[10px] text-kibo-dim/50 tracking-wider">
        ENTER to send
      </p>
    </footer>
  );
}
