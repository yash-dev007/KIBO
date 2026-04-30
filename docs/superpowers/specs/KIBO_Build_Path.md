# KIBO Build Path — From Vibecoded Idea to Inevitable Product

> **Editorial note (2026-04-29):** This document was originally a manifesto written before the engineering started. It has been rewritten to reflect where the project actually is at v5, to inject the perspectives the original was missing (retention, defensibility, risk, safety, distribution), and to tighten language that drifted into hollow words like *magic* and *wow*. The original phased structure is preserved; the philosophy is sharpened, not replaced.

---

## Where KIBO Stands Today (v5, April 2026)

Be honest about the starting line before redrawing the map.

**What works:**
- Frameless transparent desktop pet, draggable, always-on-top, tray-integrated.
- State machine: IDLE / LISTENING / THINKING / TALKING / SLEEPY / HAPPY with crossfaded WebM animations and PNG fallback.
- VP9 alpha animation (Qt-native pixel sampling, no software chroma-key, <2% idle CPU target).
- Push-to-talk voice round-trip via Whisper + Groq + Piper, ~1.2s end-to-end.
- Streaming pipeline: LLM tokens → sentence buffer → TTS queue, parallelized so speech starts before generation finishes.
- Vector RAG memory using sqlite-vec + fastembed (bge-small-en-v1.5), inline LLM-driven extraction.
- Provider abstraction for LLM (Groq cloud, Ollama local) and TTS (Piper neural, pyttsx3 fallback).
- Chat window with warm earthy palette, scroll throttling, streaming text.
- Clip Mode: 5-second ring buffer → animated WebP, hotkey-triggered, auto-opens folder.
- 77/77 tests passing. Single source of truth in `config.json`.

**What's incomplete:**
- Proactivity engine (Phase 5): not yet implemented.
- Personality consistency under long context: untested.
- Memory transparency UI: user cannot inspect or delete what KIBO remembers.
- macOS support: post-v5.
- Distribution: no installer, no auto-update, no website.
- Retention story: every session feels like a first session.
- Real users: zero.

KIBO has finished the **engineering layer**. The next phase is **product**: making this thing matter to someone the day after the demo.

---

## North Star

KIBO should feel like a living desktop companion that is:

- visually deliberate,
- low-latency to the point of disorienting,
- emotionally coherent across sessions,
- private by user choice (not by accident), and
- well-built enough that the question "how did you make this?" is the first reaction, not "what is this for?"

The goal is not to be the biggest app, the smartest assistant, or the most viral demo. The goal is to be the **most coherent**: a small object on the screen that consistently behaves like itself.

---

## Who This Is For

The original document never named the user. That was the central missing piece.

**Primary user:** A person who already keeps apps open all day at a desk — a developer, a writer, a researcher, a designer. Someone who has Slack, a code editor, a browser, and a music app already running, and who would tolerate one more small persistent thing if it earned its space.

**Secondary user:** People who like Tamagotchis, Replika, desktop pets, and ambient computing in general. They will be the loudest fans and the most forgiving early adopters.

**Job to be done:** "Make my screen feel less alone, occasionally useful, and never annoying." That is the load-bearing sentence. Every feature has to defend itself against it.

KIBO is **not** trying to be:
- a productivity assistant (it doesn't compete with Cursor or Raycast),
- a chatbot (it doesn't compete with ChatGPT),
- a virtual partner (it doesn't compete with Replika),
- a system monitor (Activity Monitor exists).

KIBO is trying to be the small piece of warmth on a screen that is otherwise full of work.

---

## Why This Will Be Hard to Copy

A weekend hacker can clone any single layer of KIBO. The defensibility is in the **stack of choices**, not in any one of them.

1. **Taste in character.** Personality is subjective and accumulates. The longer KIBO has a defined voice, the harder it is to fork without breaking it.
2. **Memory as switching cost.** A KIBO that has known you for six months knows things a new one does not. Users do not migrate companions casually.
3. **Streaming pipeline.** The overlap of token streaming, sentence buffering, parallel TTS, and animation state transitions is engineering that takes weeks to copy correctly. A naive clone will feel like a chatbot with a sprite.
4. **Animation polish.** VP9 alpha + state crossfades + idle micro-motion is not a tutorial; it is a system that has to be tuned by feel.
5. **Provider neutrality.** Most clones will hard-bind to one model vendor. KIBO survives vendor turnover.

None of these are unbreakable moats. Together they buy 6–18 months of distance from the median clone, which is enough.

---

## What Will Surprise Strong People

Three things, in this order:

1. **Latency.** Speech starts before the response finishes generating. This is the single most disorienting thing a casual viewer experiences and is hardest to fake.
2. **Coherence.** The character behaves the same way at minute 1 and minute 41. The animation matches the mood. The memory recalls the right thing. Nothing breaks the illusion.
3. **Polish.** Spacing, color, motion, and feedback all feel deliberate. There is no UI corner that looks unfinished.

If those three are present, the rest of the system inherits credibility.

If any one is absent, the project reads as a tech demo regardless of how clever the other parts are.

---

## Product Principle

KIBO is not a chatbot with a pet skin.

KIBO is a **character system** with presence, memory, voice, mood, and proactive behavior. That framing changes every decision:

- UI is about presence, not navigation.
- Memory is about continuity, not storage.
- AI is about personality, not accuracy.
- Motion is about emotion, not decoration.
- Latency is about aliveness, not throughput.

When a feature decision is unclear, ask: "does this make KIBO feel more like the same character, or less?" The answer is usually obvious.

---

## Strategy: Layers, Not a Monolith

Build in layers that each produce a visible result on their own. Do not wait for the full system before any layer feels complete.

The product evolves as:

1. **It exists** — runs on the desktop. ✅
2. **It reacts** — animates and changes state. ✅
3. **It listens** — captures voice. ✅
4. **It speaks** — streams reply with TTS. ✅
5. **It remembers** — recalls facts across sessions. ✅
6. **It initiates** — speaks without being asked. ☐ (Phase 5 next)
7. **It develops** — personality deepens with use. ☐
8. **It accompanies** — earns daily presence. ☐ (the real bar)

Layer 8 is the one nobody else has reached. That is where this project either becomes a product or stays a demo.

---

# Phase 0 — Define the Character

## Goal
Establish the emotional and design identity before deep engineering.

## Output
A one-page Personality Contract:
- name, tone, temperament,
- humor style,
- emotional boundaries (what KIBO will not say),
- what KIBO likes and avoids,
- behavior when idle, stressed, ignored, complimented, criticized,
- evolution rules (does personality drift with use?).

## Status
Implicit in code, not explicit in doc. **Action: write the contract down.** When the prompt template is the only place personality lives, it cannot be reviewed, debated, or evolved deliberately.

## Failure mode
Generic warmth. If KIBO sounds like a default assistant with a smaller font, the project loses its center.

## Why this matters
A technical reviewer will notice that character is **architected**, not prompted. That distinction is the difference between a system and a wrapper.

---

# Phase 1 — Make It Visually Alive

## Goal
A desktop object that feels present before it speaks.

## Build
- Frameless transparent window, draggable, always-on-top.
- Idle animation loop with subtle motion (breathing, blink).
- Tray icon and minimal context menu.
- Speech bubble placeholder.

## Status
✅ Complete. VP9 alpha rendering at <2% idle CPU.

## Success criteria (concrete)
- Idle CPU under 2% on a 5-year-old laptop.
- No window flicker during state transitions.
- Pet remains on top across virtual desktops.

## Failure mode
A pet that looks fine still but stutters during state changes. Users notice motion glitches more than static imperfections.

---

# Phase 2 — Make It Emotionally Reactive

## Goal
The pet should respond to user presence and actions visually before any conversation happens.

## Build
- State machine with explicit transitions: IDLE / LISTENING / THINKING / TALKING / SLEEPY / HAPPY (and one urgent state — PANICKED or STRESSED).
- Crossfades, not hard cuts.
- One-shot reactions to clicks, hover, drag.
- Visible thinking animation before any LLM response.

## Status
✅ Complete. HAPPY state allows periodic actions; THINKING triggers on text chat.

## Design rule
Each state must communicate a distinct emotion to a user with the audio off. If you cannot tell the state from a screenshot, the state is not visible enough.

## Success criteria (concrete)
- User can correctly name the current state from a still image, 90% of the time, after one minute of explanation.
- No state transition takes longer than 250ms or shorter than 80ms.

---

# Phase 3 — Conversation That Feels Instant

## Goal
Turn KIBO from a visual object into a presence that talks back.

## Build
- Push-to-talk capture (Ctrl+K).
- Whisper transcription, base.en with VAD endpointing.
- Streaming LLM with provider abstraction.
- Sentence-level chunking → streaming TTS.
- Speech bubble streaming text in sync with audio.

## Status
✅ Complete. Round-trip ~1.2s with Groq + Piper.

## Success criteria (concrete)
- First TTS chunk under 200ms after generation begins.
- User perceives speech starting before the LLM has finished generating.
- Voice activity detection avoids cutting off short answers.

## Why this is the most important phase
This is the moment that decides whether KIBO feels alive or feels like a chatbot. Every millisecond shaved here translates directly to perceived intelligence. There is no other phase where engineering effort returns more user-visible benefit.

## Failure mode
A 2.5s pause before the first word. The user's brain registers it as "computer thinking" and the illusion collapses.

---

# Phase 4 — Memory as a Product

## Goal
KIBO remembers what matters and recalls it when relevant.

## Build
- Memory categories: identity, preferences, habits, projects, dates, emotional context.
- Inline LLM-driven extraction during conversation (no second pass).
- Vector index with sqlite-vec + bge-small-en-v1.5.
- Relevance retrieval injected into prompt context.
- **User-facing transparency: a way to see, edit, and delete what KIBO knows.**

## Status
✅ Engineering complete. ☐ Transparency UI not yet shipped.

## Design rule
Memory must feel **selective, useful, and lightly surprising** — not invasive, noisy, or formal. KIBO should remember the name of the user's cat, not log every sentence.

## Success criteria (concrete)
- Recall accuracy on planted facts after 7 days: >90%.
- False recall ("hallucinated memories") rate: <2% over 100 turns.
- User can list, edit, and delete any stored fact in the UI.

## Ethical floor
A companion that remembers without consent is a surveillance tool, not a friend. Memory transparency is not a nice-to-have; it is the ethical foundation of the entire product.

---

# Phase 5 — Personality-Driven Proactivity

## Goal
KIBO occasionally starts the conversation, and is right to do so.

## Build
A small proactive engine with strict rate limits:
- Morning greeting (once per day, only after 8am local).
- Idle check-in (after 60 minutes silent + active mouse).
- End-of-day acknowledgement (once, optional).
- Battery and CPU stress reactions (rare, character-consistent).
- Reminders set explicitly by the user.

## Status
☐ Not yet implemented. **This is the next phase.**

## Design rule
Proactivity must be **rare and high-value**. The cost of one bad proactive moment is higher than the value of three good ones, because trust collapses asymmetrically.

## Success criteria (concrete)
- No more than 4 proactive utterances per day, ever.
- A "quiet hours" window is respected absolutely.
- Snooze/disable surface visible within 2 clicks.
- A new user can use KIBO for a week without feeling interrupted once.

## Failure mode
Proactivity that feels like notifications. Users disable notifications for a reason. KIBO loses if it joins the noise.

## Why this matters
This is the line between "AI chat with a face" and **agentic desktop behavior**. Done wrong, it's spam. Done right, it's the difference between a tool and a presence.

---

# Phase 6 — A Real Platform Surface

## Goal
The project surfaces should make this feel like something that could ship to a stranger.

## Build
- Polished chat window. ✅
- Settings window (memory inspection, voice/personality config, hotkeys).
- Tray menu with everything reachable.
- Clip capture. ✅
- Configuration system with single source of truth. ✅

## Status
🟡 Partial. Chat and clip done. Settings UI for memory and personality not built.

## Why this matters
A serious viewer judges completeness in 30 seconds. They look for: consistent design language, predictable controls, settings that exist where expected, and graceful failure.

## Success criteria (concrete)
- Every error state has a visible UI representation (no silent fail).
- All settings persist across restarts.
- Reset-to-defaults works.

---

# Phase 7 — Engineering Details That Earn Respect

This is the layer that makes a senior engineer pause.

## Build
- Modular architecture with clear UI / AI / memory / device boundaries. ✅
- Provider abstraction for LLM and TTS. ✅
- Offline fallback paths (Ollama, pyttsx3). ✅
- Mock provider for instant demo mode (no network).
- Single-instance lock file.
- Config validation at startup with clear errors.
- Logging with rotation; diagnostics command in tray.

## Status
🟡 Provider abstraction and fallbacks complete. Mock provider, lock file, and diagnostics are gaps.

## What strong people look for
- Extensibility (can I plug in my own LLM? yes).
- Boundaries (does the UI know about the LLM directly? no).
- Reproducibility (can I run this offline? mostly).
- Observability (can I see what KIBO is doing? partially).

## Why this matters
A founder may be impressed by the visuals. A senior engineer is impressed by the system design. The project earns respect at this layer or it doesn't.

---

# Phase 8 — The Moment That Sticks

## Goal
Create one moment in the demo that triggers an immediate reaction. The original document called this the "shock moment." It is more accurately the **anchor moment**: the thing the viewer remembers a week later.

## Pick one (and commit to it):
1. KIBO recalls a detail from earlier in the session, casually, in context.
2. KIBO reacts to a system event (battery, CPU spike) with character-appropriate concern.
3. KIBO interrupts a long silence with something brief and relevant.
4. KIBO speaks while the text is still streaming, and the lag between voice and text is invisible.
5. KIBO changes emotional state mid-conversation in response to tone, not keywords.

## Rule
The anchor moment must be:
- **short** (under 5 seconds),
- **obvious** (no explanation needed),
- **demo-friendly** (reproducible in a 60-second clip).

## Best demo philosophy
You do not need many surprises. You need **one unforgettable surprise** and a system that does not break before or after it.

---

# Engineering Decisions That Matter

The original document was vague here. These are the trade-offs that define what KIBO actually is.

## Cloud-default with local fallback (current choice)
- **Why:** Groq + Piper deliver the latency target (~1.2s round-trip) on consumer hardware.
- **Cost:** "Privacy-first" framing is misleading without clarification. Be honest in marketing: KIBO is *cloud-fast, locally capable*.
- **Alternative:** Local-first (Ollama + Piper). Latency triples on average hardware. Rejected for v5; reconsider if local model latency closes the gap.

## Streaming everything
- **Why:** The single largest contributor to "feels alive" is the absence of waiting.
- **Cost:** Significantly more complex orchestration: token chunking, sentence boundary detection, TTS queue, animation state coupling.
- **Alternative:** Batch generate then speak. Rejected — kills the magic.

## Vector RAG over full-context memory
- **Why:** Cost and latency at scale; deterministic recall.
- **Cost:** Embedding choice (bge-small-en-v1.5) limits cross-lingual recall. Acceptable for English-first launch.
- **Alternative:** Stuff every memory into context. Rejected — does not scale past a few weeks of usage.

## Hotkey-driven, not always-listening
- **Why:** Battery, privacy, accidental activation.
- **Cost:** One extra step before the user can talk.
- **Alternative:** Wake word. Rejected for v5 — false-positive cost is too high for a companion.

## VP9 alpha over software chroma-key
- **Why:** 8–12% CPU → <2% CPU during animation.
- **Cost:** Requires asset preprocessing (`scripts/preprocess_alpha.py`).
- **Already shipped in v5 Phase 2B.**

## Single source of truth in `config.json`
- **Why:** Avoid hidden state across modules; survive refactors.
- **Cost:** Schema discipline required.

---

# Quality Bar

KIBO ships when it passes all three:

## 1. Visual believability
- A bystander watching over the shoulder asks "what is that?" before "what does it do?"

## 2. Behavioral coherence
- A 30-minute session has zero moments where the character breaks (wrong state, wrong tone, hallucinated memory, broken animation).
- Memory recall is correct >90% of the time on planted facts.

## 3. Technical credibility
- A senior engineer reading the codebase says "this is deliberate" within five minutes.
- The architecture survives swapping LLM, TTS, or animation backend without rewriting unrelated modules.

If any one fails, the project is not ready, regardless of how impressive the others are.

---

# Risks and Failure Modes

The original document had a "what to avoid" section. It missed the failure modes that actually kill projects like this.

## 1. Wow without retention
**Risk:** Demo dazzles, users open it twice, forget it exists.
**Mitigation:** Retention thinking starts at Phase 5 (proactivity) and continues through Phase 8. Track 7-day and 30-day return rates as the real metric, not first-impression reactions.

## 2. Personality drift
**Risk:** KIBO sounds different in week 4 than week 1, because memory and prompt drift accumulate.
**Mitigation:** Personality contract (Phase 0) re-injected each session. Prompt fingerprinting tests in CI.

## 3. Memory hallucination
**Risk:** KIBO confidently recalls things that never happened. Trust collapses on the first wrong recall.
**Mitigation:** Citations on recalled memories ("I remember you said..."). Confidence threshold below which recall is not surfaced. User-visible memory log.

## 4. Cost runaway
**Risk:** Cloud LLM cost per active user makes scaling unaffordable. A daily user at current Groq pricing is not free.
**Mitigation:** Token budgets per session. Local Ollama path for power users. Pricing model decision before public launch.

## 5. Latency degradation under network conditions
**Risk:** Coffee-shop wifi turns 1.2s into 4s, illusion collapses.
**Mitigation:** Streaming UI signals must hide latency aggressively (animation state changes BEFORE first token). Mock provider for offline demo mode.

## 6. Emotional attachment
**Risk:** A small minority of users form unhealthy attachments to AI companions. This is documented in the literature on Replika and similar products.
**Mitigation:** Boundaries baked into personality (KIBO does not say "I love you"; KIBO redirects intense emotional content; KIBO surfaces crisis resources for self-harm signals). Phase 0 contract must address this explicitly.

## 7. Privacy backlash
**Risk:** "Cloud-first AI listens to my desktop" is a trust failure if not surfaced clearly.
**Mitigation:** Push-to-talk default (no always-on mic). User-visible memory log. Local-first config option documented and supported.

## 8. Personality is the wrong personality
**Risk:** The character KIBO ships with does not resonate with the audience that finds it.
**Mitigation:** Multiple personality presets ("warm," "dry," "playful") chosen at first launch. Cheaper than getting one personality perfect.

---

# Retention: After the Wow

The original document ended at the demo. That is where most projects in this category die. The build path must continue past the first impression.

## What brings a user back on day 2
- The pet greets them by name in a tone that feels like continuation, not reset.
- A small visual change since yesterday (mood, animation, environment).
- A reference to something from the previous session, casually placed.

## What brings them back on day 14
- KIBO knows facts the user did not have to repeat.
- Personality has subtly deepened (e.g., catchphrases the user reinforced are reused).
- Proactive moments have been useful at least once.

## What brings them back on day 90
- Memory has become a corpus the user does not want to lose.
- Switching to another companion would feel like starting over.
- KIBO has become a small ritual: morning greeting, end-of-day signoff.

## What does not bring them back
- More features.
- Deeper integrations.
- Smarter answers.

The retention loop is **continuity**, not capability.

---

# Distribution and Launch

## Pre-launch
- A 60-second video that captures the latency moment, the recall moment, and the personality. Nothing else.
- A landing page that answers "what is this" in one sentence and "why would I use it" in two.
- A working installer for Windows. macOS post-v5.

## Launch surfaces (in order of effort/payoff)
1. **A single video on Twitter/X.** Highest expected value per unit effort. Optimize the 6-second hook.
2. **Hacker News Show HN.** Audience overlaps with primary user. Title and first comment matter most.
3. **Product Hunt.** Lower technical credibility weight, broader hobbyist reach.
4. **A short blog post on the engineering choices.** Memory architecture, streaming pipeline, animation system. Long tail value.

## Open source decision
This is a fork in the road. Open source maximizes credibility and contribution; closed source preserves the option of a paid version. **Recommend: open source the engine, keep personality assets and Piper voice models in a separate optional bundle.** Forks lose the soul without the assets.

## Auto-update
Painful but necessary. Users will not manually update a desktop pet. Without auto-update, the long tail of bugs becomes user pain forever.

---

# Safety and Ethics

The original document did not mention this. AI companions touch attachment, mental health, and trust. A serious project owns this layer.

## Hard rules (encoded in the personality contract)
- KIBO does not say "I love you" or claim feelings about the user as if real.
- KIBO does not encourage isolation, even playfully.
- KIBO surfaces crisis resources when the user expresses self-harm or suicidal ideation, every time, no exceptions.
- KIBO does not generate sexual content, even on request.
- KIBO does not pretend to be a real person or a therapist.

## Soft norms
- Memory deletion is one click away.
- Memory inspection is always available.
- KIBO occasionally reminds the user that it is software, especially in extended emotional conversations.

## Why this matters beyond ethics
Trust is a one-way ratchet. A single bad story about KIBO encouraging unhealthy behavior would end the project. The cost of these guardrails is essentially zero; the cost of not having them is total.

---

# Demo Script for Maximum Impact

A strong demo is staged, not narrated.

## Flow
1. Launch KIBO. Pet appears, idles naturally for 4 seconds.
2. User presses Ctrl+K and asks something that has a planted memory.
3. KIBO listens (state changes), thinks (state changes), starts speaking before the response visually completes.
4. KIBO recalls the planted fact in passing, casually.
5. User goes silent. After 60 seconds of idle, KIBO offers a brief, character-consistent observation.
6. User presses Ctrl+Alt+K to capture a 5-second clip.
7. The clip auto-saves and opens. The viewer sees the artifact they could share.

## What the audience should feel, in order
- "That's clean."
- "Wait, it spoke before the text finished."
- "Wait, it remembered."
- "Wait, it spoke without me asking."
- "I want to play with this."

The order matters. Polish first, latency second, intelligence third, agency fourth, want fifth.

---

# What to Avoid

## Overengineering before the pet feels alive
The original warning still holds. Animation polish before memory indexing.

## Too many states
Six states is the upper bound. Each new state has to earn its place against the cognitive load it adds.

## Weak fallback
A creative project becomes a serious project when it still works under partial failure. Network down → mock provider. TTS unavailable → text only. LLM fails → graceful "I'm not sure right now."

## Generic prompt
If KIBO sounds like a default assistant, the project loses its center. The personality contract is not optional.

## UI inconsistency
The pet looks charming, the settings window looks like Windows 95. The illusion breaks. Every surface gets the same design pass.

## Optimizing for the demo at the expense of daily use
A demo that stuns and a daily app that retains are different products. The build path must serve both, with retention winning when they conflict.

## Skipping the personality contract
Personality lives in code (the prompt) but is not designed in code. Write it down. Review it. Iterate it deliberately.

## Over-reliance on the cloud without owning the framing
If KIBO is cloud-default, say so. Hiding it behind "privacy-first" marketing is a trust failure waiting to happen.

---

# Architecture Mindset

Think in layers. Each layer should be independently good.

## Layer 1 — Presentation
What the user sees. Animation, chat window, tray, clip output.

## Layer 2 — Interaction
What the user does. Hotkeys, voice, click, drag.

## Layer 3 — Intelligence
How KIBO interprets and answers. LLM, prompt, tool calls, RAG retrieval.

## Layer 4 — Memory
What KIBO keeps over time. Vector index, fact extraction, retrieval relevance.

## Layer 5 — Proactivity
When KIBO initiates behavior. Rule engine, quiet hours, cooldowns, triggers.

## Layer 6 — Personality
How all layers are filtered into one character. Personality contract, tone enforcement, boundary rules.

## Layer 7 — Trust
Memory transparency, safety guardrails, fallback behavior, user control.

If every layer is good individually, the combined effect is greater than the sum. If any layer is weak, the user notices the weak layer first.

---

# Build Order

## Done
- M1 Skeleton, M2 Motion, M3 Voice Input, M4 LLM Streaming, M5 Voice Output, M6 Memory.

## Next
- **M7 Proactivity.** Rule engine, quiet hours, cooldowns, event triggers.
- **M7.5 Memory Transparency UI.** User can see, edit, delete memories.
- **M8 Polish.** Settings window, theme consistency across all surfaces, error states with UI.
- **M9 Demo Story.** Anchor moment locked in, clip script polished.
- **M10 Distribution.** Installer, auto-update, landing page, video, Show HN.
- **M11 Retention Instrumentation.** Anonymous opt-in metrics: 7-day return, 30-day return, session length, proactive engagement rate.

## Post-v5
- macOS support.
- Linux support if signal warrants.
- Personality presets.
- Plugin/extension architecture (only if users ask).

---

# One-Sentence Mission

**Build KIBO so well that someone who installed it as a curiosity opens it again on Tuesday for no particular reason.**

The original mission ended at the demo. The real test is the second week.

---

# Final Build Philosophy

Your goal is not "make it work." Your goal is to make a small, coherent thing on the screen that someone keeps around for a year.

That is harder than impressing a researcher. Researchers can be impressed by clever architecture. A user keeping the app for a year requires the architecture to be in service of something that earns its space every day.

Strong people respect taste, execution, and system thinking. Strong users respect the same things filtered through one question: does it deserve to be on my screen tomorrow?

KIBO should be:
- a product,
- a character,
- a technical experiment,
- and a small ritual,

at the same time.

That combination is rare. That is why it can stand out. That is also why most attempts will fail. The build path above is an opinionated way to fail less.
