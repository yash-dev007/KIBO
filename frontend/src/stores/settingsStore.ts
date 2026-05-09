import { create } from "zustand";

type SettingsState = {
  accentColor: string;
  settings: Record<string, unknown>;
  skin: string;
  setAccentColor: (accentColor: string) => void;
  setSettings: (settings: Record<string, unknown>) => void;
  updateSetting: (key: string, value: unknown) => void;
  setSkin: (skin: string) => void;
};

export const useSettingsStore = create<SettingsState>((set) => ({
  accentColor: "#8FBF6A",
  settings: {},
  skin: "skales",
  setAccentColor: (accentColor) => set({ accentColor }),
  setSettings: (settings) =>
    set({
      settings,
      skin: typeof settings.buddy_skin === "string" ? settings.buddy_skin : "skales",
    }),
  updateSetting: (key, value) =>
    set((state) => ({
      settings: { ...state.settings, [key]: value },
      skin: key === "buddy_skin" && typeof value === "string" ? value : state.skin,
    })),
  setSkin: (skin) => set({ skin }),
}));
