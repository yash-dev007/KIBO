import { BrowserWindow } from "electron";

type WindowOptions = {
  preload: string;
  url: string;
  shouldQuit?: () => boolean;
};

export function createSettingsWindow({ preload, shouldQuit, url }: WindowOptions): BrowserWindow {
  const window = new BrowserWindow({
    width: 900,
    height: 680,
    minWidth: 720,
    minHeight: 560,
    show: false,
    title: "KIBO Settings",
    backgroundColor: "#1e1e2e",
    webPreferences: {
      preload,
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  window.loadURL(url);
  window.on("close", (event) => {
    if (!shouldQuit?.() && !window.isDestroyed()) {
      event.preventDefault();
      window.hide();
    }
  });
  return window;
}
