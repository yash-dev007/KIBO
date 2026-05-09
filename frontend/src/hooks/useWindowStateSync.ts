import { useEffect } from "react";
import { kiboApi } from "@/lib/kiboApi";
import type { PetAnimationState } from "@/stores/petStore";
import { usePetStore } from "@/stores/petStore";
import { useSettingsStore } from "@/stores/settingsStore";

function applySnapshot(snapshot: WindowStateSnapshot): void {
  const pet = usePetStore.getState();
  const settings = useSettingsStore.getState();
  pet.setAnimationState(snapshot.pet.animationState as PetAnimationState);
  pet.setMood(snapshot.pet.mood as ReturnType<typeof usePetStore.getState>["mood"]);
  pet.setSpeech(snapshot.pet.speech);
  settings.setSkin(snapshot.settings.skin);
}

export function useWindowStateSync(): void {
  useEffect(() => {
    let disposed = false;

    kiboApi()
      .state.get()
      .then((snapshot) => {
        if (!disposed) {
          applySnapshot(snapshot);
        }
      });

    const unsubscribe = kiboApi().state.onChanged(applySnapshot);
    return () => {
      disposed = true;
      unsubscribe();
    };
  }, []);
}

export function publishPetState(patch: Partial<WindowStateSnapshot["pet"]>): void {
  void kiboApi().state.patch({ pet: patch });
}

export function publishSettingsState(patch: Partial<WindowStateSnapshot["settings"]>): void {
  void kiboApi().state.patch({ settings: patch });
}
