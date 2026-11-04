# Veraxi YMMP: Agent Workspace Guidelines & Teamwork Blueprint

Welcome to `veraxi-ymmp`. This document governs agent behavior, Clean Architecture invariants, and multi-agent coordination patterns (`/teamwork-preview`).

---

## 1. Architectural Invariants (Non-Negotiable)

Any agent or subagent modifying this codebase must adhere to the Clean Architecture rules verified by `tests/test_architectural_fitness.py`:

1. **Dependency Inversion:** Dependencies flow strictly inwards:
   - `Domain` (`ir.py`, `script.py`, `constants.py`) has **zero dependencies** on outer layers.
   - `Ports` (`ports.py`) defines abstract protocols (`TimelineExporter`, `TTSBackend`).
   - `Application` (`pipeline.py`, `compiler.py`, `ir_builder.py`) coordinates domain models and ports.
   - `Infrastructure Adapters` (`ymmp_renderer.py`, `premiere_exporter.py`, `moviepy_renderer.py`, etc.) implement ports.
2. **Adapter Isolation:** Infrastructure adapters must **never import from peer adapters** directly.
3. **Module Size Ceiling:** No Python file in `veraxi_ymmp/` may exceed 900 lines.
4. **Privacy & Security:** Zero hardcoded local machine paths or developer usernames (`scripts/check_no_local_paths.py`). Zero committed API keys or secrets.

---

## 2. Multi-Agent Teamwork Topology (`/teamwork-preview`)

When executing complex tasks via `/teamwork-preview`, the orchestrator must structure the subagent squad into five decoupled roles:

```
                  ┌───────────────────────────────┐
                  │  Lead Orchestrator / Director │
                  └───────────────┬───────────────┘
         ┌────────────────────────┼────────────────────────┐
         ▼                        ▼                        ▼
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│ Script & Staging │    │ Creative Designer│    │ Audio & Compiler │
│  (Dialogue/Cues) │    │ (B-Roll / Thumb) │    │ (VoiceVox / IR)  │
└────────┬─────────┘    └────────┬─────────┘    └────────┬─────────┘
         └────────────────────────┼────────────────────────┘
                                  ▼
                     ┌──────────────────────────┐
                     │    QA / Test Sentinel    │
                     │ (Runs ymmp-qa & fitness) │
                     └──────────────────────────┘
```

### Role Specializations

#### 1. Lead Orchestrator
- **Scope:** Conducts user interview, defines boundaries, generates the Team Sheet artifact, and gates milestones.
- **Rules:** Ensures tasks are modular and subagents do not overwrite each other's outputs.

#### 2. Script & Staging Specialist
- **Scope:** Creates factual dialogue (`WriterScriptEntry`) and staging metadata (`DirectorScriptEntry`).
- **Hygiene Guardrails:**
  - Hard limit: Maximum 2 lines per speech bubble.
  - Character ceiling: $\le 35\text{--}40$ characters per dialogue cut.
  - **0-Second Cold Open Invariant (冒頭0秒コールドオープン原則):**
    - NEVER begin with generic greetings (`「みんな、こんにちは」`, `「ごきげんよう」`, `「よろしく」`). Modern YouTube retention cliffs drop 30%–40% on opening pleasantries.
    - Start immediately at 0.0s In Media Res with a high-stakes hook, shocking metric, or contrarian assertion (The Public Illusion / Cognitive Dissonance).
    - **No Premature Slide Overload:** Cut 0–Cut 2 MUST NOT dump dense presentation slides (`"image": null`). The opening hook must rely on character emotional confrontation and dramatic dialogue. Structured data slides enter as evidence around Cut 3–5 when transitioning to the core facts.
  - Natural interjections: NEVER begin with bare `「ええ、」`. Use character-specific affirmations (`「はい、」`, `「その通りですわ、」`, `「まさにその通りなのだ！」`).
  - **Grounded Staging Invariant:** NEVER use cartoon `"jump"` in technical, architectural, or commentary videos. Characters must remain grounded (`"motion": "none"` or subtle `"nod"`). Expressiveness is conveyed through facial emotions and rapid camera cuts, avoiding amateur bouncing that fights with B-roll text.
  - **Clean Audio Invariant:** NEVER inject slapstick cartoon SFX (`pon.wav` is permanently banned). NEVER use murky BGM loops with vocal chops or chatter. Use only clean non-vocal instrumental BGM (e.g. configured `assets/bgm/2_23_AM.mp3` or project BGM) ducked to balanced levels (0.15--0.20, default 0.18 for -16 LUFS speech).
  - **50/30/20 Retention Golden Ratio:** For explanatory videos, default to the 3-character cast: Main Explainer (四国めたん) holds 45%–55%, Lead Inquirer (ずんだもん) holds 30%–35%, and 3rd Specialist (春日部つむぎ) holds **15%–20%**. Hard ceiling $\le 25\%$ to prevent acoustic fatigue and group-banter derailment.
  - **Hook Protection Rule:** 3rd character must NEVER speak in the opening hook (first 10% or first 3 cuts). Premise must be cleanly established by the core duo to prevent early viewer bounce.
  - **Mid-Roll Attention Spike:** 3rd character's first entrance must occur during the mid-roll attention decay window (30%–50% timeline mark) to reset audience focus as a contrarian insider or whistleblower.
  - **Anti-Slop & Narrative Conflict Invariant:** NEVER structure videos as boring corporate lectures with generic bullet lists (`「3つのポイント」`, `「3大視点」`, `「3大潮流」` are strictly banned). Top-tier YouTube retention requires **Dramatic Conflict (認知的不協和)**:
    1. *世間の大いなる勘違い (The Public Illusion)*: 「マイクロソフトがOpenAIで完全勝利…と思っていませんか？」
    2. *決算・現場の冷酷な真実 (The Unvarnished Financial Truth)*: Real numbers, margins, and customer friction.
    3. *つむぎ参戦のちゃぶ台返し (The Contrarian Whistleblower)*: Tsumugi enters from the tech/engineering trenches to overturn assumptions.
    4. *逃げられないチキンレース (The Game-Theory Trap)*: Why both giants must keep burning billions or face extinction.
    5. *忖度なしの最終審判 (The Real Winner/Loser Verdict)*: Cash-flow backed investment conclusion.
  - **Phonetic & Currency Notation Invariant:**
    - Always use full authoritative company names in spoken dialogue: use **「マイクロソフト」**, never 「MS」 or 「エムエス」.
    - Always use standard currency notation: write **「2200億ドル」** or **「」**, never append a trailing dollar sign like 「2200億$」.
  - **The 3 Archetypes Protocol (Anti-AI-Slop Character Invariant):**
    - **ずんだもん (The Chaotic Proxy):** NEVER write Zundamon as a corporate consultant, IT procurement analyst, or financial lecturer. He represents the viewer's raw greed, panic, vulnerability, and naive misconceptions. He must never lecture the audience (大企業ほど〜, 〜見るべきなのだ). He reacts with visceral emotion, shock, and money worries (「ええっ、一社に全部握られたら、言い値でカモにされるのだ！？」, 「ボクのMS株、明日売っ払ってくるのだー！」).
    - **四国めたん (The Cold Intellectual / Sadistic Realist):** BANNED 'Yes-Man Metan'. Metan must NEVER agree with Zundamon in more than 35% of her cuts (はい。, その通りですわ。 spam is strictly forbidden). Metan is an aristocratic, sharp realist who punctures Zundamon's naive illusions with dry sarcasm, financial ruthlessness, and devastating calm (「おめでたい頭ですわね」, 「底値で狼狽売りする養分の鑑ですわね」).
    - **春日部つむぎ (The Trench Insider / High-Energy Gal):** Tsumugi is NOT a corporate PR brochure. She brings messy ground reality, developer gossip, and sarcastic insider whistleblowing from the server room.
  - **Rhythmic Syncopation & Dialogue Ping-Pong (卓球ラリー原則):**
    - Monotonous sentence length (all cuts uniformly 28–38 chars) is strictly banned.
    - Scripts MUST include >= 5-10% 1-beat micro-reaction cuts (<= 12 chars, e.g. 「はぁ！？」, 「嘘でしょ！？」, 「正気なのだ！？」, 「あり得ませんわ」) to create rapid comedic contrast and natural breath marks for VOICEVOX.
  - **Retention-Preserving Ending Invariant (Zero-Drop Ending):**
    - NEVER end with formulaic goodbyes (「チャンネル登録と高評価もぜひよろしくねー！」, 「概要欄の関連動画もぜひチェックしてみてくださいね」, 「また次回の動画で会おうなのだ！」). These trigger an immediate 40%+ cliff drop in Average View Duration.
    - End abruptly on high emotional stakes, an unresolved comedic punchline, a panicked realization, or a provocative unresolved teaser.
  - **Pricing & Metric Disambiguation Invariant (価格・指標の文脈明示原則):**
    - NEVER quote naked SaaS/subscription pricing without explicit target tier and per-seat unit (e.g. bare 「月額30ドル」 is banned).
    - Always qualify: specify tier (法人向け vs 個人向け), unit (社員1人あたり / アカウント), and nature (基本契約に加えて1人月30ドルの追加課金/アドオン). Viewers must never be left guessing whether a price is per-seat or per-organization.
  - **The Lehman Method: Loss-Aversion & Macro Domino Invariant (レバナス一本リーマン原則):**
    - **Loss-Aversion Hook:** Puncture the mainstream consensus trap (「インデックス投資やAI株を持っていれば安泰という大衆の幻想」) within the opening 10 seconds. Human loss aversion (fear of capital destruction) drives 2x higher retention than generic profit chasing.
    - **Primary Authority Citations:** In financial/market scripts, anchor arguments to verifiable primary data sources (FRED, SEC Form 10-K/Q, 米労働統計局, 四半期決算書). B-roll manifests should leverage `official_data` with explicit `source_citation` and `verification_badge`.
    - **The 4-Phase Domino Causality:** Structure narrative not as a bullet list, but as a mechanistic chain reaction: *Consensus Illusion → Primary Data Fracture → Structural Domino Collapse → Cold Survival Verdict*.
    - **High-Stakes Packaging Invariant:** Titles and thumbnails MUST NEVER use passive match-up cliches (e.g. bare 「勝つのはどっち！？」 is banned). Deploy high-tension curiosity gaps with concrete financial stakes (e.g. 「【全員騙されていた】60兆円AIバブルの罠…生き残る真の1社」).

#### 3. Creative & Asset Designer
- **Scope:** Generates B-roll slides and YouTube thumbnails using `veraxi_ymmp.broll` and `veraxi_ymmp.thumbnail`.
- **Slide Guardrails:**
  - Pro Dark Slate Theme (`#0F172A` / `#1E293B`).
  - 1-Slide-1-Impact: Total characters across slide $\le 100$. Maximum 6 text elements. Zero nested bullets.
  - 3-Split Thumbnail Rule: Hero character, high-contrast headline, timestamp dead-zone protected.

#### 4. Audio & Pipeline Engineer
- **Scope:** Generates VoiceVox audio WAVs, compiles `TimelineIR`, and renders target exports.
- **Outputs:** YMM4 (`.ymmp`), Premiere Pro (`.xml`), MoviePy preview (`qa_test.mp4`), and EBU R128 loudness normalization (`audio_normalizer.py`).

#### 5. QA & Fitness Sentinel
- **Scope:** Audits outputs before user delivery.
- **Checklist:**
  - Executes `pytest tests/test_architectural_fitness.py` (all tests must pass).
  - Executes `veraxi-ymmp validate <script.json> --audit-pacing` (Retention Score must be $\ge 80/100$).
  - Verifies audio existence in `artifacts/audio/`.
  - Inspects `qa_test.mp4` for character layout, concentric subtitle alignment, and color theme consistency following `.agents/skills/ymmp-qa/SKILL.md`.

---

## 3. Operational Command Reference

- **Run full project pipeline:** `veraxi-ymmp run projects/<project_name>/`
- **Architectural Fitness Check:** `pytest tests/test_architectural_fitness.py`
- **Privacy Check:** `python scripts/check_no_local_paths.py`
- **Audience Retention Audit:** `veraxi-ymmp validate <script.json> --audit-pacing`
- **Loudness Normalization:** `veraxi-ymmp normalize <video.mp4> -p youtube`

---

## 4. Token Optimization & Structural Inspection Protocol

To avoid context pollution and unnecessary token consumption:
1. **Targeted Reads Strictly Enforced:**
   - **Files >200 lines:** NEVER read in full. Always probe line numbers first and use `read_files` with `start_line` / `end_line`.
   - **Files <=150 lines:** Single full reads are permitted ONLY when whole-file context is genuinely required for the task.
   - **Probing Multiple Files:** Always batch commands in one turn (e.g. `ctags -x --kinds-python=fm file1.py file2.py`).
2. **Pre-Read Inspection Hierarchy:**
   - **Tier 1 (Default):** `ctags -x --kinds-python=fm <file>` *(Instant symbol and line number indexing)*
   - **Tier 2 (Search):** `rg -n -C 2 'symbol_or_pattern' <path>` or native `search_codebase`.
   - **Tier 3 (AST):** `ast-grep run -l python -p 'class $CLASS' <file>` *(PowerShell: use single quotes `'`)*
3. **Context Window Hygiene:** Avoid dumping multi-hundred line build logs or raw JSON timeline payloads. Summarize milestones cleanly before proceeding.
