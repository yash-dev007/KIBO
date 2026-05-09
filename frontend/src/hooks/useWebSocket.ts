import { useEffect, useRef, useState } from "react";
import { backendBaseUrl } from "@/lib/kiboApi";

type WebSocketState = "idle" | "connecting" | "open" | "closed" | "error";

const RECONNECT_DELAY_MS = 3000;

export function useWebSocket(path: string, onMessage?: (message: MessageEvent) => void) {
  const socketRef = useRef<WebSocket | null>(null);
  const [state, setState] = useState<WebSocketState>("idle");

  useEffect(() => {
    let cancelled = false;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;

    async function connect() {
      if (cancelled) return;

      const backendUrl = await backendBaseUrl();
      if (cancelled) return;

      const url = backendUrl.replace(/^http/, "ws") + path;
      const socket = new WebSocket(url);
      socketRef.current = socket;
      setState("connecting");

      socket.addEventListener("open", () => setState("open"));
      socket.addEventListener("close", () => {
        setState("closed");
        if (!cancelled) {
          retryTimer = setTimeout(connect, RECONNECT_DELAY_MS);
        }
      });
      socket.addEventListener("error", () => {
        setState("error");
        socket.close();
      });
      if (onMessage) {
        socket.addEventListener("message", onMessage);
      }
    }

    void connect();

    return () => {
      cancelled = true;
      if (retryTimer) clearTimeout(retryTimer);
      socketRef.current?.close();
      socketRef.current = null;
    };
  }, [path, onMessage]);

  return {
    state,
    send: (payload: unknown) => socketRef.current?.send(JSON.stringify(payload)),
  };
}
