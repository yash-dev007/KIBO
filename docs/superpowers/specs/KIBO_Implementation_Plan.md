# KIBO Implementation Plan

Source analyzed: `docs/superpowers/specs/KIBO_Build_Path.md`
Repo baseline checked: 2026-04-29
Test baseline: `pytest tests/ -q` -> full suite passing in current repo

This plan turns the build-path manifesto into an execution sequence from current v5 code to a product-grade release. It is intentionally ordered around trust, retention, and coherence, not around adding the most features.

---

## 0. Current Reality

KIBO is past the "can this work?" stage. The desktop pet, animation engine, voice loop, streaming LLM/TTS pipeline, vector memory, clip capture, settings shell, tray integration, and provider abstractions exist. The next work is product hardening: proactivity, user control, personality consistency, reliability surfaces, demo reproducibility, and distribution.

Important repo observations:

- `src/system/proactive_engine.py`, `src/system/proactive_policy.py`, and `src/system/notification_router.py` now provide guarded proactivity with persisted state, daily cap, quiet hours, cooldowns, snooze, disable controls, and tests. Explicit reminder creation remains future work.
- `src/ui/settings_window.py` now includes Memory, Data, Voice, notification/proactivity controls, provider status refresh, reset controls, and diagnostics export. Full data lifecycle and richer diagnostics UI remain future work.
- Memory browsing, editing, deleting individual facts, opening the vault, and rebuilding the index are implemented. Confidence/source review remains future work.
- `src/ai/memory_store.py` already writes Obsidian-compatible Markdown memories and maintains a provider index. This is a strong foundation; the missing product layer is in-app transparency.
- `main.py` already has a `QLockFile` single-instance lock, so the build-path item "single-instance lock file" is done even though the document lists it as a gap.
- Public defaults are now opt-in for proactivity in `DEFAULT_CONFIG`; first-run onboarding/settings can enable it explicitly.
- README, build-path, and privacy framing should still receive a final release pass before distribution.
- `docs/CREATE_CHARACTER.md` claims PNG fallback and uses some `actions/` paths, while `src/ui/animation_engine.py` is WebM-only and `Brain` resolves `action/` paths. The asset docs and runtime need to be reconciled before inviting custom skins.
- `VoiceListener` defaults to offline-safe RMS VAD; `silero_local` is explicit. Voice warm-up and test voice controls are wired.
- `HotkeyThread` tracks its own hooks and supports live rebind from Settings changes.
- `TaskRunner` exists and can run background LLM tasks against Ollama. It needs a product/safety boundary before any launch messaging suggests "agentic" behavior.
- Google Calendar stores OAuth token material under `~/.kibo`. Users need a visible connect/disconnect/revoke surface, not just file placement.

Execution principle: ship each phase as a visible, testable product increment. Do not bundle proactivity, memory UI, settings polish, telemetry, and installer work into one release.

---

## Phase 0 - Product Contract and Baseline Alignment

Goal: freeze the rules KIBO must obey before adding agency.

Why first: proactivity and memory are trust-sensitive. Without a character contract, safety contract, and config contract, later features will drift.

Scope:

- Write `docs/superpowers/specs/KIBO_Personality_Contract.md`.
- Define tone, humor, emotional limits, idle behavior, criticism/compliment behavior, memory behavior, and prohibited claims.
- Add a short safety section: no romantic attachment claims, no therapist impersonation, no sexual content, self-harm escalation behavior, and "KIBO is software" reminders.
- Decide the public privacy sentence: "cloud-fast, locally capable" unless cloud features are disabled by default.
- Reconcile docs:
  - update test count to 85,
  - clarify Groq is cloud when configured,
  - clarify proactive behavior is opt-in or default-on,
  - align build-path status with actual code.
- Define launch defaults:
  - recommended: `proactive_enabled: false` for first public release, with explicit first-run opt-in,
  - memory enabled can stay on only if memory inspection/deletion is shipped.

Implementation tasks:

- Create the personality contract doc.
- Add `personality_version` and `safety_version` to config defaults.
- Move prompt assembly out of `AIClient.send_query()` into a `PromptBuilder` module.
- Inject the personality contract summary into every system prompt.
- Add prompt snapshot tests so personality rules do not silently disappear.

Acceptance criteria:

- A reviewer can understand KIBO's character without reading code.
- System prompt generation is deterministic under test.
- The docs no longer contradict the code on privacy, tests, and completion status.
- All tests pass.

Recommended files:

- `docs/superpowers/specs/KIBO_Personality_Contract.md`
- `src/ai/prompt_builder.py`
- `src/core/config_manager.py`
- `src/ai/ai_client.py`
- `tests/test_prompt_builder.py`
- `README.md`
- `docs/superpowers/specs/KIBO_Build_Path.md`

---

## Phase 0.5 - First-Run Onboarding and Consent

Goal: make the first launch understandable, honest, and recoverable.

Why this was missing: the previous plan jumped from contract to proactivity. A stranger will hit setup friction first: API key, Ollama, Piper voice, microphone, hotkeys, memory consent, and calendar permissions. If that is confusing, they never reach the anchor moment.

First-run flow:

1. Welcome screen:
  - one sentence about what KIBO is,
  - one sentence about what it can remember,
  - one sentence about cloud/local provider choice.
2. Provider choice:
  - Groq cloud-fast,
  - Ollama local-capable,
  - demo/mock mode.
3. Voice setup:
  - microphone test,
  - speaker/TTS test,
  - Piper model detection/download instructions,
  - pyttsx3 fallback clearly shown.
4. Consent:
  - memory on/off,
  - proactivity off by default with a clear opt-in,
  - calendar disconnected by default,
  - local metrics off by default.
5. Hotkeys:
  - show current talk and clip hotkeys,
  - detect registration failure,
  - allow rebind or require restart explicitly.
6. Finish:
  - launch pet,
  - open Settings shortcut,
  - provide "Run demo mode" option.

Implementation tasks:

- Add `first_run_completed` and `onboarding_version` to config.
- Create an `OnboardingWindow` or first-run page inside Settings.
- Add provider health probes that do not require sending user content.
- Add microphone and speaker test buttons.
- Add explicit local data path display: `~/.kibo`.
- Add "Open data folder" and "Reset onboarding" actions.
- Add live hotkey rebind support or mark hotkey changes as restart-required in UI.

Acceptance criteria:

- A clean machine can launch KIBO without editing `config.json`.
- User understands when Groq is used and when Ollama/local mode is used.
- User can complete setup with no API key by choosing demo/mock or Ollama guidance.
- Memory, proactivity, calendar, and metrics are explicit choices.
- Failed microphone, TTS, and hotkey setup produce visible recovery steps.

Recommended files:

- `src/ui/onboarding_window.py`
- `src/ui/settings_window.py`
- `src/system/provider_health.py`
- `src/system/hotkey_listener.py`
- `src/core/config_manager.py`
- `main.py`
- `tests/test_provider_health.py`
- `tests/test_config.py`

---

## Phase 1 - Proactivity Engine v1: Rare, Useful, Interruptible

Goal: make KIBO initiate only when it has earned the right.

Why now: the build path identifies Phase 5 proactivity as the next product boundary. It is also the easiest place to damage trust, so it needs architecture before more triggers.

Core product rule:

- Maximum 4 proactive utterances per calendar day.
- Minimum 45 minutes between proactive utterances unless the user explicitly set a reminder.
- Quiet hours are absolute for all non-explicit reminders.
- Every proactive category is disableable.
- Snooze/disable is reachable within two clicks.
- Proactivity should feel like KIBO, not a desktop notification feed.

Architecture changes:

- Replace loose rule emission with structured decisions:
  - `ProactiveEvent`: raw trigger candidate, such as battery, morning, idle, reminder.
  - `ProactiveDecision`: approved/blocked plus reason.
  - `ProactiveUtterance`: final user-facing text, category, priority, expiry, and delivery mode.
- Give `ProactiveEngine` an injectable clock for deterministic tests.
- Give `NotificationRouter` a proper persisted state model:
  - daily utterance count,
  - last utterance timestamp,
  - per-rule last fired date,
  - snoozed-until timestamp,
  - disabled categories,
  - last interaction timestamp.
- Add a `ProactivePolicy` layer so rules and delivery policy are separate.
- Convert current task-like messages into character-consistent phrasing.
- Add a route from approved proactive messages to:
  - speech bubble always,
  - TTS only if proactive voice is enabled,
  - chat transcript optionally, marked as "KIBO".

Trigger set for v1:

- Morning greeting:
  - fires once per day,
  - earliest 08:00 local time,
  - only after app has been open at least 2 minutes,
  - only if the user is active or recently active.
- Idle check-in:
  - fires after 60 minutes with no KIBO interaction,
  - requires recent mouse/keyboard activity so it does not talk to an empty desk,
  - max once per day until user interacts again.
- End-of-day acknowledgement:
  - optional,
  - fires once between 17:00 and 20:00,
  - only if KIBO had at least one meaningful interaction that day.
- Battery reaction:
  - fires below threshold only once per discharge window,
  - never repeats every poll cycle.
- CPU stress reaction:
  - visual state can happen often,
  - speech should be rare, with a long cooldown.
- Explicit reminders:
  - only reminders created by the user may bypass normal daily cap,
  - still respect quiet hours unless the reminder was explicitly marked urgent.

UI controls:

- Add `Snooze 1 hour` action in the pet context menu and tray menu.
- Add `Disable Proactivity` action in the same menu path.
- In Settings -> Notifications, group categories by plain names:
  - Daily greeting,
  - Idle check-in,
  - End-of-day note,
  - Battery,
  - CPU stress,
  - Calendar/reminders.
- Show current quiet hours and daily cap.

Tests:

- Proactive rule tests with fixed clock.
- Quiet-hours wraparound tests.
- Daily cap tests.
- Once-per-day greeting tests.
- Snooze tests.
- Disabled category tests.
- Battery threshold repeat-suppression tests.
- Main signal wiring smoke test if feasible.

Acceptance criteria:

- In a simulated day, KIBO never emits more than 4 proactive utterances.
- A morning greeting can happen once and only after 08:00 local time.
- Quiet hours block non-explicit proactive events completely.
- Snooze prevents all proactive output until it expires.
- The user can disable proactivity from the pet UI within two clicks.
- Proactive output can be tested without waiting for real time.

Recommended files:

- `src/system/proactive_engine.py`
- `src/system/notification_router.py`
- `src/system/activity_tracker.py`
- `src/ui/ui_manager.py`
- `src/ui/tray_manager.py`
- `src/ui/settings_window.py`
- `src/core/config_manager.py`
- `main.py`
- `tests/test_proactive_engine.py`
- `tests/test_notification_router.py`

---

## Phase 2 - Memory Transparency UI

Goal: make memory inspectable, editable, and deleteable from inside KIBO.

Why now: the build path is correct that memory without transparency becomes a trust problem. The current Obsidian vault is useful, but most users will not open `~/.kibo/vault`.

Memory product model:

- Memories are facts, not logs.
- Every fact needs:
  - id,
  - content,
  - category,
  - keywords,
  - extracted date,
  - source session/date,
  - provider index status.
- User actions:
  - list,
  - search,
  - filter by category,
  - edit content/category/keywords,
  - delete one,
  - delete all,
  - open vault folder,
  - rebuild index.

Implementation tasks:

- Add public APIs to `MemoryStore`:
  - `list_facts() -> list[dict]`,
  - `update_fact(fact_id, changes)`,
  - `delete_fact(fact_id)`,
  - `rebuild_index()`,
  - `get_vault_path()`.
- Ensure edits update both Markdown files and retrieval provider index.
- Add a Memory tab to settings or create a dedicated `MemoryWindow`.
- Use a table/list with category chips, content preview, search box, and edit/delete actions.
- Add confirmation only for destructive bulk actions, not for single edit saves.
- Add an "Open Vault" button using platform-safe file opening.
- Show "No memories yet" empty state.

Tests:

- Listing returns all Markdown memories.
- Updating a memory changes disk content and provider retrieval result.
- Deleting a memory removes disk file and provider index row.
- Rebuild index repopulates from Markdown.
- Memory cap eviction still deletes provider rows.

Acceptance criteria:

- A user can inspect every stored memory without leaving KIBO.
- A user can edit a wrong memory and retrieval uses the edited value.
- A user can delete a single memory and KIBO cannot retrieve it afterward.
- Clear-all still works.
- The Obsidian vault remains compatible.

Recommended files:

- `src/ai/memory_store.py`
- `src/ai/memory_providers/base.py`
- `src/ai/memory_providers/vector_provider.py`
- `src/ai/memory_providers/lexical_provider.py`
- `src/ui/settings_window.py`
- `tests/test_memory_store.py`
- `tests/test_vector_memory.py`

---

## Phase 3 - Personality and Memory Coherence

Goal: make KIBO sound like the same character across long sessions and across days.

Why after transparency: once users can see memory, KIBO can safely lean on continuity. Before that, stronger memory recall can feel invasive.

Implementation tasks:

- Build `PromptBuilder` fully:
  - base personality contract,
  - safety boundaries,
  - current user message,
  - recent conversation history,
  - retrieved memories,
  - current pet/system state if relevant.
- Add a memory recall format that nudges humility:
  - "You may use these remembered facts only if relevant."
  - "Do not claim certainty beyond the memory text."
  - "If uncertain, ask instead of asserting."
- Add internal memory metadata to prompts, but keep user-facing replies natural.
- Add optional recall citation in debug mode or memory UI, not in normal speech unless the user asks "why do you know that?"
- Add a small personality regression suite:
  - greeting,
  - refusal,
  - memory recall,
  - emotional content,
  - criticism,
  - long-context session.
- Decide whether personality presets are pre-launch or post-launch:
  - recommended: post-launch unless early testers reject the default.

Safety tasks:

- Add a lightweight response guard for self-harm signals before or after LLM response.
- Add tests for prohibited phrases and boundary behavior.
- Avoid pretending to be a human, therapist, partner, or sentient being.

Acceptance criteria:

- KIBO's system prompt is assembled from explicit, test-covered components.
- Long-context behavior keeps tone stable.
- Memory recall does not introduce unsupported claims.
- Safety rules are present in docs and enforced in prompt/tests.

Recommended files:

- `src/ai/prompt_builder.py`
- `src/ai/ai_client.py`
- `src/ai/safety.py`
- `docs/superpowers/specs/KIBO_Personality_Contract.md`
- `tests/test_prompt_builder.py`
- `tests/test_safety.py`

---

## Phase 4 - Settings, Controls, and Error Surfaces

Goal: make all user-facing surfaces feel shippable to a stranger.

Why now: after proactivity and memory UI, settings become the trust control center. It cannot feel bolted on.

Implementation tasks:

- Redesign Settings into stable sections:
  - General,
  - Voice,
  - AI providers,
  - Memory,
  - Proactivity,
  - Appearance,
  - Diagnostics.
- Add Settings to the tray menu. The pet context menu already exposes it; tray should too.
- Add reset-to-defaults with scoped reset:
  - current tab only,
  - all settings.
- Add config validation errors shown in UI, not just logs.
- Add visible provider status:
  - Groq available/missing,
  - Ollama available/unavailable,
  - Piper model found/missing,
  - memory provider vector/lexical,
  - calendar auth status.
- Add error states:
  - no LLM provider,
  - TTS failed,
  - microphone unavailable,
  - memory index unavailable,
  - calendar credentials missing,
  - clip encoding failed.
- Normalize theme and typography between chat, settings, speech bubble, about dialog, context menu, and tray labels.
- Fix text encoding/mojibake in visible strings and docs where present.

Tests:

- Config validation for new keys.
- Settings save/load preserves all keys.
- Reset-to-defaults restores only intended keys.
- Provider status functions are testable without network.

Acceptance criteria:

- Every major failure has a visible, understandable UI response.
- Settings changes persist across restarts.
- Reset-to-defaults works.
- Tray menu gives access to Chat, Settings, Snooze/Disable Proactivity, Reset Position, About, and Quit.
- No visible surface looks like a different app.

Recommended files:

- `src/ui/settings_window.py`
- `src/ui/tray_manager.py`
- `src/ui/ui_manager.py`
- `src/ui/chat_window.py`
- `src/core/config_manager.py`
- `main.py`
- `tests/test_config.py`

---

## Phase 4.5 - Voice, Hotkey, and Device Reliability

Goal: make voice interaction predictable on normal user machines.

Why this matters: the latency demo only works if input, transcription, TTS, and cancellation are reliable. The current code has strong building blocks, but device and hotkey failures are still mostly treated as logs/errors rather than setup states.

Voice input tasks:

- Add device selection for microphone input.
- Add a microphone level meter/test during onboarding and Settings.
- Add a "no speech detected" retry state that does not feel like an app failure.
- Preload or warm the Whisper model after first launch when AI is enabled, with visible "voice warming up" state if needed.
- Decide how silero-vad is installed:
  - recommended: do not call `torch.hub` in normal runtime without clear user consent,
  - support an explicit `stt_vad_provider` config: `off`, `rms`, `silero_local`.
- Add offline-safe VAD behavior for demo mode.

TTS tasks:

- Add output-device health check.
- Add "test voice" button.
- Add clear status for Piper model missing vs Piper package missing vs audio output failure.
- Add voice-download guidance or downloader in onboarding.
- Add barge-in support:
  - pressing push-to-talk while KIBO is speaking should stop current TTS,
  - cancel queued TTS chunks,
  - move state to LISTENING.
- Ensure `TTSThread.stop()` stops any active provider stream before quitting.

Hotkey tasks:

- Detect global hotkey registration failure.
- Show conflict/failure in Settings.
- Add live rebind support or enforce restart-required state correctly.
- Avoid `keyboard.unhook_all()` removing unrelated hooks from other code if possible; track registered hotkeys and remove only KIBO's hooks.

Tests:

- TTS queue cancellation tests.
- Hotkey config validation tests.
- Provider health tests for missing Piper files.
- Voice listener tests for RMS endpoint behavior with synthetic audio.
- No-network test for demo/offline mode.

Acceptance criteria:

- Push-to-talk can interrupt speech.
- Missing mic, missing output device, missing Piper voice, and hotkey failure have clear UI states.
- Demo mode never attempts a network fetch for VAD/model setup.
- Hotkey changes either work live or are honestly marked as restart-required.

Recommended files:

- `src/ai/voice_listener.py`
- `src/ai/tts_manager.py`
- `src/ai/tts_providers/piper_provider.py`
- `src/system/hotkey_listener.py`
- `src/system/provider_health.py`
- `src/ui/settings_window.py`
- `src/ui/onboarding_window.py`
- `main.py`
- `tests/test_tts_manager.py`
- `tests/test_provider_health.py`

---

## Phase 5 - Engineering Credibility and Demo Resilience

Goal: make KIBO robust enough that demos and reviewer machines do not depend on perfect external conditions.

Implementation tasks:

- Add a mock LLM provider:
  - deterministic streaming chunks,
  - deterministic memory tool calls,
  - configurable latency,
  - no network.
- Add mock TTS or text-only demo mode.
- Add "demo mode" config:
  - seeded memory,
  - known script responses,
  - proactivity timers shortened only under demo mode,
  - visible demo watermark disabled by default for normal users.
- Add diagnostics export:
  - app version,
  - OS,
  - Python version,
  - config with secrets redacted,
  - provider availability,
  - recent logs,
  - memory provider status.
- Add logging rotation in `~/.kibo/logs`.
- Add a tray action: "Open Diagnostics Folder" or "Copy Diagnostics".
- Verify single-instance lock behavior and document it as complete.
- Add graceful degradation:
  - network down -> local provider or mock/demo provider,
  - TTS unavailable -> text bubble only,
  - memory provider unavailable -> lexical fallback,
  - calendar unavailable -> no proactive meeting rule.

Tests:

- Mock provider streams in order.
- Demo mode produces expected anchor moment.
- Diagnostics redacts secrets.
- Log rotation creates bounded files.
- Provider fallback selection is deterministic.

Acceptance criteria:

- A 60-second demo can run without Groq, Ollama, Google Calendar, or microphone.
- Diagnostics can explain most user failures without asking the user to inspect code.
- Senior reviewer can identify clear module boundaries within five minutes.

Recommended files:

- `src/ai/llm_providers/mock_provider.py`
- `src/ai/llm_providers/__init__.py`
- `src/ai/tts_providers/mock_provider.py`
- `src/system/diagnostics.py`
- `src/core/config_manager.py`
- `src/ui/tray_manager.py`
- `main.py`
- `tests/test_ai_client.py`
- `tests/test_diagnostics.py`

---

## Phase 5.5 - Data Lifecycle, Privacy, and Security

Goal: make local data boringly controllable and cloud boundaries obvious.

Why this was missing: memory transparency handles individual facts, but users also need whole-app data lifecycle controls: export, import, reset, backup, credentials, logs, and OAuth revocation.

Local data inventory:

- `~/.kibo/vault/memories/*.md`
- `~/.kibo/memories.db`
- `~/.kibo/proactive_state.json`
- `~/.kibo/tasks.json`
- `~/.kibo/cost_state.json`
- `~/.kibo/clips/`
- `~/.kibo/google_token.json`
- future logs and metrics files

Implementation tasks:

- Add a Data tab or Diagnostics section with:
  - open data folder,
  - export all user data,
  - import/restore data,
  - delete memories only,
  - delete clips only,
  - reset proactive state,
  - reset all local KIBO data.
- Add config versioning and migrations earlier than packaging:
  - `config_version`,
  - migration registry,
  - backup old config before migration,
  - migration tests.
- Add data export format:
  - zip with memories, config, proactive state, task state, clips optionally,
  - manifest with version and timestamps,
  - secrets excluded by default.
- Add OAuth/calendar controls:
  - connect,
  - disconnect,
  - delete token,
  - show scopes requested.
- Add diagnostics redaction rules:
  - API keys,
  - tokens,
  - raw prompts,
  - transcripts,
  - memory contents unless user explicitly includes them.
- Add log retention policy:
  - rotate logs,
  - cap size,
  - never log raw audio or full conversation by default.
- Add dependency/security notes:
  - avoid runtime network downloads without consent,
  - document cloud requests,
  - pin/lock dependency versions for release builds.

Acceptance criteria:

- User can export and delete all local KIBO data from the UI.
- Calendar tokens can be deleted without manually browsing files.
- Diagnostics never include secrets or raw user content by default.
- Config migrations are tested and reversible via backup.
- Runtime network behavior is documented and opt-in where possible.

Recommended files:

- `src/system/data_lifecycle.py`
- `src/system/diagnostics.py`
- `src/core/migrations.py`
- `src/core/config_manager.py`
- `src/ui/settings_window.py`
- `src/system/calendar_manager.py`
- `tests/test_data_lifecycle.py`
- `tests/test_migrations.py`
- `tests/test_diagnostics.py`

---

## Phase 5.6 - Background Task Safety Boundary

Goal: prevent the background task system from blurring into unsafe "agent" behavior.

Why this matters: `TaskRunner` already exists and can process queued tasks through an LLM. Even if it currently only asks Ollama for text, the product should define its boundary before adding reminders, task automation, or plugins.

Product boundary:

- KIBO may help track or summarize tasks.
- KIBO must not perform destructive actions without explicit user approval.
- KIBO must not claim a task is done unless the result is inspectable.
- KIBO must not create background tasks from casual conversation unless the user explicitly asks.
- Background task state must be visible and cancellable.

Implementation tasks:

- Add a Tasks UI:
  - pending,
  - blocked,
  - in progress,
  - completed,
  - failed/cancelled.
- Add global task enable/disable setting.
- Add per-task approval prompt before execution when source is proactive or inferred.
- Add rate limit controls to config and UI.
- Add task result review before KIBO summarizes it proactively.
- Route `TaskRunner.status_update`, `task_failed`, and `task_blocked` to visible UI states.
- Do not wire task creation into the LLM prompt until the safety contract and UI are complete.
- Add deterministic fake task execution for tests/demo.

Tests:

- Tasks cannot start when disabled.
- Approval-required tasks stay blocked until approved.
- Cancelled tasks do not execute.
- Rate limit state is persisted and visible.
- Failed tasks surface a user-visible status.

Acceptance criteria:

- User can see and cancel every background task.
- No background task starts from ambiguous conversation.
- Proactivity can mention task state only after the task system is visible and enabled.
- TaskRunner errors do not silently disappear into logs.

Recommended files:

- `src/system/task_runner.py`
- `src/ui/task_window.py`
- `src/ui/chat_window.py`
- `src/ui/settings_window.py`
- `src/system/proactive_engine.py`
- `main.py`
- `tests/test_task_runner.py`
- `tests/test_task_window.py`

---

## Phase 6 - Anchor Moment and Demo Script

Goal: create one repeatable moment people remember.

Recommended anchor moment:

KIBO remembers a detail from earlier, starts speaking before text finishes, then later makes one restrained proactive comment after a staged idle period. This exercises the three strongest differentiators: latency, memory, and agency.

Implementation tasks:

- Build a `demo_seed.py` script:
  - inserts one memory,
  - sets demo mode,
  - shortens idle check-in delay under demo mode only,
  - resets proactive state.
- Add demo script docs:
  - exact prompt,
  - expected state changes,
  - expected line from KIBO,
  - clip capture timing.
- Add a "recordable" launch path that hides debug windows and normalizes position.
- Ensure Clip Mode captures the relevant 5 seconds reliably.

Demo flow:

1. Launch KIBO and show idle motion for 4 seconds.
2. Ask by voice: "Do you remember what drink I like while coding?"
3. KIBO enters LISTENING, then THINKING, then starts voice before the text completes.
4. KIBO casually recalls the seeded memory.
5. Wait for shortened demo idle trigger.
6. KIBO offers one brief proactive line.
7. Press clip hotkey and open the generated WebP.

Acceptance criteria:

- Demo completes in under 90 seconds.
- No network is required in mock mode.
- The clip shows visual state, speech bubble, and continuity.
- The anchor moment needs no narration.

Recommended files:

- `scripts/demo_seed.py`
- `docs/demo_script.md`
- `src/system/proactive_engine.py`
- `src/ui/clip_recorder.py`
- `config.json.example`

---

## Phase 6.5 - Test Matrix and Performance Budgets

Goal: protect the three things that make KIBO impressive: low idle cost, low voice latency, and smooth visual presence.

Why this was missing: unit tests confirm logic, but they do not prove the pet stays lightweight, responsive, or visually alive on real machines.

Performance budgets:

- Idle CPU:
  - target <2% on a 5-year-old laptop,
  - warning threshold 4%,
  - fail threshold 6%.
- Voice latency:
  - hotkey to recording indicator <100ms,
  - end-of-speech to transcript under the chosen STT budget,
  - LLM start to first TTS chunk <200ms when using Groq + Piper.
- Memory:
  - embedding one memory <100ms after model warmup,
  - retrieval <50ms for 200 memories on vector provider.
- Clip capture:
  - passive frame capture should not visibly affect animation,
  - WebP encode should run off the UI path.
- Startup:
  - pet visible quickly,
  - heavy model/provider initialization should be lazy or visibly staged.

Test matrix:

- AI off.
- Groq cloud.
- Ollama local.
- Mock/demo provider.
- Piper available.
- Piper missing -> pyttsx3 fallback.
- Microphone missing.
- Hotkey registration failure.
- Vector memory available.
- Vector memory unavailable -> lexical fallback.
- Calendar disabled.
- Calendar credentials missing.
- Network unavailable.
- Clean `~/.kibo`.
- Existing `~/.kibo` with old config/memory data.

Implementation tasks:

- Add a smoke-test launch mode that initializes core components without opening a full interactive session.
- Add provider health tests independent of real network by using mocks.
- Add benchmark scripts:
  - idle CPU sampler,
  - memory retrieval benchmark,
  - TTS first-audio benchmark where measurable,
  - clip encode benchmark.
- Add a manual QA checklist for visual states:
  - idle,
  - listening,
  - thinking,
  - talking,
  - sleepy,
  - battery,
  - CPU stress,
  - proactive bubble.
- Add asset validation:
  - required WebM clips per skin,
  - alpha/native transparency check,
  - path convention check,
  - docs path consistency.

Acceptance criteria:

- Performance budgets are documented and measured before release.
- Every fallback mode has at least one test or manual QA step.
- Custom skin docs match the runtime resolver.
- Demo mode is covered by a repeatable smoke test.

Recommended files:

- `scripts/benchmark_idle_cpu.py`
- `scripts/benchmark_memory.py`
- `scripts/validate_assets.py`
- `docs/qa_checklist.md`
- `tests/test_provider_health.py`
- `tests/test_animation_engine.py`
- `docs/CREATE_CHARACTER.md`

---

## Phase 7 - Retention Instrumentation

Goal: measure whether KIBO earns day-two and day-seven use.

Why after demo resilience: instrumentation before trust controls can look extractive. This should be opt-in and boringly transparent.

Instrumentation model:

- Start local-only. Store events in `~/.kibo/metrics.jsonl`.
- Add cloud analytics only after a public privacy decision.
- Make telemetry opt-in during first-run or Settings.
- Never log raw conversation, transcript, or memory content.

Events to capture:

- app_started,
- app_exited,
- session_duration,
- voice_turn_completed,
- text_turn_completed,
- memory_created,
- memory_deleted,
- proactive_shown,
- proactive_snoozed,
- proactive_disabled,
- clip_saved,
- provider_fallback_used,
- error_category.

Metrics:

- day-1 return,
- day-7 return,
- day-30 return,
- average session length,
- proactive acceptance/snooze/disable rate,
- memory creation rate,
- clip save rate,
- provider failure rate.

Acceptance criteria:

- User can inspect local metrics file.
- User can disable metrics.
- No raw message text is stored.
- Metrics answer whether proactivity helps retention or causes disablement.

Recommended files:

- `src/system/metrics.py`
- `src/ui/settings_window.py`
- `main.py`
- `tests/test_metrics.py`
- `README.md`

---

## Phase 8 - Packaging and Distribution

Goal: make KIBO installable and updateable on Windows.

Implementation tasks:

- Create a PyInstaller or Nuitka packaging path.
- Bundle required assets:
  - WebM animations,
  - icons,
  - config defaults,
  - optional Piper voice instructions or downloader.
- Decide voice model distribution:
  - recommended: do not silently bundle large voice files in source; provide first-run downloader or optional asset bundle.
- Add installer:
  - Start Menu shortcut,
  - auto-start option,
  - uninstall support,
  - user data preserved in `~/.kibo`.
- Add code signing plan.
- Add auto-update plan:
  - recommend using a proven updater rather than hand-rolled update logic.
- Add crash-safe config migration:
  - config version,
  - migration functions,
  - backup old config before migration.

Acceptance criteria:

- A non-developer can install, launch, configure, quit, and uninstall KIBO.
- User data survives app updates.
- Missing optional dependencies produce guided UI states.
- Auto-update strategy is selected before public launch.

Recommended files:

- `packaging/`
- `scripts/build_windows.ps1`
- `src/core/config_manager.py`
- `src/core/migrations.py`
- `README.md`
- `docs/install.md`

---

## Phase 9 - Launch Surface

Goal: explain KIBO clearly enough that strangers understand why it deserves screen space.

Implementation tasks:

- Create one landing page:
  - one sentence: what it is,
  - two sentences: why someone uses it,
  - one short video,
  - privacy/provider explanation,
  - install link,
  - local/cloud capability table.
- Create 60-second launch video.
- Create engineering blog post:
  - VP9 alpha rendering,
  - streaming sentence-to-TTS pipeline,
  - memory architecture,
  - proactivity safety.
- Prepare Show HN post:
  - honest scope,
  - Windows-first,
  - cloud-fast/local-capable,
  - why it is not a chatbot widget.
- Prepare Product Hunt copy only after Show HN/video feedback.

Acceptance criteria:

- Viewer understands KIBO in under 10 seconds.
- Launch materials do not overclaim privacy.
- Demo video shows latency, memory, and agency in that order.
- Install path is real before launch post goes live.

Recommended files:

- `docs/launch/landing_copy.md`
- `docs/launch/show_hn.md`
- `docs/launch/video_script.md`
- `docs/engineering_blog.md`

---

## Phase 10 - Post-Launch Learning Loop

Goal: convert feedback into retention decisions, not feature sprawl.

First two weeks:

- Track install success/failure.
- Track whether users disable proactivity.
- Track memory creation and deletion patterns.
- Track session return rate.
- Interview 5-10 users who kept KIBO open for more than one day.
- Interview 5 users who uninstalled or stopped opening it.

Decision gates:

- If proactivity disable rate is high, reduce triggers before adding new ones.
- If users distrust memory, improve transparency before adding memory depth.
- If latency is praised, preserve it above all new feature work.
- If users ask for "smarter assistant" features, verify they fit the companion frame before building.
- If users mainly want custom characters, prioritize character SDK over integrations.

Acceptance criteria:

- Week-two roadmap is based on observed behavior.
- No major feature is added without linking it to retention, trust, or coherence.

---

## Phase 11 - Platform Expansion and Optional Power Features

Goal: expand only after Windows product-market signal.

Candidates:

- macOS support:
  - replace Windows-specific hotkey/window dependencies,
  - verify transparent always-on-top behavior,
  - package and sign properly.
- Linux support:
  - only if demand is real,
  - expect compositor/window-manager variance.
- Personality presets:
  - warm,
  - dry,
  - playful,
  - quiet.
- Character SDK:
  - asset validator,
  - preview tool,
  - drop-in skin folder,
  - documentation fixes for `action` vs `actions` path naming.
- Plugin architecture:
  - only if repeated user requests justify it,
  - start with read-only context providers before action plugins.

Acceptance criteria:

- Expansion work does not weaken the Windows core.
- New platforms preserve animation, hotkey, voice, memory, and proactivity quality.

---

## Recommended Execution Order

1. Phase 0 - Product contract and doc alignment.
2. Phase 0.5 - First-run onboarding and consent.
3. Phase 1 - Proactivity v1 policy, state, controls, tests.
4. Phase 2 - Memory transparency UI and editable memory APIs.
5. Phase 3 - Prompt/personality coherence and safety tests.
6. Phase 4 - Settings, controls, and visible error surfaces.
7. Phase 4.5 - Voice, hotkey, and device reliability.
8. Phase 5 - Mock/demo resilience and diagnostics.
9. Phase 5.5 - Data lifecycle, privacy, and security.
10. Phase 5.6 - Background task safety boundary.
11. Phase 6 - Anchor demo script and seeded demo mode.
12. Phase 6.5 - Test matrix and performance budgets.
13. Phase 7 - Opt-in retention instrumentation.
14. Phase 8 - Windows packaging and update plan.
15. Phase 9 - Launch materials.
16. Phase 10 - Post-launch learning loop.
17. Phase 11 - Platform expansion only after signal.

Critical path to a credible demo:

1. Personality contract.
2. First-run/demo mode path.
3. Proactivity v1 with strict caps.
4. Memory transparency UI.
5. Voice/TTS interruption and provider health.
6. Mock/demo provider.
7. Seeded anchor moment.

Critical path to public release:

1. Onboarding and consent.
2. Memory transparency.
3. Proactivity controls.
4. Voice/hotkey/device reliability.
5. Data export/delete and diagnostics.
6. Error surfaces.
7. Installer.
8. Honest privacy/docs.

---

## Phase Dependency Map

- Proactivity depends on Phase 0 because agency needs personality and safety boundaries.
- Public defaults depend on Phase 0.5 because consent should be collected before enabling memory/proactivity/calendar/metrics.
- Memory coherence depends on Phase 2 because stronger recall requires user control.
- Voice latency claims depend on Phase 4.5 and Phase 6.5 because they need device handling and measurement, not only code structure.
- Diagnostics depend on Phase 5.5 because redaction and data inventory must exist before export.
- Task-based proactivity depends on Phase 5.6 because background tasks must be visible and cancellable first.
- Retention instrumentation depends on Phase 4 because users need visible controls before metrics.
- Launch depends on Phase 8 because a video without an installer creates curiosity without adoption.
- Platform expansion depends on post-launch signal because cross-platform desktop pet behavior is expensive to polish.

---

## Non-Negotiable Quality Gates

KIBO should not launch publicly until these are true:

- `pytest tests/ -q` passes.
- Proactivity cannot exceed 4 utterances per day.
- Quiet hours are absolute for non-explicit reminders.
- User can inspect, edit, and delete memories.
- User can export and delete all local KIBO data.
- User can disable memory.
- User can disable proactivity within two clicks.
- User can revoke/delete calendar credentials.
- First-run onboarding clearly explains cloud/local behavior.
- Microphone, speaker/TTS, and hotkey failures have visible recovery paths.
- Pressing push-to-talk while KIBO speaks stops current speech and starts listening.
- No raw conversation content is captured by telemetry.
- Diagnostics redact secrets and raw user content by default.
- Cloud usage is described honestly.
- Installer works on a clean Windows machine.
- Demo can run without network in mock mode.
- Runtime model/VAD downloads do not happen without explicit user action.
- Asset docs match runtime behavior.
- Every user-visible failure has a visible explanation.

---

## First Implementation Sprint

Sprint objective: make Phase 1 proactivity safe enough to enable for testing.

Tasks:

1. Add `src/system/proactive_policy.py`.
2. Add structured state to `NotificationRouter`.
3. Add global daily cap and minimum gap.
4. Add once-per-day morning greeting logic.
5. Add snooze state and UI action.
6. Add Settings controls for proactivity categories.
7. Add fixed-clock tests for all policy decisions.
8. Keep `config.json` proactive disabled until the controls are complete.

Definition of done:

- Proactivity is deterministic under test.
- No rule can spam.
- User has visible control.
- Existing 85 tests still pass.
- New proactivity tests cover policy edge cases.

