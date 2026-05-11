import { BrowserWindow } from "electron";

type WindowOptions = {
  preload: string;
  url: string;
  shouldQuit?: () => boolean;
};

export function createChatWindow({ preload, shouldQuit, url }: WindowOptions): BrowserWindow {
  const window = new BrowserWindow({
    width: 460,
    height: 640,
    minWidth: 380,
    minHeight: 480,
    show: false,
    frame: false,
    backgroundColor: "#faf8f5",
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
