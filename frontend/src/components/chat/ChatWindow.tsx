import { useCallback, useEffect, useRef, useState } from "react";
import { Bot, Headphones, History, Maximize, Plus, Settings, Trash2, X } from "lucide-react";
import { apiDelete, apiGet, apiPost } from "@/lib/kiboApi";
import { MessageBubble } from "./MessageBubble";
import { InputBar } from "./InputBar";
import { MarkdownContent } from "./MarkdownContent";
import { useWebSocket } from "@/hooks/useWebSocket";
import { publishPetState } from "@/hooks/useWindowStateSync";
import { useChatStore } from "@/stores/chatStore";
import { usePetStore } from "@/stores/petStore";

function TypingIndicator() {
  return (
    <div className="animate-slide-up flex flex-col items-start gap-2">
      <div className="flex items-center gap-2 px-2 text-sm text-kibo-dim">
        <Bot size={16} />
        <span>KIBO</span>
      </div>
      <div className="flex items-center gap-1.5 rounded-[24px] rounded-bl-[6px] border border-kibo-accent-soft bg-kibo-accent-dim px-5 py-[18px] shadow-[0_2px_8px_oklch(0%_0_0_/_0.02)]">
        <span className="animate-typing-dot h-2 w-2 rounded-full bg-kibo-accent" style={{ animationDelay: "0ms" }} />
        <span className="animate-typing-dot h-2 w-2 rounded-full bg-kibo-accent" style={{ animationDelay: "200ms" }} />
        <span className="animate-typing-dot h-2 w-2 rounded-full bg-kibo-accent" style={{ animationDelay: "400ms" }} />
      </div>
    </div>
  );
}

type ChatEvent =
  | { type: "response_chunk"; text: string }
  | { type: "response_done"; text: string }
  | { type: "error"; message: string }
  | { type: "transcript_ready"; text: string }
  | { type: "recording_started" }
  | { type: "conversation_created"; id: string; title: string };

type ConversationMeta = {
  id: string;
  title: string;
  updated_at: string;
  message_count: number;
};

function formatConvDate(iso: string): string {
  const date = new Date(iso);
  const now = new Date();
  const diffDays = Math.floor((now.getTime() - date.getTime()) / 86400000);
  if (diffDays === 0) return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  if (diffDays === 1) return "Yesterday";
  if (diffDays < 7) return date.toLocaleDateString([], { weekday: "short" });
  return date.toLocaleDateString([], { month: "short", day: "numeric" });
}

export function ChatWindow() {
  const messages = useChatStore((state) => state.messages);
  const streamingText = useChatStore((state) => state.streamingText);
  const connectionState = useChatStore((state) => state.connectionState);
  const error = useChatStore((state) => state.error);
  const addMessage = useChatStore((state) => state.addMessage);
  const replaceMessages = useChatStore((state) => state.replaceMessages);
  const appendStream = useChatStore((state) => state.appendStream);
  const clearStream = useChatStore((state) => state.clearStream);
  const finishStream = useChatStore((state) => state.finishStream);
  const setConnectionState = useChatStore((state) => state.setConnectionState);
  const setError = useChatStore((state) => state.setError);
  const conversationId = useChatStore((state) => state.conversationId);
  const setConversationId = useChatStore((state) => state.setConversationId);
  const setMood = usePetStore((state) => state.setMood);
  const scrollRef = useRef<HTMLDivElement>(null);
  const [isListening, setIsListening] = useState(false);
  const [voiceMode, setVoiceMode] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [conversations, setConversations] = useState<ConversationMeta[]>([]);

  const refreshConversations = useCallback(async () => {
    const list = await apiGet<ConversationMeta[]>("/conversations", []);
    setConversations(list);
  }, []);

  useEffect(() => {
    void refreshConversations();
  }, [refreshConversations]);

  const handleMessage = useCallback(
    (message: MessageEvent) => {
      const event = JSON.parse(message.data) as ChatEvent;
      if (event.type === "recording_started") {
        setIsListening(true);
      }
      if (event.type === "transcript_ready") {
        addMessage({ id: crypto.randomUUID(), role: "user", text: event.text });
        setIsListening(false);
        setMood("thinking");
        publishPetState({ animationState: "action", mood: "thinking", speech: "" });
      }
      if (event.type === "response_chunk") {
        setIsListening(false);
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
        setIsListening(false);
        setError(event.message);
        setMood("idle");
        publishPetState({ animationState: "idle", mood: "idle", speech: event.message });
      }
      if (event.type === "conversation_created") {
        setConversationId(event.id);
        setConversations((prev) => [
          { id: event.id, title: event.title, updated_at: new Date().toISOString(), message_count: 0 },
          ...prev,
        ]);
      }
    },
    [addMessage, appendStream, finishStream, setConversationId, setError, setMood],
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
    socket.send({ type: "query", text, conversation_id: conversationId });
  }

  function handleNewChat() {
    setConversationId(null);
    replaceMessages([]);
    clearStream();
    setError("");
    setMood("idle");
    setSidebarOpen(false);
  }

  async function handleLoadConversation(id: string) {
    type ConvData = { messages: Array<{ id: string; role: string; text: string }> };
    const data = await apiGet<ConvData | null>(`/conversations/${id}`, null);
    if (!data) return;
    replaceMessages(
      data.messages
        .filter((m) => m.role === "user" || m.role === "assistant")
        .map((m) => ({ id: m.id, role: m.role as "user" | "assistant", text: m.text })),
    );
    clearStream();
    setError("");
    setConversationId(id);
    setSidebarOpen(false);
  }

  async function handleDeleteConversation(id: string, e: React.MouseEvent) {
    e.stopPropagation();
    await apiDelete(`/conversations/${id}`, { ok: true });
    setConversations((prev) => prev.filter((c) => c.id !== id));
    if (conversationId === id) handleNewChat();
  }

  async function toggleVoiceMode() {
    const next = !voiceMode;
    setVoiceMode(next);
    await apiPost("/settings", { tts_enabled: next }, { ok: true });
  }

  function handleVoice() {
    if (isListening) return;
    setIsListening(true);
    setError("");
    clearStream();
    setMood("listening");
    publishPetState({ animationState: "action", mood: "listening", speech: "Listening…" });
    socket.send({ type: "voice_start" });
  }

  const isConnected = connectionState === "open";
  const isEmpty = messages.length === 0 && !streamingText && !error;
  const isLoading =
    messages.length > 0 &&
    messages[messages.length - 1].role === "user" &&
    !streamingText &&
    !error;

  return (
    <main className="relative flex h-screen flex-col bg-kibo-bg text-kibo-text">

      {/* Sidebar backdrop */}
      {sidebarOpen && (
        <div
          className="absolute inset-0 z-10 bg-black/20"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Conversation sidebar */}
      <aside
        className={`absolute left-0 top-0 z-20 flex h-full w-72 flex-col border-r border-kibo-border bg-kibo-surface shadow-xl transition-transform duration-200 ${
          sidebarOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="drag-region flex shrink-0 items-center justify-between border-b border-kibo-border px-4 py-4">
          <span className="text-sm font-medium text-kibo-text">Conversations</span>
          <button
            className="grid h-7 w-7 place-items-center rounded-full text-kibo-dim transition hover:bg-kibo-bg hover:text-kibo-text"
            type="button"
            onClick={() => setSidebarOpen(false)}
          >
            <X size={15} />
          </button>
        </div>

        <div className="no-drag shrink-0 p-3">
          <button
            className="flex w-full items-center gap-2 rounded-xl border border-kibo-border bg-kibo-bg px-4 py-2.5 text-sm text-kibo-text transition hover:border-kibo-accent/40 hover:bg-kibo-accent-dim"
            type="button"
            onClick={handleNewChat}
          >
            <Plus size={15} />
            New chat
          </button>
        </div>

        <div className="no-drag flex-1 overflow-y-auto px-2 pb-4">
          {conversations.length === 0 ? (
            <p className="px-3 py-4 text-center text-xs text-kibo-dim">No conversations yet</p>
          ) : (
            conversations.map((conv) => (
              <button
                key={conv.id}
                type="button"
                className={`group flex w-full items-start justify-between gap-2 rounded-xl px-3 py-2.5 text-left transition hover:bg-kibo-bg ${
                  conversationId === conv.id ? "bg-kibo-accent-dim" : ""
                }`}
                onClick={() => handleLoadConversation(conv.id)}
              >
                <div className="min-w-0 flex-1">
                  <p className={`truncate text-sm ${conversationId === conv.id ? "font-medium text-kibo-accent" : "text-kibo-text"}`}>
                    {conv.title}
                  </p>
                  <p className="mt-0.5 text-xs text-kibo-dim">{formatConvDate(conv.updated_at)}</p>
                </div>
                <button
                  type="button"
                  className="mt-0.5 shrink-0 text-kibo-dim opacity-0 transition hover:text-red-400 group-hover:opacity-100"
                  aria-label="Delete conversation"
                  onClick={(e) => handleDeleteConversation(conv.id, e)}
                >
                  <Trash2 size={13} />
                </button>
              </button>
            ))
          )}
        </div>
      </aside>

      {/* Draggable header */}
      <header className="drag-region flex shrink-0 items-center justify-between px-6 py-4">
        <div className="no-drag flex items-center gap-3">
          <button
            className="grid h-9 w-9 place-items-center rounded-full text-kibo-dim transition-all hover:bg-kibo-surface hover:text-kibo-text"
            type="button"
            aria-label="Conversation history"
            onClick={() => { setSidebarOpen(true); void refreshConversations(); }}
          >
            <History size={18} />
          </button>
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
            className={`grid h-9 w-9 place-items-center rounded-full transition-all ${
              voiceMode
                ? "bg-kibo-accent text-white shadow-[0_0_10px_var(--color-kibo-accent-glow)]"
                : "text-kibo-dim hover:bg-kibo-surface hover:text-kibo-text"
            }`}
            type="button"
            aria-label={voiceMode ? "Voice mode on — click to disable" : "Enable voice mode"}
            aria-pressed={voiceMode}
            onClick={toggleVoiceMode}
          >
            <Headphones size={18} />
          </button>
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

            {isLoading ? <TypingIndicator /> : null}

            {streamingText ? (
              <div className="animate-slide-up flex flex-col items-start gap-2">
                <div className="flex items-center gap-2 px-2 text-sm text-kibo-dim">
                  <Bot size={16} />
                  <span>KIBO</span>
                </div>
                <div className="max-w-[85%] rounded-[24px] rounded-bl-[6px] border border-kibo-accent-soft bg-kibo-accent-dim px-6 py-4 text-base text-kibo-text shadow-[0_2px_8px_oklch(0%_0_0_/_0.02)]">
                  <MarkdownContent text={streamingText} />
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
      <InputBar disabled={!isConnected} isListening={isListening} onSend={send} onVoice={handleVoice} />
    </main>
  );
}
