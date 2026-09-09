# Kivi — UI / Design Specification

**Dark dashboard. Mint accent. Inter throughout.**

This document is the source of truth for what the Kivi front end is, how it is
built, and every token it uses. If you change the look, change this file too.

---

## 1. What we are building

Kivi is a **personal phonetic memory** for speech-to-text. A recogniser mangles
the words that matter to you — your name, your product, your teammates — the
same way every time. Kivi learns *your* mishearings from *your* corrections and
repairs the transcript before you ever see the mistake.

The transcript moves through three levels:

| Level | What it is | Who produces it |
|-------|-----------|-----------------|
| 1 · ASR | raw recogniser output | echo ASR (or Whisper) |
| 2 · Formatted | punctuation, casing, numbers | deterministic rule formatter |
| 3 · Memory-aware | your words restored | the REPLACE / KEEP / DEFER engine |

Every level-3 change is an explainable decision with a reason code, a score, and
a link back to the evidence that justified it. **There is no LLM in the core
path — cost is $0.00 by design**, and that is stated in the UI rather than
buried in a README.

### The three surfaces

| Surface | Job |
|---------|-----|
| **Transcribe** | Speak or type → see the memory-aware line → click any highlighted word to correct it. Corrections feed straight back into memory. |
| **Memory** | The full, auditable state: what Kivi knows, how confident it is, the evidence behind every number, and the accent rules learned from you. |
| **Evaluation** | The committed deterministic run — pass rate, intervention precision/recall, over-intervention count, and the full report. |

---

## 2. Design direction

Two references drive the look:

1. **`github.com/kailash-git/Accenture_AI_Hackathon`** — `css/tokens.css` and
   `css/layout.css`. We inherit its **token architecture** (semantic surface
   ramp, restrained accents, one type scale) and its font, **Inter**.
2. **The Finomic dashboard reference** — a dark, rounded-card financial console.
   We inherit its **layout language**: a labelled sidebar with a filled pill for
   the active item, an avatar/greeting topbar, and a grid of rounded cards
   carrying big numbers, bar lists and a data table.

### Rules this design follows

- **One accent.** Mint. It marks the active nav item, primary buttons, live
  data, and nothing else. Peach appears only in the logo mark and avatar.
- **No monospace in the chrome.** The reference has zero monospace — every
  figure is Inter with `tabular-nums`. A true monospace is reserved for two
  places: the inline `<code>` tag and the evaluation report `<pre>`.
- **One card treatment.** `--bg-card`, 1px `--border`, `--r-card` radius. No
  gradient edges, no per-card decoration, no drop shadows.
- **Numbers are the hero.** Stat trios, big display values and bar lists carry
  the page. Tables are for detail, not for the headline.
- **Colour never carries meaning alone.** Every status badge has a word in it.

---

## 3. Design tokens

All tokens live in `:root` in `frontend/styles.css`. Never hardcode a hex in a
component rule.

### Surfaces

| Token | Value | Used for |
|-------|-------|----------|
| `--bg-app` | `#0b0b0d` | page ground, main pane, report block |
| `--bg-sidebar` | `#0e0e11` | sidebar |
| `--bg-card` | `#141416` | every card |
| `--bg-elevated` | `#1a1a1e` | inputs, icon tiles, chips, inset panels, hover |
| `--bg-pill` | `#1e1e23` | pressed / menu hover |

A three-step ramp: ground → card → elevated. Nothing sits on a fourth level.

### Accent — mint

| Token | Value | Used for |
|-------|-------|----------|
| `--accent` | `#8ce8d0` | active nav fill, primary buttons, bar fills, links, live values |
| `--accent-strong` | `#6fdcbf` | hover on filled accent surfaces |
| `--accent-dim` | `rgba(140,232,208,.12)` | badge / pill backgrounds |
| `--accent-border` | `rgba(140,232,208,.28)` | badge / focus borders |
| `--on-accent` | `#06231d` | text on a mint fill (contrast ≈ 13:1) |

### Secondary + status

| Token | Value | Used for |
|-------|-------|----------|
| `--peach` | `#f5b493` | logo mark, avatar gradient — decorative only |
| `--pos` | `#4ade80` | "firing", online dot, positive deltas |
| `--warn` / `--warn-dim` | `#f5b544` | DEFER, `proposed` status |
| `--neg` / `--neg-dim` | `#f87171` | destructive actions, recording state |

### Text

| Token | Value | Contrast on `--bg-card` | Used for |
|-------|-------|------------------------|----------|
| `--text-1` | `#ffffff` | 18.5:1 | headings, values, term names |
| `--text-2` | `#a9adb6` | 8.4:1 | body copy, nav labels |
| `--text-3` | `#71767f` | 4.6:1 | captions, meta, secondary labels |
| `--text-4` | `#55595f` | 2.9:1 | **decorative only** — section labels, table headers, disabled |

`--text-4` never carries body copy. Everything a user must read is `--text-3`
or lighter.

### Lines, radii, motion

| Token | Value |
|-------|-------|
| `--border` | `rgba(255,255,255,.07)` — card edges, row rules |
| `--border-2` | `rgba(255,255,255,.12)` — inputs, popovers |
| `--r-card` | `18px` |
| `--r-item` | `14px` — nav rows, tiles, inset panels |
| `--r-sm` | `10px` — inputs |
| `--r-pill` | `999px` — buttons, badges, chips, composer |
| `--dur` | `180ms` |
| `--ease` | `cubic-bezier(.2, 0, 0, 1)` |

### Dimensions

| Token | Value |
|-------|-------|
| `--sidebar-w` | `292px` (`84px` when `body.rail`) |
| `--topbar-h` | `84px` |

---

## 4. Typography

**Inter**, weights `400 / 500 / 600 / 700 / 800` — the same set the reference
repo loads. `--code` (`ui-monospace, 'SF Mono', Menlo, Consolas`) is used twice
in the whole app.

| Role | Size | Weight | Colour |
|------|------|--------|--------|
| Stat number (`.stat-row .st b`) | 32px | 700 | `--text-1` |
| Display value (`.display .val`) | 40px | 700 | `--text-1` |
| Eval stat (`.stat .n`) | 24px | 700 | `--text-1` |
| Card title (`.card-h h2`) | 18px | 600 | `--text-1` |
| Sidebar brand | 17px | 700 | `--text-1` |
| Greeting name | 16.5px | 600 | `--text-1` |
| Term name (`.dt-name b`) | 15px | 600 | `--text-1` |
| Nav item | 15px | 400 (600 active) | `--text-2` / `--on-accent` |
| Body / table cell | 14px | 400 | `--text-2` |
| Meta, captions | 13–13.5px | 400 | `--text-3` |
| Section label (`MENU`, `TERM`) | 11px | 600, `1.1–1.3px` tracking, uppercase | `--text-4` |

Every figure carries `font-variant-numeric: tabular-nums` so columns of numbers
do not jitter as they update.

---

## 5. Layout

```
body
└── .app                    grid: var(--sidebar-w) | 1fr   height 100dvh
    ├── aside.sidebar
    │   ├── .side-top       logo · brand · rail toggle          h = --topbar-h
    │   ├── .side-scroll
    │   │   ├── .side-label "MENU"
    │   │   ├── nav.nav     Transcribe · Memory · Evaluation
    │   │   ├── hr.side-div
    │   │   ├── .side-label "SESSION"
    │   │   └── .side-stats live DB counts
    │   └── .side-foot      Reset memory
    └── .main
        ├── header.topbar   avatar · greeting · status pill
        └── .content        the only scroll container
            └── section.view.on
                └── .grid / .card …
```

`.content` owns the scroll. Cards never scroll internally except `.stream`,
which is capped at `46vh`.

### Grid

| Class | Columns |
|-------|---------|
| `.grid.two` | `1.55fr 1fr` — Overview + Accent profile, Evaluation + Cost |
| `.grid.chat` | `1fr 340px` — transcript + session rail |

Both collapse to a single column below **1180px**. Below **900px** the sidebar
becomes a horizontal strip and the session list is hidden.

---

## 6. Components

### Sidebar nav (`.navlink`)
50px tall, `--r-item`, 20px icon + label + caret. Inactive `--text-2` on
transparent; hover `--bg-elevated`; **active is a filled mint pill** with
`--on-accent` text, 600 weight and a visible caret — the signature element of
the reference.

### Topbar
44px avatar with a `--pos` online dot, name + "Hello, welcome back!", and a
status pill on the right reading `local · no model calls · $0.00`.

### Card (`.card`)
`--bg-card`, 1px `--border`, `--r-card`, `24px 26px` padding.
`.card-h` holds an 18px title with either `.meta` (plain caption) or `.pill`
(mint badge) pushed right.

### Stat trio (`.stat-row`)
Three equal cells split by 1px vertical rules, 32px/700 number over a 13px
caption, closed by a bottom rule. Used for Overview and This session.

### Bar list (`.bars` / `.bar`)
`label | track | value` grid. 8px track on `rgba(255,255,255,.06)`, mint fill,
width animated over 500ms. Used for confidence-by-term, accent rules and the
pipeline readout.

### Display value (`.display`)
Small label, 40px/700 value with an optional mint `<em>` suffix, then a note
line where `<b>` renders `--pos`. Used for the strongest accent rule and cost.

### Inset panel (`.inset`)
`--bg-elevated` with a faint mint radial at the top, centred heading + subtitle,
and an optional `.wavefield` — 44 mint bars whose height is driven by the rule
weight. The reference's "Finance Health" block.

### Data table (`.dt`)
`.dt-head` of uppercase 11px labels over `.dt-row` buttons. Each row: 42px icon
tile → name + type → alias chips → mini confidence bar → status badge → chevron.
Rows expand in place into `.mem-body`.

### Badges (`.badge`)
Pill, 12px. `.active` mint, `.proposed` amber, `.contested` red, `.inactive`
grey. The status word is always visible.

### Composer (`.composer`)
Pill-shaped `--bg-elevated` bar: auto-growing textarea, a 13-bar waveform mic
button that animates while recording, and a 42px circular mint send button.

### Word marks (in the transcript)
`.w.rep` mint + 2px mint underline · `.w.def` amber dashed underline ·
`.w.kc` dotted underline · `.w.flash` mint wash on a successful correction.
The "How to read it" legend on the Transcribe page explains all three.

---

## 7. Interaction & accessibility

- **Focus**: `:focus-visible` → 2px mint outline, 2px offset. Never removed.
- **Targets**: nav rows 50px, table rows ~72px, buttons ≥42px.
- **Motion**: one token pair (`--dur` / `--ease`). Only colour, background and
  transform animate. Fully disabled under `prefers-reduced-motion: reduce`.
- **Icons**: single Lucide-style set, 1.7px stroke, `currentColor`. Decorative
  icons are `aria-hidden`; icon-only controls carry an `aria-label`.
- **Expandable rows** set `aria-expanded`.
- **Contrast**: all body text ≥ 4.5:1; `--text-4` is decorative only.

---

## 8. File map

| File | Contents |
|------|----------|
| `frontend/styles.css` | every token and rule — the only stylesheet |
| `frontend/index.html` | markup + all view logic |
| `backend/api/main.py` | HTTP surface; serves `/` and mounts `/static` → `frontend/` |

### JS render functions (`frontend/index.html`)

| Function | Renders |
|----------|---------|
| `setView(v)` | tab switching; calls `loadMemory()` on entering Memory |
| `submit(text)` / `renderTurn` / `wordify` | the transcript and its word marks |
| `applyFix` / `acceptSuggestion` / `observeAndReprocess` | inline correction → `/api/observe` → re-run `/api/process` |
| `loadMemory` | fetches health, decisions, memory list + detail, then calls the three below |
| `renderOverview` | stat trio + confidence bar list |
| `renderAccent` | accent card: display value, inset wavefield, secondary rule bars |
| `renderEntries` / `renderMemBody` | the terms table and its expanded detail |

### API consumed

`GET /api/health` · `POST /api/process` · `POST /api/process-audio` ·
`POST /api/observe` · `GET|POST /api/memory` · `GET|DELETE /api/memory/{id}` ·
`GET /api/phonetic-profile` · `GET /api/decisions` ·
`GET /api/evaluation/results` · `POST /api/admin/reset`

---

## 9. Changing the design

- **Recolour** → edit `:root` only. The accent appears in ~30 rules, all via
  `var(--accent*)`.
- **Add a card** → `.card` + `.card-h`, then compose from `.stat-row`,
  `.bars`, `.display`, `.inset` or `.dt`. Do not invent a new card treatment.
- **Add a nav item** → a `.navlink` with `data-view="x"` and a matching
  `<section class="view" id="view-x">`. `setView` needs no change.
- **Never** add a monospace font to the chrome, a gradient border, a drop
  shadow on a card, or a second accent hue.

Run it with `python manage.py serve` → <http://127.0.0.1:8000>
