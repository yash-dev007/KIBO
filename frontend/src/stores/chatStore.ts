import { create } from "zustand";

export type ChatMessage = {
  id: string;
  role: "user" | "assistant" | "system";
  text: string;
};

type ChatState = {
  messages: ChatMessage[];
  streamingText: string;
  connectionState: string;
  error: string;
  conversationId: string | null;
  addMessage: (message: ChatMessage) => void;
  replaceMessages: (messages: ChatMessage[]) => void;
  appendStream: (text: string) => void;
  finishStream: () => void;
  clearStream: () => void;
  setConnectionState: (connectionState: string) => void;
  setError: (error: string) => void;
  setConversationId: (id: string | null) => void;
};

export const useChatStore = create<ChatState>((set) => ({
  messages: [],
  streamingText: "",
  connectionState: "idle",
  error: "",
  conversationId: null,
  addMessage: (message) => set((state) => ({ messages: [...state.messages, message] })),
  replaceMessages: (messages) => set({ messages }),
  setConversationId: (id) => set({ conversationId: id }),
  appendStream: (text) =>
    set((state) => ({ streamingText: `${state.streamingText}${text}` })),
  finishStream: () =>
    set((state) => {
      const text = state.streamingText.trim();
      if (!text) {
        return { streamingText: "" };
      }
      return {
        streamingText: "",
        messages: [
          ...state.messages,
          { id: crypto.randomUUID(), role: "assistant", text },
        ],
      };
    }),
  clearStream: () => set({ streamingText: "" }),
  setConnectionState: (connectionState) => set({ connectionState }),
  setError: (error) => set({ error }),
}));
