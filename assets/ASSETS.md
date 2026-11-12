# Veraxi YMMP Asset Attribution, Licensing & Setup Guide

This document governs the licensing, attribution requirements, and local setup instructions for media assets used with `veraxi-ymmp`.

---

## 1. Zero Third-Party Binary Tracking Invariant (二次配布防止)

To respect creator copyright guidelines and terms of service, **raw third-party character art (立ち絵素材), background illustrations, and royalty-free BGM files are NOT redistributed in this Git repository**.

Under standard Japanese licensing for voice synthesis characters and standing art:
- **Redistribution of raw image/audio files is strictly prohibited (二次配布・転載の禁止)**.
- Video creators are licensed to use the assets in rendered video outputs (YouTube, Niconico), provided appropriate credits are given.

The repository commits only **synthetic, programmatic test fixtures** and project-owned configuration dictionaries (`tts_dictionary.json`).

### 1.1 Optional assets and the `default_dark.png` fallback (fresh-clone behaviour)

The following referenced assets are **optional and intentionally not in git**:

| Referenced path | Status when absent |
|---|---|
| `assets/bgm/2_23_AM.mp3` / `assets/bgm/2_23_AM.m4a` | BGM is **omitted** — no BGM item is written to the `.ymmp`, and MoviePy renders without a BGM track. Never an error, never a dangling file reference. |
| `assets/bg/classroom.jpg` | Background falls back to the committed **`assets/bg/default_dark.png`** (Pro Dark Slate). Resolution order is `classroom.jpg` first (preferred when a user supplies it locally), then `default_dark.png`, via `resolve_background_image()` / `resolve_optional_asset()` in `veraxi_ymmp/core/constants.py`. |

A fresh clone therefore renders end-to-end with zero missing-file failures: place your own licensed copies at the paths above if you want the classroom background or the Sharou BGM, and the renderers will pick them up automatically.

---

## 2. Character Standing Art (立ち絵素材)

### 2.1. ずんだもん (Zundamon) & 四国めたん (Shikoku Metan)
- **Character IP:** SSS合同会社（東北ずん子・ずんだもんプロジェクト）
  - Guidelines: [東北ずん子利用規約](https://zunko.jp/guideline.html)
- **Voice Synthesizer:** VOICEVOX (VOICEVOX:ずんだもん, VOICEVOX:四国めたん)
  - Guidelines: [VOICEVOX 利用規約](https://voicevox.hiroshiba.jp/)
- **Recommended Standing Art:** 坂本アヒル氏 立ち絵素材
  - Terms: 二次配布禁止 (No secondary distribution). Commercial/non-commercial video production permitted with credit.
  - Setup: Place your downloaded character PSD or PNG face pack in your user Pictures folder (`~/Pictures/ずんだもん立ち絵素材/`) or specify via environment variable:
    ```bash
    export VERAXI_ZUNDA_PSD="$HOME/Pictures/ずんだもん立ち絵素材/ずんだもん立ち絵素材.psd"
    export VERAXI_METAN_PSD="$HOME/Pictures/四国めたん立ち絵素材/四国めたん立ち絵素材.psd"
    ```

### 2.2. 春日部つむぎ (Kasukabe Tsumugi)
- **Character & Voice IP:** 春日部つむぎ公式 (Kasukabe Tsumugi Project)
  - Guidelines: [春日部つむぎ利用規約](https://tsumugi-official.studio.site/rule)
- **Voice Synthesizer:** VOICEVOX (VOICEVOX:春日部つむぎ)
- **Recommended Standing Art:** 春日部つむぎ公式 立ち絵素材
  - Terms: 二次配布禁止.
  - Setup: Place PSD at `~/Pictures/春日部つむぎ立ち絵素材/春日部つむぎ立ち絵素材.psd` or set `VERAXI_TSUMUGI_PSD`.

---

## 3. Background Music (BGM) & Sound Effects

### 3.1. Explainer BGM (e.g. 2:23 AM)
- **Composer:** しゃろう (Sharou)
- **Source:** DOVA-SYNDROME / YouTube
- **Terms:** [DOVA-SYNDROME 音源利用規約](https://dova-s.jp/_contents/agreement/)
  - 音源ファイル自体の再配布、転載、販売は禁止されています。
  - Video producers should obtain their preferred BGM directly and place it in `assets/bgm/2_23_AM.mp3` or configure in `script.json`:
    ```json
    { "bgm": "path/to/your/bgm.mp3" }
    ```

---

## 4. YouTube Mandatory Credits Template (クレジット表記)

When deploying produced videos to YouTube, include the following credits in the video description:

```text
【音声】
VOICEVOX: ずんだもん
VOICEVOX: 四国めたん
VOICEVOX: 春日部つむぎ
https://voicevox.hiroshiba.jp/

【キャラクター立ち絵】
ずんだもん / 四国めたん: 坂本アヒル様
春日部つむぎ: 春日部つむぎ公式様

【音楽・効果音】
しゃろう様 - 2:23 AM (DOVA-SYNDROME)
https://dova-s.jp/
```
