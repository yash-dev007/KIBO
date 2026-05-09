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
  addMessage: (message: ChatMessage) => void;
  appendStream: (text: string) => void;
  finishStream: () => void;
  clearStream: () => void;
  setConnectionState: (connectionState: string) => void;
  setError: (error: string) => void;
};

export const useChatStore = create<ChatState>((set) => ({
  messages: [],
  streamingText: "",
  connectionState: "idle",
  error: "",
  addMessage: (message) => set((state) => ({ messages: [...state.messages, message] })),
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
