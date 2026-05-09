import { useEffect } from "react";
import { ChatWindow } from "./components/chat/ChatWindow";
import { OnboardingWindow } from "./components/onboarding/OnboardingWindow";
import { PetSprite } from "./components/pet/PetSprite";
import { SettingsWindow } from "./components/settings/SettingsWindow";
import { useWindowStateSync } from "./hooks/useWindowStateSync";
import { apiGet } from "./lib/kiboApi";
import { useSettingsStore } from "./stores/settingsStore";

function currentRoute(): string {
  return window.location.hash.replace(/^#\/?/, "") || "pet";
}

export function App() {
  useWindowStateSync();
  const setSettings = useSettingsStore((state) => state.setSettings);

  useEffect(() => {
    apiGet<Record<string, unknown>>("/settings", {}).then(setSettings);
  }, [setSettings]);

  const route = currentRoute();

  if (route === "chat") {
    return <ChatWindow />;
  }

  if (route === "settings") {
    return <SettingsWindow />;
  }

  if (route === "onboarding") {
    return <OnboardingWindow />;
  }

  return <PetSprite />;
}
