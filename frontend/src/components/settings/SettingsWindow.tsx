import { useEffect, useMemo, useState } from "react";
import {
  Bell,
  Brain,
  Check,
  ChevronDown,
  Database,
  Download,
  Mic,
  Palette,
  Save,
  Settings,
  Shield,
  Trash2,
  X,
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
    <label className="block text-sm text-kibo-text">
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
      className="h-10 w-full rounded-lg border border-kibo-border bg-kibo-bg px-3 text-sm text-kibo-text outline-none transition focus:border-kibo-accent/40 focus:shadow-[0_0_0_3px_var(--color-kibo-accent-dim)]"
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
      className="h-10 w-full rounded-lg border border-kibo-border bg-kibo-bg px-3 text-sm text-kibo-text outline-none transition focus:border-kibo-accent/40 focus:shadow-[0_0_0_3px_var(--color-kibo-accent-dim)]"
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
      className={`h-6 w-11 rounded-full p-1 transition ${checked ? "bg-kibo-accent" : "bg-kibo-dim/30"}`}
      type="button"
      aria-pressed={checked}
      onClick={() => onChange(!checked)}
    >
      <span
        className={`block h-4 w-4 rounded-full bg-white shadow-sm transition ${checked ? "translate-x-5" : ""}`}
      />
    </button>
  );
}

function CustomSelect({
  value,
  options,
  onChange,
}: {
  value: string;
  options: { label: string; value: string }[];
  onChange: (value: string) => void;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const selected = options.find((o) => o.value === value) || options[0];

  const handleSelect = (val: string) => {
    setIsOpen(false);
    onChange(val);
  };

  return (
    <div className="relative">
      <button
        type="button"
        className="flex h-11 w-full items-center justify-between rounded-xl border border-kibo-border bg-kibo-bg px-4 text-sm text-kibo-text outline-none transition focus:border-kibo-accent focus:shadow-[0_0_0_3px_var(--color-kibo-accent-soft)]"
        onClick={() => setIsOpen(!isOpen)}
      >
        <span>{selected.label}</span>
        <ChevronDown
          size={16}
          className={`text-kibo-dim transition-transform ${isOpen ? "rotate-180" : ""}`}
        />
      </button>

      {isOpen && (
        <>
          <div
            className="fixed inset-0 z-40 bg-black/0"
            onClick={(e) => {
              e.stopPropagation();
              setIsOpen(false);
            }}
          />
          <div className="animate-slide-up absolute top-full z-50 mt-2 w-full overflow-hidden rounded-2xl border border-kibo-border bg-kibo-surface p-1 shadow-2xl">
            {options.map((opt) => (
              <button
                key={opt.value}
                type="button"
                className={`flex w-full items-center px-4 py-2.5 text-left text-sm transition-colors hover:bg-kibo-accent-soft ${
                  value === opt.value
                    ? "bg-kibo-accent-dim font-medium text-kibo-accent"
                    : "text-kibo-text"
                }`}
                onClick={(e) => {
                  e.stopPropagation();
                  handleSelect(opt.value);
                }}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
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
            <div key={key} className="flex items-center justify-between rounded-lg border border-kibo-border bg-kibo-surface px-3 py-2">
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
          <CustomSelect
            value={skin}
            options={[
              { label: "Skales", value: "skales" },
              { label: "Bubbles", value: "bubbles" },
              { label: "Capy", value: "capy" },
            ]}
            onChange={(value) => {
              updateSetting("buddy_skin", value);
              publishSettingsState({ skin: value });
            }}
          />
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
        <button
          className="inline-flex h-10 items-center gap-2 rounded-lg border border-kibo-border px-3 text-sm text-kibo-text transition hover:bg-kibo-accent-dim"
          type="button"
        >
          <Download size={16} />
          Export
        </button>
        <button
          className="inline-flex h-10 items-center gap-2 rounded-lg border border-red-200 px-3 text-sm text-red-600 transition hover:bg-red-50"
          type="button"
        >
          <Trash2 size={16} />
          Clear data
        </button>
      </div>
    ),
  } satisfies Record<TabId, React.ReactNode>;

  return (
    <main className="grid min-h-screen grid-cols-[220px_1fr] bg-kibo-bg text-kibo-text">
      <aside className="border-r border-kibo-border p-3">
        <h1 className="drag-region px-2 py-3 font-display text-lg italic text-kibo-text">Settings</h1>
        <nav className="space-y-1">
          {tabs.map(({ id, label, icon: Icon }) => (
            <button
              key={label}
              className={`flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-sm transition-colors hover:bg-kibo-accent-dim ${
                activeTab === id ? "bg-kibo-accent-soft text-kibo-accent" : "text-kibo-dim"
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
        <header className="drag-region flex items-center justify-between border-b border-kibo-border px-6 py-4">
          <div className="no-drag flex items-center gap-2">
            <h2 className="text-lg font-semibold">{tabs.find((tab) => tab.id === activeTab)?.label}</h2>
          </div>
          <div className="no-drag flex items-center gap-3">
            <button
              className="inline-flex h-9 items-center gap-2 rounded-full bg-kibo-accent px-4 text-sm text-white transition hover:brightness-105"
              type="button"
              onClick={save}
            >
              {saved ? <Check size={16} /> : <Save size={16} />}
              {saved ? "Saved" : "Save"}
            </button>
            <button
              className="grid h-9 w-9 place-items-center rounded-full text-kibo-dim transition-all hover:bg-kibo-surface hover:text-kibo-text"
              type="button"
              aria-label="Close"
              onClick={() => window.kibo?.app.quit()}
            >
              <X size={20} />
            </button>
          </div>
        </header>
        <div className="grid max-w-3xl gap-5 p-6">{content[activeTab]}</div>
      </section>
    </main>
  );
}
