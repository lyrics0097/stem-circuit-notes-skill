# STEM Circuit & Notes Skill (`stem-circuit-notes-skill`)

> **Maintenance Policy (Released As-Is)**
>
> This repository is shared freely under the MIT License **as-is** for community reference and self-hosted customization. Issues, Discussions, Wiki, and Projects are intentionally disabled, and there is no active maintenance commitment or support SLA. Feel free to fork and adapt it for your own courses and AI coding assistants.

[中文文档 (README_ZH.md)](./README_ZH.md)

A self-contained, bilingual (Chinese & English) AI Agent Skill pack for **STEM exam-targeted self-study, lecture note review, textbook-standard vector circuit/physics diagrams, static CSS review boards, offline interactive quizzes, and deterministic quality gates**.

Built around the **Code-as-Memory** pattern: instead of stuffing fragile styling and quiz rules into long prompts, layout templates (`resources/*.html`) and a fast (<50 ms) deterministic linter (`scripts/notes_quality_gate.py`) enforce publication-grade typography, pure SVG diagrams, balanced multiple-choice options, and zero-network offline persistence automatically.

---

## Features

- **Cross-Agent Compatible**: Standard `SKILL.md` YAML frontmatter + self-contained `resources/` and `scripts/` folders. Works out of the box with **Qoder CLI**, **Claude Code**, **Cursor**, **Codex**, and any agent that reads project skills.
- **Bilingual Self-Contained Skill Variants**:
  - `skills/stem-notes-zh/` — Chinese STEM skill following **GB/T 4728** rectangular resistor & national-standard circuit conventions.
  - `skills/stem-notes-en/` — English STEM skill following **IEEE / IEC** circuit & physics diagram conventions.
- **Four Standalone Workspace Deliverables (Zero Backend Required)**:
  - `board.html` — Three-in-one study review board with pure-CSS radio tabs & checkbox flashcards (works even in script-restricted previewers) plus progressive `localStorage` state persistence.
  - `diagrams/fig_*.html` — Standalone, high-DPI pure-SVG circuit and geometric field diagrams with legend strips and collision-checked symbol labels.
  - `quiz.html` — Interactive variant quiz with per-question immutable lock after answering, a **"Don't Know"** button, instant option-level diagnostics, live score tracking, and a **`localStorage`-backed Mistake Notebook** (100% offline, zero external requests).
  - `notes.md` — Clean Markdown + LaTeX archive notes guarded against common parser pitfalls (prime-sign leaks, raw pipe `|` inside GFM table math, unsupported table macros).
- **Deterministic Quality Gate (`scripts/notes_quality_gate.py`)**:
  - Validates SVG purity (no HTML tags inside `<svg>`, concise labels, zero `<text>` coordinate overlap, one deterministic topology per figure).
  - Validates print-grade HTML math (blocks raw `^`, `_`, and unescaped `\frac` leaks).
  - Validates quiz integrity (2x2 compact option grid, 4 balanced options, no single-option parenthetical spoilers, immutable CSS lock, offline `localStorage` persistence, circuit diagrams required for circuit-topology questions).
  - Validates Markdown LaTeX safety and zero-leak output hygiene.

---

## Repository Structure

```text
stem-circuit-notes-skill/
├── LICENSE
├── README.md
├── README_ZH.md
└── skills/
    ├── stem-notes-zh/                     # Chinese STEM Skill (GB/T 4728 circuit standard)
    │   ├── SKILL.md
    │   ├── resources/
    │   │   ├── board_template.html
    │   │   ├── quiz_template.html
    │   │   └── svg_diagram_template.html
    │   └── scripts/
    │       └── notes_quality_gate.py
    └── stem-notes-en/                     # English STEM Skill (IEEE/IEC circuit standard)
        ├── SKILL.md
        ├── resources/
        │   ├── board_template.html
        │   ├── quiz_template.html
        │   └── svg_diagram_template.html
        └── scripts/
            └── notes_quality_gate.py
```

---

## Quick Installation

Clone the repository and copy the language variant you want into your agent's skill directory.

### Qoder CLI / Qoder IDE (Project-Level)

```bash
git clone https://github.com/lyrics0097/stem-circuit-notes-skill.git

# Chinese STEM skill
mkdir -p .qoder/skills
cp -r stem-circuit-notes-skill/skills/stem-notes-zh .qoder/skills/

# Or English STEM skill
cp -r stem-circuit-notes-skill/skills/stem-notes-en .qoder/skills/
```

Windows PowerShell:

```powershell
git clone https://github.com/lyrics0097/stem-circuit-notes-skill.git
New-Item -ItemType Directory -Force -Path ".qoder\skills" | Out-Null
Copy-Item -Recurse -Force "stem-circuit-notes-skill\skills\stem-notes-zh" ".qoder\skills\stem-notes-zh"
```

### Claude Code / Cursor / Codex

Copy either `skills/stem-notes-zh` or `skills/stem-notes-en` into the corresponding skill directory used by your tool:

- **Claude Code**: `.claude/skills/stem-notes-en/` (or `stem-notes-zh/`)
- **Cursor**: `.cursor/skills/stem-notes-en/` (or `stem-notes-zh/`)
- **Codex**: `.codex/skills/stem-notes-en/` (or `stem-notes-zh/`)

---

## Usage Example

After copying a skill folder into your workspace, ask your AI agent to teach a STEM topic and generate the study package:

```text
Use the stem-notes-en skill to walk through a classic NPN BJT voltage-divider
common-emitter amplifier (DC Q-point estimation and small-signal voltage gain Av).
Generate board.html, diagrams/fig_01_bjt_ce.html, quiz.html, and notes.md,
then run the quality gate script to verify all outputs.
```

Run the deterministic quality gate manually at any time (Python 3.10+, standard library only):

```bash
python .qoder/skills/stem-notes-en/scripts/notes_quality_gate.py .
```

Open `board.html`, `diagrams/fig_*.html`, and `quiz.html` directly in any modern browser — no web server or internet connection required.

---

## License

MIT License — Copyright (c) 2026 [lyrics0097](https://github.com/lyrics0097).
