import { Bot } from "lucide-react";
import type { ChatMessage } from "@/stores/chatStore";
import { MarkdownContent } from "./MarkdownContent";

type MessageBubbleProps = {
  message: ChatMessage;
  isFirstInGroup?: boolean;
};

export function MessageBubble({ message, isFirstInGroup = false }: MessageBubbleProps) {
  const isUser = message.role === "user";

  if (isUser) {
    return (
      <div className="animate-slide-up flex flex-col items-end gap-2">
        <div className="max-w-[85%] rounded-[24px] rounded-br-[6px] border border-kibo-border bg-kibo-surface px-6 py-4 text-base leading-relaxed text-kibo-text shadow-[0_2px_8px_oklch(0%_0_0_/_0.02)]">
          {message.text}
        </div>
      </div>
    );
  }

  return (
    <div className="animate-slide-up flex flex-col items-start gap-2">
      {isFirstInGroup && (
        <div className="flex items-center gap-2 px-2 text-sm text-kibo-dim">
          <Bot size={16} />
          <span>KIBO</span>
        </div>
      )}
      <div className="max-w-[85%] rounded-[24px] rounded-bl-[6px] border border-kibo-accent-soft bg-kibo-accent-dim px-6 py-4 text-base text-kibo-text shadow-[0_2px_8px_oklch(0%_0_0_/_0.02)]">
        <MarkdownContent text={message.text} />
      </div>
    </div>
  );
}
