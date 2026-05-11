import { useCallback, useEffect, useRef } from "react";
import { Bot, Maximize, Settings, X } from "lucide-react";
import { MessageBubble } from "./MessageBubble";
import { InputBar } from "./InputBar";
import { useWebSocket } from "@/hooks/useWebSocket";
import { publishPetState } from "@/hooks/useWindowStateSync";
import { useChatStore } from "@/stores/chatStore";
import { usePetStore } from "@/stores/petStore";

type ChatEvent =
  | { type: "response_chunk"; text: string }
  | { type: "response_done"; text: string }
  | { type: "error"; message: string };

export function ChatWindow() {
  const messages = useChatStore((state) => state.messages);
  const streamingText = useChatStore((state) => state.streamingText);
  const connectionState = useChatStore((state) => state.connectionState);
  const error = useChatStore((state) => state.error);
  const appendStream = useChatStore((state) => state.appendStream);
  const clearStream = useChatStore((state) => state.clearStream);
  const finishStream = useChatStore((state) => state.finishStream);
  const setConnectionState = useChatStore((state) => state.setConnectionState);
  const setError = useChatStore((state) => state.setError);
  const setMood = usePetStore((state) => state.setMood);
  const scrollRef = useRef<HTMLDivElement>(null);

  const handleMessage = useCallback(
    (message: MessageEvent) => {
      const event = JSON.parse(message.data) as ChatEvent;
      if (event.type === "response_chunk") {
        appendStream(event.text);
        setMood("talking");
        publishPetState({ animationState: "action", mood: "talking" });
      }
      if (event.type === "response_done") {
        finishStream();
        setMood("idle");
        publishPetState({ animationState: "idle", mood: "idle" });
      }
      if (event.type === "error") {
        setError(event.message);
        setMood("idle");
        publishPetState({ animationState: "idle", mood: "idle", speech: event.message });
      }
    },
    [appendStream, finishStream, setError, setMood],
  );

  const socket = useWebSocket("/ws/chat", handleMessage);

  useEffect(() => {
    setConnectionState(socket.state);
  }, [setConnectionState, socket.state]);

  useEffect(() => {
    return window.kibo?.app.onShortcut((event) => {
      if (event.type === "talk") {
        setMood("listening");
        publishPetState({ animationState: "action", mood: "listening", speech: "Listening." });
      }
      if (event.type === "clip") {
        setMood("thinking");
        publishPetState({ animationState: "action", mood: "thinking", speech: "Capturing context." });
      }
    });
  }, [setMood]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, streamingText]);

  function send(text: string) {
    setError("");
    clearStream();
    setMood("thinking");
    publishPetState({ animationState: "action", mood: "thinking", speech: "" });
    socket.send({ type: "query", text });
  }

  const isConnected = connectionState === "open";
  const isEmpty = messages.length === 0 && !streamingText && !error;

  return (
    <main className="flex h-screen flex-col bg-kibo-bg text-kibo-text">
      {/* Draggable header */}
      <header className="drag-region flex shrink-0 items-center justify-between px-6 py-4">
        <div className="no-drag flex items-center gap-3">
          <span
            className={`h-2 w-2 rounded-full transition-all ${
              isConnected
                ? "bg-kibo-accent shadow-[0_0_8px_var(--color-kibo-accent)]"
                : "bg-[oklch(60%_0.18_20)] shadow-[0_0_8px_oklch(60%_0.18_20)]"
            }`}
          />
          <span className="font-display text-xl italic tracking-tight text-kibo-text">KIBO</span>
        </div>
        <div className="no-drag flex gap-1">
          <button
            className="grid h-9 w-9 place-items-center rounded-full text-kibo-dim transition-all hover:bg-kibo-surface hover:text-kibo-text"
            type="button"
            aria-label="Maximize"
            onClick={() => window.kibo?.app.toggleMaximize()}
          >
            <Maximize size={20} />
          </button>
          <button
            className="grid h-9 w-9 place-items-center rounded-full text-kibo-dim transition-all hover:bg-kibo-surface hover:text-kibo-text"
            type="button"
            aria-label="Settings"
            onClick={() => window.kibo?.app.showSettings()}
          >
            <Settings size={20} />
          </button>
          <button
            className="grid h-9 w-9 place-items-center rounded-full text-kibo-dim transition-all hover:bg-kibo-surface hover:text-kibo-text"
            type="button"
            aria-label="Close"
            onClick={() => window.kibo?.app.quit()}
          >
            <X size={20} />
          </button>
        </div>
      </header>

      {/* Scrollable chat canvas — pb-[120px] keeps content above floating input */}
      <section
        ref={scrollRef}
        className="chat-scroll flex-1 overflow-y-auto px-6 pb-4 pt-2"
      >
        {isEmpty ? (
          <div className="animate-fade-in flex h-full flex-col items-center justify-center gap-4">
            <Bot size={64} strokeWidth={1.5} className="text-kibo-border" />
            <p className="text-lg tracking-wide text-kibo-dim">ask anything</p>
          </div>
        ) : (
          <div className="mx-auto flex w-full max-w-[800px] flex-col gap-6">
            {messages.map((message, index) => (
              <MessageBubble
                key={message.id}
                message={message}
                isFirstInGroup={
                  message.role !== "user" &&
                  (index === 0 || messages[index - 1].role === "user")
                }
              />
            ))}

            {streamingText ? (
              <div className="animate-slide-up flex flex-col items-start gap-2">
                <div className="flex items-center gap-2 px-2 text-sm text-kibo-dim">
                  <Bot size={16} />
                  <span>KIBO</span>
                </div>
                <div className="max-w-[85%] rounded-[24px] rounded-bl-[6px] border border-kibo-accent-soft bg-kibo-accent-dim px-6 py-4 text-base leading-relaxed text-kibo-text shadow-[0_2px_8px_oklch(0%_0_0_/_0.02)]">
                  {streamingText}
                  <span className="cursor-blink ml-0.5 inline-block h-3.5 w-0.5 bg-kibo-accent align-middle" />
                </div>
              </div>
            ) : null}

            {error ? (
              <div className="animate-slide-up flex flex-col items-start">
                <div className="rounded-[24px] rounded-bl-[6px] border border-red-200 bg-red-50 px-6 py-4 text-base text-red-600">
                  {error}
                </div>
              </div>
            ) : null}
          </div>
        )}
      </section>

      {/* Floating input — absolutely anchored to bottom of main */}
      <InputBar disabled={!isConnected} onSend={send} />
    </main>
  );
}
