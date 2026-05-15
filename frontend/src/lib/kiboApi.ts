const DEFAULT_BACKEND_URL = "http://127.0.0.1:8765";

function fallbackApi(): KiboApi {
  return {
    app: {
      showChat: () => undefined,
      showSettings: () => undefined,
      hideCurrentWindow: () => undefined,
      toggleMaximize: () => undefined,
      quit: () => undefined,
      onShortcut: () => () => undefined,
    },
    backend: {
      status: async () => ({ running: false, url: DEFAULT_BACKEND_URL }),
      health: async () => false,
    },
    pet: {
      setClickThrough: async () => undefined,
      dragStart: () => undefined,
      dragMove: () => undefined,
      dragEnd: () => undefined,
    },
    state: {
      get: async () => ({
        pet: { animationState: "idle", mood: "idle", speech: "" },
        settings: { skin: "skales" },
      }),
      patch: async (patch: WindowStatePatch) => ({
        pet: {
          animationState: patch.pet?.animationState ?? "idle",
          mood: patch.pet?.mood ?? "idle",
          speech: patch.pet?.speech ?? "",
        },
        settings: { skin: patch.settings?.skin ?? "skales" },
      }),
      onChanged: () => () => undefined,
    },
    assets: {
      animationPath: async (relativePath: string) =>
        new URL(`../../../assets/animations/${relativePath}`, import.meta.url).toString(),
    },
  };
}

export function kiboApi(): KiboApi {
  return window.kibo ?? fallbackApi();
}

export async function backendBaseUrl(): Promise<string> {
  const status = await kiboApi().backend.status();
  return status.url || DEFAULT_BACKEND_URL;
}

export async function apiGet<T>(path: string, fallback: T): Promise<T> {
  try {
    const response = await fetch(`${await backendBaseUrl()}${path}`);
    if (!response.ok) {
      return fallback;
    }
    return (await response.json()) as T;
  } catch {
    return fallback;
  }
}

export async function apiDelete<T>(path: string, fallback: T): Promise<T> {
  try {
    const response = await fetch(`${await backendBaseUrl()}${path}`, { method: "DELETE" });
    if (!response.ok) return fallback;
    return (await response.json()) as T;
  } catch {
    return fallback;
  }
}

export async function apiPost<T>(path: string, body: unknown, fallback: T): Promise<T> {
  try {
    const response = await fetch(`${await backendBaseUrl()}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      return fallback;
    }
    return (await response.json()) as T;
  } catch {
    return fallback;
  }
}
