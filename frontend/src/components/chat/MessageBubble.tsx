import type { ChatMessage } from "@/stores/chatStore";

type MessageBubbleProps = {
  message: ChatMessage;
};

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user";

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[78%] text-right">
          <p className="mb-0.5 font-mono text-[10px] tracking-widest text-kibo-dim uppercase">you</p>
          <p className="border-r-2 border-kibo-accent/50 pr-3 text-sm leading-relaxed text-kibo-text">
            {message.text}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start">
      <div className="max-w-[78%]">
        <p className="mb-0.5 font-mono text-[10px] tracking-widest text-kibo-accent/60 uppercase">◈ kibo</p>
        <p className="border-l-2 border-kibo-accent/30 pl-3 text-sm leading-relaxed text-kibo-text">
          {message.text}
        </p>
      </div>
    </div>
  );
}
