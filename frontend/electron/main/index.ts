import { app, BrowserWindow, ipcMain, Menu } from "electron";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import { createChatWindow } from "./chat-window";
import { createPetWindow } from "./pet-window";
import { createSettingsWindow } from "./settings-window";
import { registerShortcuts, unregisterShortcuts } from "./shortcuts";
import { createTray } from "./tray";
import { PythonBridge } from "./python-bridge";
import { broadcastWindowState, getWindowState, patchWindowState } from "./window-state";

const isDev = Boolean(process.env.ELECTRON_RENDERER_URL);
const bridge = new PythonBridge();

let petWindow: BrowserWindow | null = null;
let chatWindow: BrowserWindow | null = null;
let settingsWindow: BrowserWindow | null = null;
let isQuitting = false;

function allWindows(): Array<BrowserWindow | null> {
  return [petWindow, chatWindow, settingsWindow];
}

function showChat(): void {
  chatWindow?.show();
  chatWindow?.focus();
}

function showSettings(): void {
  settingsWindow?.show();
  settingsWindow?.focus();
}

function togglePet(): void {
  if (!petWindow) {
    return;
  }
  if (petWindow.isVisible()) {
    petWindow.hide();
  } else {
    petWindow.show();
  }
}

function broadcast(channel: string, payload: unknown): void {
  for (const window of allWindows()) {
    if (window && !window.isDestroyed()) {
      window.webContents.send(channel, payload);
    }
  }
}

function talkShortcut(): void {
  showChat();
  broadcast("shortcut:pressed", { type: "talk" });
}

function clipShortcut(): void {
  showChat();
  broadcast("shortcut:pressed", { type: "clip" });
}

function rendererUrl(route: string): string {
  if (isDev && process.env.ELECTRON_RENDERER_URL) {
    return `${process.env.ELECTRON_RENDERER_URL}/#/${route}`;
  }

  const htmlPath = join(__dirname, "../renderer/index.html");
  return `${pathToFileURL(htmlPath).toString()}#/${route}`;
}

function preloadPath(): string {
  // Preload build is forced to CJS output (entryFileNames: "[name].js")
  return join(__dirname, "../preload/index.js");
}

async function createWindows(): Promise<void> {
  const preload = preloadPath();
  petWindow = createPetWindow({ preload, url: rendererUrl("pet") });
  chatWindow = createChatWindow({ preload, shouldQuit: () => isQuitting, url: rendererUrl("chat") });
  settingsWindow = createSettingsWindow({
    preload,
    shouldQuit: () => isQuitting,
    url: rendererUrl("settings"),
  });
  if (isDev) {
    chatWindow.once("ready-to-show", showChat);
  }

  createTray({
    showChat,
    showSettings,
    togglePet,
    talk: talkShortcut,
    clip: clipShortcut,
    quit: () => app.quit(),
  });
}

app.whenReady().then(async () => {
  Menu.setApplicationMenu(null);
  bridge.start();
  await bridge.waitUntilReady();
  await createWindows();
  registerShortcuts({
    talk: talkShortcut,
    clip: clipShortcut,
  });
});

app.on("before-quit", () => {
  isQuitting = true;
  unregisterShortcuts();
  bridge.stop();
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    void createWindows();
  } else {
    petWindow?.show();
  }
});

ipcMain.handle("app:show-chat", () => showChat());
ipcMain.handle("app:show-settings", () => showSettings());
ipcMain.handle("app:hide-current-window", (event) => {
  BrowserWindow.fromWebContents(event.sender)?.hide();
});
ipcMain.handle("app:toggle-maximize", (event) => {
  const win = BrowserWindow.fromWebContents(event.sender);
  if (win) {
    if (win.isMaximized()) {
      win.unmaximize();
    } else {
      win.maximize();
    }
  }
});
ipcMain.handle("app:quit", () => app.quit());
ipcMain.handle("backend:status", () => bridge.status());
ipcMain.handle("backend:health", () => bridge.health());
ipcMain.handle("pet:set-click-through", (_event, enabled: boolean) => {
  petWindow?.setIgnoreMouseEvents(enabled, { forward: true });
});

let _dragStartCursor = { x: 0, y: 0 };
let _dragStartWindow = { x: 0, y: 0 };

ipcMain.on("pet:drag-start", (_event, x: number, y: number) => {
  if (!petWindow) return;
  const [wx, wy] = petWindow.getPosition();
  _dragStartCursor = { x, y };
  _dragStartWindow = { x: wx, y: wy };
});

ipcMain.on("pet:drag-move", (_event, x: number, y: number) => {
  if (!petWindow) return;
  petWindow.setPosition(
    _dragStartWindow.x + (x - _dragStartCursor.x),
    _dragStartWindow.y + (y - _dragStartCursor.y),
  );
});

ipcMain.on("pet:drag-end", () => { /* position is already committed */ });
ipcMain.handle("state:get", () => getWindowState());
ipcMain.handle("state:patch", (_event, patch) => {
  const snapshot = patchWindowState(patch);
  broadcastWindowState(allWindows());
  return snapshot;
});
ipcMain.handle("assets:animation-path", (_event, relativePath: string) => {
  const assetRoot = app.isPackaged
    ? join(process.resourcesPath, "assets")
    : join(app.getAppPath(), "..", "assets");
  const assetPath = join(assetRoot, "animations", relativePath);

  // In dev mode the renderer runs on http://localhost (Vite). Chromium blocks
  // file:// loads from an http:// origin, so serve via Vite's /@fs/ route instead.
  if (!app.isPackaged && process.env.ELECTRON_RENDERER_URL) {
    const fsPath = assetPath.replace(/\\/g, "/");
    return `${process.env.ELECTRON_RENDERER_URL}/@fs/${fsPath}`;
  }

  return pathToFileURL(assetPath).toString();
});
