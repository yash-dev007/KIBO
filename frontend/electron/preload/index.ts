import { contextBridge, ipcRenderer } from "electron";

contextBridge.exposeInMainWorld("kibo", {
  app: {
    showChat: () => ipcRenderer.invoke("app:show-chat"),
    showSettings: () => ipcRenderer.invoke("app:show-settings"),
    hideCurrentWindow: () => ipcRenderer.invoke("app:hide-current-window"),
    toggleMaximize: () => ipcRenderer.invoke("app:toggle-maximize"),
    quit: () => ipcRenderer.invoke("app:quit"),
    onShortcut: (handler: (event: { type: "talk" | "clip" }) => void) => {
      const listener = (_event: Electron.IpcRendererEvent, payload: { type: "talk" | "clip" }) =>
        handler(payload);
      ipcRenderer.on("shortcut:pressed", listener);
      return () => ipcRenderer.off("shortcut:pressed", listener);
    },
  },
  backend: {
    status: () => ipcRenderer.invoke("backend:status"),
    health: () => ipcRenderer.invoke("backend:health"),
  },
  pet: {
    setClickThrough: (enabled: boolean) => ipcRenderer.invoke("pet:set-click-through", enabled),
    dragStart: (x: number, y: number) => ipcRenderer.send("pet:drag-start", x, y),
    dragMove: (x: number, y: number) => ipcRenderer.send("pet:drag-move", x, y),
    dragEnd: () => ipcRenderer.send("pet:drag-end"),
  },
  state: {
    get: () => ipcRenderer.invoke("state:get"),
    patch: (patch: unknown) => ipcRenderer.invoke("state:patch", patch),
    onChanged: (handler: (state: unknown) => void) => {
      const listener = (_event: Electron.IpcRendererEvent, state: unknown) => handler(state);
      ipcRenderer.on("state:changed", listener);
      return () => ipcRenderer.off("state:changed", listener);
    },
  },
  assets: {
    animationPath: (relativePath: string) =>
      ipcRenderer.invoke("assets:animation-path", relativePath),
  },
});
