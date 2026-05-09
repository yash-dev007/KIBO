import { app, Menu, Tray } from "electron";
import { join } from "node:path";

type TrayActions = {
  showChat: () => void;
  showSettings: () => void;
  togglePet: () => void;
  talk: () => void;
  clip: () => void;
  quit: () => void;
};

let tray: Tray | null = null;

export function createTray(actions: TrayActions): Tray {
  const iconPath = join(app.getAppPath(), "..", "assets", "animations", "skales", "icon.png");
  tray = new Tray(iconPath);
  tray.setToolTip("KIBO");
  tray.setContextMenu(
    Menu.buildFromTemplate([
      { label: "Open Chat", click: actions.showChat },
      { label: "Talk", accelerator: "Ctrl+K", click: actions.talk },
      { label: "Capture Clip", accelerator: "Ctrl+Alt+K", click: actions.clip },
      { label: "Show/Hide Pet", click: actions.togglePet },
      { label: "Settings", click: actions.showSettings },
      { type: "separator" },
      { label: "Quit KIBO", click: actions.quit },
    ]),
  );

  return tray;
}
