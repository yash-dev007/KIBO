import { useEffect, useMemo, useState } from "react";
import {
  Bell,
  Brain,
  Check,
  Database,
  Download,
  Mic,
  Palette,
  Save,
  Settings,
  Shield,
  Trash2,
} from "lucide-react";
import { publishSettingsState } from "@/hooks/useWindowStateSync";
import { apiGet, apiPost } from "@/lib/kiboApi";
import { useSettingsStore } from "@/stores/settingsStore";

type TabId = "general" | "voice" | "ai" | "notifications" | "appearance" | "memory" | "data";

const tabs = [
  { id: "general", label: "General", icon: Settings },
  { id: "voice", label: "Voice", icon: Mic },
  { id: "ai", label: "AI", icon: Brain },
  { id: "notifications", label: "Notifications", icon: Bell },
  { id: "appearance", label: "Appearance", icon: Palette },
  { id: "memory", label: "Memory", icon: Database },
  { id: "data", label: "Data", icon: Shield },
] satisfies Array<{ id: TabId; label: string; icon: typeof Settings }>;

function asString(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function asNumber(value: unknown, fallback: number): number {
  return typeof value === "number" ? value : fallback;
}

function asBoolean(value: unknown, fallback = false): boolean {
  return typeof value === "boolean" ? value : fallback;
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block text-sm text-kibo-text/80">
      <span>{label}</span>
      <div className="mt-2">{children}</div>
    </label>
  );
}

function TextInput({
  value,
  onChange,
}: {
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <input
      className="h-10 w-full rounded-md border border-white/10 bg-black/40 px-3 text-sm text-kibo-text outline-none focus:border-kibo-accent"
      value={value}
      onChange={(event) => onChange(event.target.value)}
    />
  );
}

function NumberInput({
  value,
  onChange,
}: {
  value: number;
  onChange: (value: number) => void;
}) {
  return (
    <input
      className="h-10 w-full rounded-md border border-white/10 bg-black/40 px-3 text-sm text-kibo-text outline-none focus:border-kibo-accent"
      type="number"
      value={value}
      onChange={(event) => onChange(Number(event.target.value))}
    />
  );
}

function Toggle({
  checked,
  onChange,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <button
      className={`h-6 w-11 rounded-full p-1 transition ${checked ? "bg-kibo-accent" : "bg-white/20"}`}
      type="button"
      aria-pressed={checked}
      onClick={() => onChange(!checked)}
    >
      <span
        className={`block h-4 w-4 rounded-full bg-black transition ${checked ? "translate-x-5" : ""}`}
      />
    </button>
  );
}

export function SettingsWindow() {
  const [activeTab, setActiveTab] = useState<TabId>("general");
  const [saved, setSaved] = useState(false);
  const skin = useSettingsStore((state) => state.skin);
  const settings = useSettingsStore((state) => state.settings);
  const setSettings = useSettingsStore((state) => state.setSettings);
  const updateSetting = useSettingsStore((state) => state.updateSetting);

  useEffect(() => {
    apiGet<Record<string, unknown>>("/settings", {}).then(setSettings);
  }, [setSettings]);

  const notificationTypes = useMemo(
    () =>
      typeof settings.notification_types === "object" && settings.notification_types
        ? (settings.notification_types as Record<string, boolean>)
        : {},
    [settings.notification_types],
  );

  function updateNotification(key: string, value: boolean) {
    updateSetting("notification_types", { ...notificationTypes, [key]: value });
  }

  async function save() {
    await apiPost("/settings", settings, { ok: true });
    setSaved(true);
    window.setTimeout(() => setSaved(false), 1500);
  }

  const content = {
    general: (
      <>
        <Field label="Pet name">
          <TextInput
            value={asString(settings.pet_name, "KIBO")}
            onChange={(value) => updateSetting("pet_name", value)}
          />
        </Field>
        <Field label="Activation hotkey">
          <TextInput
            value={asString(settings.activation_hotkey, "ctrl+k")}
            onChange={(value) => updateSetting("activation_hotkey", value)}
          />
        </Field>
        <Field label="AI enabled">
          <Toggle
            checked={asBoolean(settings.ai_enabled, true)}
            onChange={(value) => updateSetting("ai_enabled", value)}
          />
        </Field>
      </>
    ),
    voice: (
      <>
        <Field label="TTS provider">
          <TextInput
            value={asString(settings.tts_provider, "mock")}
            onChange={(value) => updateSetting("tts_provider", value)}
          />
        </Field>
        <Field label="TTS rate">
          <NumberInput
            value={asNumber(settings.tts_rate, 175)}
            onChange={(value) => updateSetting("tts_rate", value)}
          />
        </Field>
        <Field label="Voice warmup">
          <Toggle
            checked={asBoolean(settings.voice_warmup_on_launch, true)}
            onChange={(value) => updateSetting("voice_warmup_on_launch", value)}
          />
        </Field>
      </>
    ),
    ai: (
      <>
        <Field label="LLM provider">
          <TextInput
            value={asString(settings.llm_provider, "mock")}
            onChange={(value) => updateSetting("llm_provider", value)}
          />
        </Field>
        <Field label="Ollama model">
          <TextInput
            value={asString(settings.ollama_model, "llama3.2:3b")}
            onChange={(value) => updateSetting("ollama_model", value)}
          />
        </Field>
        <Field label="Groq model">
          <TextInput
            value={asString(settings.groq_model, "llama-3.3-70b-versatile")}
            onChange={(value) => updateSetting("groq_model", value)}
          />
        </Field>
      </>
    ),
    notifications: (
      <>
        <Field label="Proactive mode">
          <Toggle
            checked={asBoolean(settings.proactive_enabled, false)}
            onChange={(value) => updateSetting("proactive_enabled", value)}
          />
        </Field>
        <div className="grid gap-3 sm:grid-cols-2">
          {Object.entries(notificationTypes).map(([key, value]) => (
            <div key={key} className="flex items-center justify-between rounded-md bg-white/5 px-3 py-2">
              <span className="text-sm capitalize">{key.replaceAll("-", " ")}</span>
              <Toggle checked={value} onChange={(next) => updateNotification(key, next)} />
            </div>
          ))}
        </div>
      </>
    ),
    appearance: (
      <>
        <Field label="Skin">
          <select
            className="h-10 w-full rounded-md border border-white/10 bg-black/40 px-3 text-sm"
            value={skin}
            onChange={(event) => {
              updateSetting("buddy_skin", event.target.value);
              publishSettingsState({ skin: event.target.value });
            }}
          >
            <option value="skales">Skales</option>
            <option value="bubbles">Bubbles</option>
            <option value="capy">Capy</option>
          </select>
        </Field>
        <Field label="Speech bubbles">
          <Toggle
            checked={asBoolean(settings.enable_speech_bubbles, true)}
            onChange={(value) => updateSetting("enable_speech_bubbles", value)}
          />
        </Field>
        <Field label="Bubble timeout ms">
          <NumberInput
            value={asNumber(settings.speech_bubble_timeout_ms, 5000)}
            onChange={(value) => updateSetting("speech_bubble_timeout_ms", value)}
          />
        </Field>
      </>
    ),
    memory: (
      <>
        <Field label="Memory enabled">
          <Toggle
            checked={asBoolean(settings.memory_enabled, true)}
            onChange={(value) => updateSetting("memory_enabled", value)}
          />
        </Field>
        <Field label="Memory provider">
          <TextInput
            value={asString(settings.memory_provider, "mock")}
            onChange={(value) => updateSetting("memory_provider", value)}
          />
        </Field>
        <Field label="Maximum facts">
          <NumberInput
            value={asNumber(settings.memory_max_facts, 200)}
            onChange={(value) => updateSetting("memory_max_facts", value)}
          />
        </Field>
      </>
    ),
    data: (
      <div className="flex flex-wrap gap-2">
        <button className="inline-flex h-10 items-center gap-2 rounded-md border border-white/10 px-3 text-sm hover:bg-white/10" type="button">
          <Download size={16} />
          Export
        </button>
        <button className="inline-flex h-10 items-center gap-2 rounded-md border border-red-400/30 px-3 text-sm text-red-100 hover:bg-red-950/40" type="button">
          <Trash2 size={16} />
          Clear data
        </button>
      </div>
    ),
  } satisfies Record<TabId, React.ReactNode>;

  return (
    <main className="grid min-h-screen grid-cols-[220px_1fr] bg-kibo-bg text-kibo-text">
      <aside className="border-r border-white/10 p-3">
        <h1 className="px-2 py-3 text-base font-semibold">Settings</h1>
        <nav className="space-y-1">
          {tabs.map(({ id, label, icon: Icon }) => (
            <button
              key={label}
              className={`flex w-full items-center gap-2 rounded-md px-2 py-2 text-left text-sm hover:bg-white/10 ${
                activeTab === id ? "bg-white/10 text-kibo-accent" : ""
              }`}
              type="button"
              onClick={() => setActiveTab(id)}
            >
              <Icon size={16} />
              {label}
            </button>
          ))}
        </nav>
      </aside>
      <section className="flex min-w-0 flex-col">
        <header className="flex items-center justify-between border-b border-white/10 px-6 py-4">
          <h2 className="text-lg font-semibold">{tabs.find((tab) => tab.id === activeTab)?.label}</h2>
          <button
            className="inline-flex h-9 items-center gap-2 rounded-md bg-kibo-accent px-3 text-sm text-black hover:brightness-110"
            type="button"
            onClick={save}
          >
            {saved ? <Check size={16} /> : <Save size={16} />}
            {saved ? "Saved" : "Save"}
          </button>
        </header>
        <div className="grid max-w-3xl gap-5 p-6">{content[activeTab]}</div>
      </section>
    </main>
  );
}
