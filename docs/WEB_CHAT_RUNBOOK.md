# Web-Chat Fallback Runbook

You are here because the agentic tools (Antigravity / Claude Code) are
out of quota. Everything below works with a plain web chat — Muse,
Gemini web, or Claude web — plus this repo's CLI. You are the transport
layer: you copy bundles out, paste them into the chat, save the reply,
and apply it locally. The tooling is built to fail loudly instead of
corrupting files, so a rejected reply is normal workflow, not an error
to work around.

## Golden rules

1. Never edit the reply by hand to "fix" a rejection. Re-prompt with
   the block the tool prints — it names the exact problem.
2. Never paste secrets, API keys, or local machine paths into a web
   chat. The bundle does **not** redact anything — it embeds the
   packed files and raw test output verbatim, and test output can
   contain absolute paths. Review the bundle before you paste it.
3. Complete files or exact anchored edits only. No "rest unchanged",
   no summaries of code — the guards reject them anyway.
4. One task per chat session where possible. Long chats drift; the
   session-start paste (below) re-anchors a fresh one in seconds.

## 1. Start a session

```powershell
veraxi-ymmp session-start > session-start.txt
```

(On a checkout where the command is not recognized, use the
fallback below — it is the same content minus the live git state.)

Open the file, copy everything, and paste it as the first message of
the web chat. It contains the slim rules (`AGENTS_WEB.md`), the
current git state, open TODOs, and the exact commands for the session,
so the model starts oriented instead of guessing.

If `session-start` is unavailable for any reason, paste `AGENTS_WEB.md`
itself as the first message and state the task in one or two sentences.

## 2. Code task loop

### 2.1 Pack the task

Full-file mode (default; best for small files that already exist —
`pack` cannot include a file that is not on disk yet; new files
arrive via the reply and are admitted with `--allow-new`, below):

```powershell
veraxi-ymmp pack --task "Fix the retry backoff in the fetcher" `
  --files veraxi_ymmp/app/fetcher.py tests/test_fetcher.py `
  -o bundle.md
```

Edit mode (best for files over ~400 lines — `pack` hints at it):

```powershell
veraxi-ymmp pack --mode edit --task "Extract the retry helper" `
  --files veraxi_ymmp/app/pipeline.py -o bundle.md
```

Copy the whole bundle into the web chat.

### 2.2 Save the reply

Save the model's entire reply to a file, exactly as received —
`reply.md` for full mode, `reply-edit.md` for edit mode. Do not trim
the code fences or the `===END OF REPLY===` marker.

### 2.3 Apply

Full mode (always pass the manifest written next to the bundle):

```powershell
veraxi-ymmp apply reply.md --manifest bundle.md.manifest.json
```

Edit mode:

```powershell
veraxi-ymmp apply-edit reply-edit.md
```

Outcomes:

- **Success** — the changes land on a new branch, checks run, and the
  diff summary prints. Review with `git diff` / your editor, merge
  the branch when satisfied.
- **Rejected, nothing written** — the tool prints a re-prompt block.
  Copy that block into the chat; the model re-sends a corrected reply.
  Save it over the old reply file and apply again. Common causes and
  what the model must do:
  - *stale base / base drifted* — the file changed since packing.
    Re-pack (step 2.1) and paste the fresh bundle; do not force.
  - *elision detected* — the reply contains "rest unchanged"-style
    shortcuts. The re-prompt names the lines; demand complete files.
  - *shrink guard* — a file came back suspiciously shorter. If the
    shrink is genuinely intended, say so in the chat and re-apply
    with `--allow-shrink`; otherwise re-prompt.
  - *file not in manifest* — the reply touched an unlisted file.
    For a file that exists in the repo, pack a new bundle that
    includes it. For a genuinely new file, re-apply with
    `--allow-new <path>` (`pack` cannot include it — it is not on
    disk yet).
  - *SEARCH matches 0 / N places* (edit mode) — the anchor text does
    not match the file exactly once. Re-prompt with the re-prompt
    block; the model must quote the file's current text verbatim.
  - *unclosed wrapper / incomplete reply* — the paste was truncated.
    Re-copy the reply from the chat in full and apply again; if the
    chat itself truncated it, ask the model to split the reply.

### 2.4 Continue or finish

For the next task in the same session, pack a fresh bundle and repeat
from 2.1. When the session gets long or confused, start a new chat
and repeat section 1 — nothing is lost; the repo is the memory.

## 3. Video task loop (Zero-Quota NotebookLM + Web-Chat Golden Path)

### 3.1 Ideate & NotebookLM Evidence Extraction

1. Scaffold the project dossier and resolve primary source filings:

```powershell
veraxi-ymmp ideate "Your Topic Here" --archetype post_mortem
```

2. Open `projects/<slug>/notebooklm_dossier.md`, upload the primary source filings/documents to **Gemini NotebookLM**, and run Turns 1–4.
3. Save the resulting Turn 4 Forensic Evidence Extraction Matrix table as `projects/<slug>/evidence.md`.

### 3.2 Script & B-roll Generation in Web Chat

Run the manual handoff command against your NotebookLM evidence table:

```powershell
veraxi-ymmp ingest-script projects/<slug>/evidence.md --provider manual
```

This writes `projects/<slug>/script_prompt.md` (embedding your verified NotebookLM evidence, `UNIVERSAL_AI_PROMPT.md`, and the JSON Schema) and waits for your paste. Copy `script_prompt.md` into **Gemini Web, Claude Web, or ChatGPT**, then paste the reply back and terminate with `---END---`.

The expected reply is a single JSON object:

```json
{"script": [ ... ], "broll_manifest": [ ... ], "thumbnail_config": { ... }}
```

Older reply shapes (a bare array, or an array with appended b-roll entries) are also accepted — ingest normalizes them — but the object shape is the contract to ask for.

During handoff, the CLI automatically runs **cut-length, unmapped ASCII/ruby, B-roll cognitive load, retention pacing (>= 80), and fact-parity** checks. If anything fails, it prints an `LLM RE-PROMPT BLOCK` to paste back into the web chat without writing broken files. Once valid, it automatically writes `script.json`, `broll_manifest.json`, `thumbnail_config.json` (if provided), and `claims.json`.

### 3.3 Validate, Build, and Multimodal QA

Run the local compiler pipeline (zero AI quota required):

```powershell
veraxi-ymmp validate projects/<slug>/script.json --audit-facts --audit-pacing
veraxi-ymmp run projects/<slug>/ --render-video --normalize-loudness
veraxi-ymmp qa projects/<slug>/
```

Slides render automatically from `broll_manifest.json` (`type`: `metric`, `vs`, `overview`, `official_data`, etc.). You do **not** need custom video clips.

### 3.4 (Optional) Custom Video Clips from a Web App

> **Optional step:** Video clip ingestion (`ingest-clips`) is **not required** for standard slide/infographic videos. Only use this if you specifically want to overlay external AI-generated video clips (`clip_id`) onto timeline cuts.

1. Generate the clips in the web AI app from the script's clip descriptions.
2. Download them into one folder (names do not matter yet).
3. Have the web chat produce the clip manifest: a JSON list mapping each `clip_id` from the script to the downloaded filename, in script order.
4. Ingest by manifest — matching is by the manifest, not by probing or guessing:

```powershell
veraxi-ymmp ingest-clips downloads/ --from-manifest clip-manifest.json
```

Manifest ingest is all-or-nothing: missing or unmatched files are reported by name, and if any declared clip then fails to read or normalize, the whole ingest aborts and writes nothing. Fix what the messages name and re-run; do not hand-edit `clips/manifest.json`. (Without `--from-manifest`, `ingest-clips` probes every video in the folder with ffprobe.)

## 4. When something else goes wrong

| Symptom | Action |
|---|---|
| Bundle is huge / chat refuses it | Split the task; pack fewer files; use `--mode edit` for big files. |
| Model keeps returning summaries instead of files | Re-paste the bundle's Reply Format section and the re-prompt block; start a fresh chat if it persists. |
| `apply` warns "no manifest" | You packed without `-o` or lost the sidecar. Re-pack with `-o bundle.md` so the guards can protect you. |
| Checks fail after a successful apply | The branch holds the change; fix forward with another pack/apply round describing the failing check output (paste it into the chat). |
| Chat session lost mid-task | New chat, section 1, re-pack the current file state — bundles always reflect the files on disk now. |

## 5. What the tooling guarantees

- A malformed or truncated reply writes **nothing** and creates
  **no branch**.
- Full-mode `apply --manifest` also rejects a stale base and writes
  **nothing**; without `--manifest` that check is skipped.
- Edit mode has no manifest or base-hash check: it rejects a reply
  whose SEARCH text no longer matches exactly once, but an edit
  whose SEARCH text still matches applies even if other parts of
  the file changed since packing. That is by design — the anchor
  *is* the context — but re-pack before editing a file you know
  changed elsewhere.
- Edits apply all-or-nothing: every anchor must match exactly once.
- Japanese text and each file's existing line endings survive the
  round trip byte-exactly outside the edited spans.
- Every rejection prints a re-prompt block written for the model,
  not just an error for you.
