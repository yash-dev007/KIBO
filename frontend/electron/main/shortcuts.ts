import { app, globalShortcut } from "electron";

type ShortcutActions = {
  talk: () => void;
  clip: () => void;
};

export function registerShortcuts(actions: ShortcutActions): void {
  globalShortcut.unregisterAll();
  globalShortcut.register("CommandOrControl+K", actions.talk);
  globalShortcut.register("CommandOrControl+Alt+K", actions.clip);
}

export function unregisterShortcuts(): void {
  if (app.isReady()) {
    globalShortcut.unregisterAll();
  }
}
