import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { kiboApi } from "@/lib/kiboApi";
import { useWebSocket } from "@/hooks/useWebSocket";
import { publishPetState } from "@/hooks/useWindowStateSync";
import { usePetStore } from "@/stores/petStore";
import { useSettingsStore } from "@/stores/settingsStore";
import { SpeechBubble } from "./SpeechBubble";

const animationBySkin = {
  skales: {
    idle: "idle/still.webm",
    intro: "intro/spawn.webm",
    action: "action/smartphone.webm",
    outro: "outro/out.webm",
  },
  bubbles: {
    idle: "idle/vibe.webm",
    intro: "intro/dropin.webm",
    action: "action/magic.webm",
    outro: "idle/chill.webm",
  },
  capy: {
    idle: "idle/idle.webm",
    intro: "intro/unfolding.webm",
    action: "action/keyboard.webm",
    outro: "idle/tired.webm",
  },
};

export function PetSprite() {
  const animationState = usePetStore((state) => state.animationState);
  const setAnimationState = usePetStore((state) => state.setAnimationState);
  const speech = usePetStore((state) => state.speech);
  const setSpeech = usePetStore((state) => state.setSpeech);
  const mood = usePetStore((state) => state.mood);
  const skin = useSettingsStore((state) => state.skin);
  const [src, setSrc] = useState("");
  const [fallbackSrc, setFallbackSrc] = useState("");
  const [videoFailed, setVideoFailed] = useState(false);
  const dragging = useRef(false);

  const handleStateMessage = useCallback(
    (message: MessageEvent) => {
      const event = JSON.parse(message.data) as { type: string; message?: string; task?: unknown };
      if (event.type === "proactive_notification" && event.message) {
        setSpeech(event.message);
        setAnimationState("action");
        publishPetState({ animationState: "action", mood: "notify", speech: event.message });
      }
      if (event.type === "task_completed") {
        setSpeech("Done.");
        setAnimationState("action");
        publishPetState({ animationState: "action", mood: "notify", speech: "Done." });
      }
      if (event.type === "task_blocked") {
        setSpeech("I need a hand with that.");
        setAnimationState("action");
        publishPetState({
          animationState: "action",
          mood: "notify",
          speech: "I need a hand with that.",
        });
      }
    },
    [setAnimationState, setSpeech],
  );

  useWebSocket("/ws/state", handleStateMessage);

  const handleChatMessage = useCallback(
    (message: MessageEvent) => {
      const event = JSON.parse(message.data) as { type: string; text?: string; message?: string };
      if (event.type === "response_chunk" && event.text) {
        const chunk = event.text;
        setSpeech((prev) => (prev ? `${prev}${chunk}` : chunk).slice(-220));
        setAnimationState("action");
        publishPetState({ animationState: "action", mood: "talking" });
      }
      if (event.type === "response_done") {
        setAnimationState("idle");
        publishPetState({ animationState: "idle", mood: "idle" });
      }
      if (event.type === "error" && event.message) {
        setSpeech(event.message);
        setAnimationState("idle");
        publishPetState({ animationState: "idle", mood: "idle", speech: event.message });
      }
    },
    [setAnimationState, setSpeech],
  );

  useWebSocket("/ws/chat", handleChatMessage);

  const resolvedState = useMemo(() => {
    if (mood === "thinking" || mood === "talking" || mood === "notify") {
      return "action";
    }
    return animationState;
  }, [animationState, mood]);

  useEffect(() => {
    const skinKey = skin in animationBySkin ? (skin as keyof typeof animationBySkin) : "skales";
    const relative = `${skinKey}/${animationBySkin[skinKey][resolvedState]}`;
    setVideoFailed(false);
    kiboApi().assets.animationPath(relative).then(setSrc);
    kiboApi().assets.animationPath(`${skinKey}/icon.png`).then(setFallbackSrc);
  }, [resolvedState, skin]);

  useEffect(() => {
    if (!speech) {
      return;
    }
    const timeout = window.setTimeout(() => setSpeech(""), 5000);
    return () => window.clearTimeout(timeout);
  }, [setSpeech, speech]);

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    if (e.button !== 0) return;
    dragging.current = true;
    kiboApi().pet.dragStart(e.screenX, e.screenY);

    const onMove = (ev: MouseEvent) => {
      if (dragging.current) kiboApi().pet.dragMove(ev.screenX, ev.screenY);
    };
    const onUp = () => {
      dragging.current = false;
      kiboApi().pet.dragEnd();
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  }, []);

  return (
    <main
      className="grid min-h-screen select-none place-items-center overflow-hidden bg-transparent"
      onMouseEnter={() => void kiboApi().pet.setClickThrough(false)}
      onMouseLeave={() => void kiboApi().pet.setClickThrough(true)}
    >
      {speech ? <SpeechBubble text={speech} /> : null}
      {src && !videoFailed ? (
        <div
          className="h-44 w-44 cursor-grab active:cursor-grabbing"
          onMouseDown={handleMouseDown}
        >
          <video
            className="h-full w-full object-contain drop-shadow-2xl"
            style={{ pointerEvents: "none" }}
            src={src}
            autoPlay
            loop
            muted
            playsInline
            onError={() => setVideoFailed(true)}
          />
        </div>
      ) : fallbackSrc ? (
        <div
          className="h-32 w-32 cursor-grab active:cursor-grabbing"
          onMouseDown={handleMouseDown}
        >
          <img
            className="h-full w-full object-contain drop-shadow-2xl"
            style={{ pointerEvents: "none" }}
            src={fallbackSrc}
            alt="KIBO"
          />
        </div>
      ) : null}
    </main>
  );
}
