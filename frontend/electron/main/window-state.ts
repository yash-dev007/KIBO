import type { BrowserWindow } from "electron";

export type WindowState = {
  pet: {
    animationState: string;
    mood: string;
    speech: string;
  };
  settings: {
    skin: string;
  };
};

const state: WindowState = {
  pet: {
    animationState: "idle",
    mood: "idle",
    speech: "",
  },
  settings: {
    skin: "skales",
  },
};

export function getWindowState(): WindowState {
  return structuredClone(state);
}

export function patchWindowState(patch: Partial<WindowState>): WindowState {
  if (patch.pet) {
    state.pet = { ...state.pet, ...patch.pet };
  }
  if (patch.settings) {
    state.settings = { ...state.settings, ...patch.settings };
  }
  return getWindowState();
}

export function broadcastWindowState(windows: Array<BrowserWindow | null>): void {
  const snapshot = getWindowState();
  for (const window of windows) {
    if (window && !window.isDestroyed()) {
      window.webContents.send("state:changed", snapshot);
    }
  }
}
