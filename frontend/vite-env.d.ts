/// <reference types="vite/client" />

interface KiboApi {
  app: {
    showChat: () => void;
    showSettings: () => void;
    hideCurrentWindow: () => void;
    toggleMaximize: () => void;
    quit: () => void;
    onShortcut: (handler: (event: { type: "talk" | "clip" }) => void) => () => void;
  };
  backend: {
    status: () => Promise<{ running: boolean; url: string }>;
    health: () => Promise<boolean>;
  };
  pet: {
    setClickThrough: (enabled: boolean) => Promise<void>;
    dragStart: (x: number, y: number) => void;
    dragMove: (x: number, y: number) => void;
    dragEnd: () => void;
  };
  state: {
    get: () => Promise<WindowStateSnapshot>;
    patch: (patch: WindowStatePatch) => Promise<WindowStateSnapshot>;
    onChanged: (handler: (state: WindowStateSnapshot) => void) => () => void;
  };
  assets: {
    animationPath: (relativePath: string) => Promise<string>;
  };
}

type WindowStateSnapshot = {
  pet: {
    animationState: string;
    mood: string;
    speech: string;
  };
  settings: {
    skin: string;
  };
};

type WindowStatePatch = {
  pet?: Partial<WindowStateSnapshot["pet"]>;
  settings?: Partial<WindowStateSnapshot["settings"]>;
};

interface Window {
  kibo?: KiboApi;
}
