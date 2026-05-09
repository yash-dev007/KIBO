import { BrowserWindow } from "electron";

type WindowOptions = {
  preload: string;
  url: string;
};

export function createPetWindow({ preload, url }: WindowOptions): BrowserWindow {
  const window = new BrowserWindow({
    width: 200,
    height: 200,
    frame: false,
    transparent: true,
    hasShadow: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    resizable: false,
    movable: true,
    show: false,
    webPreferences: {
      preload,
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  window.setIgnoreMouseEvents(true, { forward: true });
  window.setAlwaysOnTop(true, "screen-saver");
  window.loadURL(url);
  window.once("ready-to-show", () => window.show());

  return window;
}
