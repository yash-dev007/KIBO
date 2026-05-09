import { useCallback, useEffect, useRef } from "react";
import { Settings, X } from "lucide-react";
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

  return (
    <main className="flex min-h-screen flex-col bg-kibo-bg text-kibo-text">
      {/* Header */}
      <header className="flex items-center justify-between border-b border-white/5 px-4 py-2.5">
        <div className="flex items-center gap-2.5">
          <span
            className={`h-1.5 w-1.5 rounded-full transition-colors ${
              isConnected ? "bg-kibo-accent shadow-[0_0_6px_var(--color-kibo-accent)]" : "bg-red-500/70"
            }`}
          />
          <span className="font-mono text-xs font-semibold tracking-[0.2em] text-kibo-text uppercase">
            KIBO
          </span>
          <span className="rounded border border-kibo-accent/20 px-1.5 py-px font-mono text-[10px] tracking-wider text-kibo-accent/50 uppercase">
            AI
          </span>
        </div>
        <div className="flex items-center gap-1">
          <button
            className="grid h-7 w-7 place-items-center rounded text-kibo-dim transition-colors hover:text-kibo-text"
            type="button"
            aria-label="Settings"
            onClick={() => window.kibo?.app.showSettings()}
          >
            <Settings size={13} />
          </button>
          <button
            className="grid h-7 w-7 place-items-center rounded text-kibo-dim transition-colors hover:text-kibo-text"
            type="button"
            aria-label="Close"
            onClick={() => window.kibo?.app.hideCurrentWindow()}
          >
            <X size={13} />
          </button>
        </div>
      </header>

      {/* Messages */}
      <section
        ref={scrollRef}
        className="kibo-scroll flex-1 space-y-4 overflow-auto p-4"
      >
        {messages.length === 0 && !streamingText ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 text-center">
            <p className="font-mono text-xs tracking-[0.3em] text-kibo-dim/60 uppercase">
              session started
            </p>
            <p className="font-mono text-[11px] text-kibo-dim/40">
              › ask anything
            </p>
          </div>
        ) : null}

        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} />
        ))}

        {streamingText ? (
          <div className="flex justify-start">
            <div className="max-w-[78%]">
              <p className="mb-0.5 font-mono text-[10px] tracking-widest text-kibo-accent/60 uppercase">◈ kibo</p>
              <p className="border-l-2 border-kibo-accent/30 pl-3 text-sm leading-relaxed text-kibo-text">
                {streamingText}
                <span className="cursor-blink ml-0.5 inline-block h-3 w-0.5 bg-kibo-accent align-middle" />
              </p>
            </div>
          </div>
        ) : null}

        {error ? (
          <div className="flex justify-start">
            <p className="border-l-2 border-red-500/50 pl-3 font-mono text-xs text-red-400/80">
              ✗ {error}
            </p>
          </div>
        ) : null}
      </section>

      <InputBar disabled={!isConnected} onSend={send} />
    </main>
  );
}
