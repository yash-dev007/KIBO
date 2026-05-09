import { create } from "zustand";

export type PetAnimationState = "idle" | "intro" | "action" | "outro";

type PetState = {
  animationState: PetAnimationState;
  speech: string;
  mood: "idle" | "listening" | "thinking" | "talking" | "notify";
  setAnimationState: (animationState: PetAnimationState) => void;
  setMood: (mood: PetState["mood"]) => void;
  setSpeech: (speech: string | ((prev: string) => string)) => void;
};

export const usePetStore = create<PetState>((set) => ({
  animationState: "idle",
  mood: "idle",
  speech: "",
  setAnimationState: (animationState) => set({ animationState }),
  setMood: (mood) => set({ mood }),
  setSpeech: (speech) =>
    set((state) => ({ speech: typeof speech === "function" ? speech(state.speech) : speech })),
}));
