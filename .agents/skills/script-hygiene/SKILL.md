---
name: script-hygiene
description: >-
  Use this skill whenever authoring or validating dialogue, staging metadata, video scripts, or retention rules for veraxi-ymmp. Covers cold opens, character archetypes, 50/30/20 pacing, dialogue ping-pong, causal domino causality, and anti-AI-slop invariants.
---

# Script Hygiene & Audience Retention Guidelines (Anti-AI-Slop)

This skill governs all dialogue generation, staging metadata, and pacing rules for `veraxi-ymmp` projects.

---

## 1. 0-Second Cold Open Invariant (冒頭0秒コールドオープン原則)
- **Zero Greetings:** NEVER begin with generic greetings (`「みんな、こんにちは」`, `「ごきげんよう」`, `「よろしく」`). Modern YouTube retention drops 30%–40% on opening pleasantries.
- **In Media Res:** Start at 0.0s with high-stakes cognitive dissonance, shocking metrics, or contrarian conflict (The Public Illusion / 世間の大いなる勘違い).
- **No Premature Slide Overload:** Cut 0–Cut 2 MUST NOT dump presentation slides (`"image": null`). The opening hook relies on character emotional confrontation and dramatic dialogue. Structured data slides enter around Cut 3–5 when transitioning to core facts.

---

## 2. The 3 Character Archetypes (Anti-AI-Slop Protocol)
- **ずんだもん (The Chaotic Proxy):**
  - Represents the viewer's raw greed, panic, shock, and naive misconceptions.
  - NEVER write him as a B2B corporate consultant, IT procurement analyst, or financial lecturer.
  - He must NEVER lecture the audience (`大企業ほど〜`, `〜見るべきなのだ`). He reacts with visceral emotion, shock, and money worries (`「ええっ、一社に全部握られたら、言い値でカモにされるのだ！？」`, `「ボクの株、明日売っ払ってくるのだー！」`).
- **四国めたん (The Cold Intellectual / Sadistic Realist):**
  - Aristocratic, sharp realist who punctures Zundamon's naive illusions with dry sarcasm, forensic ruthlessness, and devastating calm.
  - **Banned 'Yes-Man Metan':** Metan must NEVER agree with Zundamon in more than 35% of her cuts (`はい。`, `その通りですわ。` spam is strictly forbidden).
  - Punishing quips: `「おめでたい頭ですわね」`, `「底値で狼狽売りする養分の鑑ですわね」`.
- **春日部つむぎ (The Trench Insider / High-Energy Gal):**
  - High-energy gal bringing messy ground reality, developer gossip, and contrarian whistleblower perspectives from the server room.
  - NEVER a corporate PR brochure or bullet-point reader.

---

## 3. Retention Golden Ratio & Cast Allocation
- **50/30/20 Ratio:**
  - Main Explainer (四国めたん): 45%–55%
  - Lead Inquirer (ずんだもん): 30%–35%
  - 3rd Specialist (春日部つむぎ): **15%–20%** (Hard ceiling $\le 25\%$ to prevent acoustic fatigue and group-banter derailment).
- **Hook Protection Rule:** 3rd character must NEVER speak in the opening hook (first 10% or first 3 cuts). Premise must be cleanly established by the core duo to prevent early bounce.
- **Mid-Roll Attention Spike:** 3rd character's first entrance must occur during the mid-roll attention decay window (30%–50% timeline mark) to reset audience focus as a contrarian insider.


---

## 4. Rhythmic Syncopation & Dialogue Ping-Pong (卓球ラリー原則)
- **Anti-Monotony:** Monotonous sentence lengths (all cuts uniformly 28–38 chars) are strictly banned.
- **Micro-Reactions:** Scripts MUST include $\ge 5\text{--}10\%$ 1-beat micro-reaction cuts ($\le 12$ chars, e.g. `「ええっ！？」`, `「嘘でしょ！？」`, `「正気なのだ！？」`, `「あり得ませんわ」`) to create rapid comedic contrast and natural breath marks for VOICEVOX.
- **Line Ceilings:** Maximum 2 lines per speech bubble. Character ceiling $\le 35\text{--}40$ characters per dialogue cut.

---

## 5. Narrative Conflict Structure (Dramatic Conflict)
NEVER structure videos as boring corporate lectures with generic bullet lists (`「3つのポイント」`, `「3大視点」`, `「3大潮流」` are strictly banned). Top-tier YouTube retention requires **Dramatic Conflict (認知的不協和)**:
1. **世間の大いなる勘違い (The Public Illusion):** `「マイクロソフトがOpenAIで完全勝利…と思っていませんか？」`
2. **一次資料・現場の冷酷な真実 (The Unvarnished Forensic Truth):** Real numbers, engineering limits, or financial disclosures.
3. **つむぎ参戦のちゃぶ台返し (The Contrarian Whistleblower):** Tsumugi enters from the tech/engineering trenches to overturn assumptions.
4. **逃げられないチキンレース (The Game-Theory Trap):** Why both giants must keep burning billions or face extinction.
5. **忖度なしの最終審判 (The Real Winner/Loser Verdict):** Grounded causal conclusion.

---

## 6. Phonetic & Currency Notation Invariant
- **Authoritative Names:** Always use full company names in spoken dialogue: use **「マイクロソフト」**, never 「MS」 or 「エムエス」.
- **Standard Currency:** Write **「2200億ドル」** or **「3兆円」**, never append a trailing dollar sign like `「2200億$」`.
- **Natural Affirmations:** NEVER begin with bare `「ええ、」`. Use character-specific affirmations (`「はい、」`, `「その通りですわ、」`, `「まさにその通りなのだ！」`).

---

## 7. Pricing & Metric Disambiguation Invariant (価格・指標の文脈明示原則)
- NEVER quote naked SaaS/subscription pricing without explicit target tier and per-seat unit (bare `「月額30ドル」` is banned).
- Always qualify: specify tier (法人向け vs 個人向け), unit (社員1人あたり / 1アカウント), and nature (基本契約に加えて1人月30ドルの追加課金/アドオン). Viewers must never be left guessing whether a price is per-seat or per-organization.

---

## 8. The Causal Domino Protocol: Loss-Aversion & Structural Domino Invariant (構造的ドミノ連鎖原則)
- **Loss-Aversion / Cognitive Disillusion Hook:** Puncture the mainstream consensus trap or widespread myth within opening 10 seconds. High-stakes loss aversion (capital destruction, system crash, legal liability) drives 2x higher retention than generic cheerleading.
- **Primary Authority Citations:** Anchor scripts to verifiable primary data sources (Technical RFC/CVE specs, PubMed/arXiv, Court dockets, FRED, SEC filings, government statistics).
- **4-Phase Domino Causality:** Structure narrative as a mechanistic chain reaction:
  *Consensus Illusion $\to$ Primary Evidence Fracture $\to$ Structural Domino Cascade $\to$ Cold Survival Verdict*.
- **High-Stakes Packaging:** Titles and thumbnails MUST NEVER use passive match-up cliches (e.g. bare `「勝つのはどっち！？」` is banned). Deploy high-tension curiosity gaps with concrete stakes (e.g. `「【全員騙されていた】60兆円AIバブルの罠…生き残る真の1社」` or `「【脆弱性CVE-2024】99%のエンジニアが見落とす致命的欠陥」`).

---

## 9. Retention-Preserving Ending Invariant (Zero-Drop Ending)
- NEVER end with formulaic goodbyes (`「チャンネル登録と高評価もぜひよろしくねー！」`, `「また次回の動画で会おうなのだ！」`). These trigger an immediate 40%+ cliff drop in Average View Duration.
- End abruptly on high emotional stakes, an unresolved comedic punchline, a panicked realization, or a provocative teaser.

---

## 10. Staging, Audio & Visual Standards
- **Grounded Staging:** NEVER use cartoon `"jump"` in commentary/technical videos. Characters remain grounded (`"motion": "none"` or subtle `"nod"`).
- **Clean Audio:** NEVER inject slapstick cartoon SFX (`pon.wav` banned). Use only clean non-vocal instrumental BGM ducked to balanced levels ($\le 0.18$ volume for -16 LUFS speech).
- **Pro Dark Slate B-Roll:** Background `#0F172A` / `#1E293B`. 1-Slide-1-Impact: Total characters across slide $\le 100$. Maximum 6 text elements. Zero nested bullets.
- **YouTube Thumbnail:** 3-Split layout (character reaction right, high-contrast headline left, bottom-right timestamp safe zone protected).


---

## 11. Conversational Naturalness & Rival Quality Protocol (対話の自然性・ライバル品質プロトコル)

Top YouTube explainer channels (ゆっくり解説, ずんだもん解説) succeed because dialogue feels like lively human comedy/banter, not AI-generated SEC filing bullet points.

1. **Anti-Echo / Anti-Parrot Mandate (オウム返しの厳禁):**
   - **Banned:** Explainer states `「1日で2000億円以上の資金が消えていますわ」` $	o$ Reactor echoes `「1日2000億円！？回収できるのか！？」`.
   - **Remedy:** Reactors must NEVER copy-paste the explainer's metric followed by `！？`. Translate numbers immediately into **visceral emotion, street-level scale, or comedic comparison**:
     - *Bad:* `「たった3ヶ月で18.4兆円！？正気じゃないのだ！」`
     - *Good (Rival Quality):* `「ちょ、国家予算どころか毎日スカイツリーを建てて爆破してるような桁なのだ！？」`
     - *Bad:* `「コストが半額になるのだ！？」`
     - *Good (Rival Quality):* `「は、半額！？スーパーの見切り品じゃあるまいし、そんな上手い話あるわけないのだ！」`
2. **Spoken Dialogue vs. Written Press Releases (体言止め・ニュース原稿読み上げの禁止):**
   - VoiceVox synthesizes bare Sino-Japanese verbal nouns (`〜を突破。`, `〜を記録。`, `〜へ低下。`) with a dead, robotic falling pitch.
   - Spoken dialogue MUST always end in conversational inflected predicates:
     - *Banned:* `「AWS営業利益は177億ドルを突破。」`
     - *Required:* `「AWSの営業利益は177億ドルを軽々と叩き出していますのよ。」`
3. **Authentic Character Voice & Anti-Register Drift (キャラクター固有の語尾と文体の死守):**
   - **四国めたん:** Sarcastic gothic aristocrat. Uses `〜ですわ`, `〜ますわよ`, `〜かしら`, `〜のよ`. BANNED from dropping into flat corporate announcer `〜です。` / `〜ます。`, and banned from archaic samurai keigo (`左様でございますわ`).
   - **春日部つむぎ:** Cheerful, cheeky server-room insider kouhai. MUST use natural colloquial endings (`〜っすよ！`, `〜じゃないすか！`, `〜っすね！`). BANNED from sterile corporate speech disguised with generic `〜んだよ！` / `〜の！`.
   - **ずんだもん:** Raw human vulnerability, money panic, gullible optimism, and greed. Speaks with relatable human perspective (ずんだ餅, ソシャゲ課金, お小遣い, 家賃).
4. **Varying Affirmations & Dynamic Banter (定型相槌の重複禁止):**
   - Repeating `「その通りですわ」` multiple times across a video sounds mechanical.
   - Use lively, varied conversational reactions: `「甘いですわね」`, `「仰る通りですわ」`, `「核心を突きましたわね」`, `「愚問ですわ」`, `「まさにその通りなのだ！」`.
