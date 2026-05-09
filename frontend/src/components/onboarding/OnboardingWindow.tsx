import { useState } from "react";
import { Check, ChevronLeft, ChevronRight, Mic, Shield, Sparkles, Wand2, Zap } from "lucide-react";
import { apiPost } from "@/lib/kiboApi";
import { useSettingsStore } from "@/stores/settingsStore";

const steps = [
  { title: "Welcome", icon: Sparkles },
  { title: "Provider", icon: Wand2 },
  { title: "Voice", icon: Mic },
  { title: "Privacy", icon: Shield },
  { title: "Hotkeys", icon: Zap },
  { title: "Finish", icon: Check },
];

export function OnboardingWindow() {
  const [index, setIndex] = useState(0);
  const settings = useSettingsStore((state) => state.settings);
  const updateSetting = useSettingsStore((state) => state.updateSetting);
  const step = steps[index];
  const Icon = step.icon;

  function finish() {
    const nextSettings = {
      ...settings,
      first_run_completed: true,
      onboarding_version: "1.0",
    };
    void apiPost("/settings", nextSettings, { ok: true });
    window.kibo?.app.showChat();
    window.kibo?.app.hideCurrentWindow();
  }

  return (
    <main className="grid min-h-screen grid-cols-[220px_1fr] bg-kibo-bg text-kibo-text">
      <aside className="border-r border-white/10 p-4">
        <h1 className="px-2 py-3 text-base font-semibold">KIBO</h1>
        <ol className="grid gap-1">
          {steps.map(({ title, icon: StepIcon }, stepIndex) => (
            <li key={title}>
              <button
                className={`flex w-full items-center gap-2 rounded-md px-2 py-2 text-left text-sm ${
                  stepIndex === index ? "bg-white/10 text-kibo-accent" : "text-kibo-text/75"
                }`}
                type="button"
                onClick={() => setIndex(stepIndex)}
              >
                <StepIcon size={16} />
                {title}
              </button>
            </li>
          ))}
        </ol>
      </aside>
      <section className="flex min-w-0 flex-col">
        <header className="border-b border-white/10 px-8 py-6">
          <div className="flex items-center gap-3">
            <span className="grid h-10 w-10 place-items-center rounded-md bg-kibo-accent text-black">
              <Icon size={20} />
            </span>
            <h2 className="text-2xl font-semibold">{step.title}</h2>
          </div>
        </header>
        <div className="grid max-w-2xl gap-5 p-8">
          {index === 0 ? <p className="text-kibo-text/75">Set up your desktop companion.</p> : null}
          {index === 1 ? (
            <label className="block text-sm">
              LLM provider
              <select
                className="mt-2 h-10 w-full rounded-md border border-white/10 bg-black/40 px-3"
                value={String(settings.llm_provider ?? "mock")}
                onChange={(event) => updateSetting("llm_provider", event.target.value)}
              >
                <option value="mock">Mock</option>
                <option value="ollama">Ollama</option>
                <option value="groq">Groq</option>
              </select>
            </label>
          ) : null}
          {index === 2 ? (
            <label className="flex items-center justify-between rounded-md bg-white/5 px-3 py-3 text-sm">
              TTS enabled
              <input
                checked={Boolean(settings.tts_enabled ?? true)}
                type="checkbox"
                onChange={(event) => updateSetting("tts_enabled", event.target.checked)}
              />
            </label>
          ) : null}
          {index === 3 ? (
            <label className="flex items-center justify-between rounded-md bg-white/5 px-3 py-3 text-sm">
              Memory enabled
              <input
                checked={Boolean(settings.memory_enabled ?? true)}
                type="checkbox"
                onChange={(event) => updateSetting("memory_enabled", event.target.checked)}
              />
            </label>
          ) : null}
          {index === 4 ? (
            <div className="grid gap-4 sm:grid-cols-2">
              <label className="block text-sm">
                Talk
                <input
                  className="mt-2 h-10 w-full rounded-md border border-white/10 bg-black/40 px-3"
                  value={String(settings.activation_hotkey ?? "ctrl+k")}
                  onChange={(event) => updateSetting("activation_hotkey", event.target.value)}
                />
              </label>
              <label className="block text-sm">
                Clip
                <input
                  className="mt-2 h-10 w-full rounded-md border border-white/10 bg-black/40 px-3"
                  value={String(settings.clip_hotkey ?? "ctrl+alt+k")}
                  onChange={(event) => updateSetting("clip_hotkey", event.target.value)}
                />
              </label>
            </div>
          ) : null}
          {index === 5 ? <p className="text-kibo-text/75">KIBO is ready.</p> : null}
        </div>
        <footer className="mt-auto flex items-center justify-between border-t border-white/10 p-4">
          <button
            className="inline-flex h-10 items-center gap-2 rounded-md border border-white/10 px-3 text-sm disabled:opacity-40"
            type="button"
            disabled={index === 0}
            onClick={() => setIndex((current) => Math.max(0, current - 1))}
          >
            <ChevronLeft size={16} />
            Back
          </button>
          <button
            className="inline-flex h-10 items-center gap-2 rounded-md bg-kibo-accent px-3 text-sm text-black"
            type="button"
            onClick={index === steps.length - 1 ? finish : () => setIndex((current) => current + 1)}
          >
            {index === steps.length - 1 ? "Finish" : "Next"}
            {index === steps.length - 1 ? <Check size={16} /> : <ChevronRight size={16} />}
          </button>
        </footer>
      </section>
    </main>
  );
}
