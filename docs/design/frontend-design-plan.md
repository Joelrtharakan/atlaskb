# AtlasKB — Frontend Design Plan

**Status: proposed (plan only, awaiting approval). No components built.**

Governing concept: **cartography of knowledge.** Documents are territory being
surveyed and mapped; asking a question is navigating that map and watching a
route light up between the places that answer you. Every design decision below
serves the metaphor of a *working map sheet* — neatline borders, a title block,
graticule ticks, surveyor's marginalia, and a living survey field — not a
generic SaaS dashboard.

---

## 1. Color token system

Six named tokens. Three neutrals (ink / paper / slate), one muted house metallic
(structural chrome + interactivity), and **two reserved luminous state colors**
that appear *nowhere else* so their presence carries meaning.

| Token          | Hex       | Role | Usage rule |
| -------------- | --------- | ---- | ---------- |
| `atlas-ink`    | `#16232B` | Cool near-black. Primary text, strokes, node cores on the map. | Everywhere text/marks are needed. |
| `chart-linen`  | `#D9DCD1` | App background — a **cool sage-linen** paper (green-grey cast, deliberately *not* cream). | Base surface. Panels use the same token at ~92% over ink for depth — no extra token. |
| `graphite`     | `#515C63` | Slate. Secondary text, hairline contour rules, neatlines, **latent (quiet) map threads**. | Structure and de-emphasis. |
| `pewter`       | `#8793A0` | House metallic — cool, low-chroma steel (drafting instruments). Interactive chrome: buttons, borders, focus rings, dividers, hover. | The *only* interactive accent. Low chroma so it reads as "UI metal," never as a signal. |
| `beacon`       | `#E8A22B` | **RESERVED STATE — "retrieval in progress / citations active."** Warm amber lamp. | ONLY on: citation chips, source markers, the retrieval progress indicator, and the map nodes being retrieved. It is the single warm-saturated color in the whole UI, so it always means *"a source is live."* |
| `meridian`     | `#22B2A6` | **RESERVED STATE — "the 3D connection threads."** Luminous verdigris-cyan. | ONLY on threads in the Living Atlas that are *actively carrying a retrieval*. Never appears in 2D UI. |

**Why the two states stay legible:** `pewter` is cool and desaturated (chrome),
`beacon` is the lone warm-saturated hue (~42°), `meridian` is a cool luminous
teal (~176°). Three well-separated hue/chroma regions means a user never
confuses "the lamp is lit" (beacon) or "a route is live" (meridian) with
ordinary interface metal. Latent map structure is drawn in **graphite**, not
meridian — a thread only turns meridian at the instant it carries an active
connection, which is what makes the light mean something.

Contrast note: `atlas-ink` on `chart-linen` is very high contrast (good body
legibility). `beacon` and `meridian` are used as fills, glows, and markers with
ink text on top — never as small colored text on linen.

---

## 2. Typography

An **instrument family** logic: the body and mono faces share a skeleton so a
number set in mono reads like the *same instrument's readout* — surveyor's
marginalia — while the display face is a separate, editorial "atlas plate" voice
used sparingly.

- **Display — `Fraunces` (variable), headings only, used sparingly.**
  Old-style, optical-size-aware, with its *soft* and *wonk* axes dialed in for an
  engraved-almanac character. Set at a **low-contrast optical size** and tracked
  like a map cartouche (all-caps eyebrows; title-case H1). Intentionally *not* a
  sharp Didone. Never used for body or UI labels.
- **Body — `IBM Plex Sans`.** Humanist but engineered — reads like precise
  drafting/instrument labeling. Long-form answers, prose, buttons, nav.
- **Mono — `IBM Plex Mono`, reserved for data/system facts.** Chunk IDs
  (`c7f3-0421`), costs (`$0.0032`), latency (`412 ms`), timestamps, tenant IDs,
  token counts — **always** mono, **always** tabular figures, tinted graphite or
  ink. Because Plex Sans and Plex Mono share a skeleton, these numbers feel like
  annotations pencilled onto the same chart, not generic UI chrome. **Rule: the
  body face never renders a raw system number; if it's a fact the system knows,
  it's mono.**

Fallback stacks: display → `Fraunces, "Times New Roman", serif`; body →
`"IBM Plex Sans", system-ui, sans-serif`; mono →
`"IBM Plex Mono", ui-monospace, monospace`.

---

## 3. Layout concepts

Neither page is a centered hero with a card. Both are composed like an actual
map sheet: a **neatline** (thin framing border), **graticule ticks** along the
edges, an asymmetric **title block**, and mono marginalia in the corners.

### 3a. Landing page — "the plate"

The Living Atlas is the *field* of the page: a near-full-bleed ambient
constellation drifting behind a thin brass/pewter neatline. Text is anchored to
the **left margin as a cartouche** (a map's title block) — one-liner, a two-line
manifesto, and a single **engraved label link** ("→ Enter the atlas") rather
than a big pill CTA. Top-left: a small compass logo mark + wordmark. Bottom-left:
a **mono scale-bar strip** carrying real build metadata. No centered stack, no
card, no gradient blob — the "hero" is a truthful rotating data field, and the
copy sits in the margin the way a legend sits on a map.

```
┌─ neatline ─────────────────────────────────────────────────────────┐
│ ◈ ATLASKB                                          graticule ticks ⌐ │
│                              · ·  ✦  · ·                             │
│  ┌ cartouche (title block) ┐   ·   ╲   ·                             │
│  │ Chart your organization │  ·  ✦───·───✦  ·      ← Living Atlas:   │
│  │ 's knowledge.           │     ·   |   ·           nodes drifting, │
│  │                         │       · ✦ ·             faint graphite  │
│  │ two-line manifesto…     │      ·     ·            threads, slow   │
│  │                         │   ·    ·  ·             ambient spin,   │
│  │ → Enter the atlas       │        · ·              full-bleed      │
│  └─────────────────────────┘                                        │
│                                                                     │
│ status: scaffold · build 0.0.0 · pg 15432 · redis 6380  ← mono strip│
└─────────────────────────────────────────────────────────────────────┘
```

### 3b. In-app chat page — "the survey table"

Three co-equal zones under one neatline — **not** sidebar-plus-cards. The map is
not a decorative side panel; it is the spatial counterpart to the text and holds
roughly equal weight.

- **Left — Index Rail (quiet):** tenant switcher and document "territories" as a
  plain hairline-ruled list with mono labels. Deliberately still (see §6).
- **Center — Field Journal (transcript):** Q&A rendered as dated log entries, not
  chat bubbles or cards. Each entry has a **mono margin** carrying its timestamp,
  chunk IDs, cost, and latency — surveyor's annotations. Citations inline are
  **beacon** chips.
- **Right — Living Atlas (docked, persistent):** the same 3D field as the
  landing page, now wired to real retrieval (see §4). Beacon chips in the
  transcript correspond one-to-one with nodes lighting in the map.
- **Bottom — the ruled input:** a single ruled line ("write on the chart"); on
  submit its rule animates a travelling **beacon** underline.

```
┌─ neatline ──────────────────────────────────────────────────────────────┐
│ ◈ ATLASKB · acme-corp ▾                                     tokens 12,847 │
├──────────┬────────────────────────────────┬──────────────────────────────┤
│ INDEX    │  FIELD JOURNAL                  │   LIVING ATLAS (docked)      │
│ RAIL     │                                 │                              │
│ ▤ Docs   │ 09:14 ▸ How does billing work?  │        ·    ◍(beacon)        │
│  · spec  │       ┌ answer ───────────────┐ │       ·  ╲                   │
│  · legal │       │ …drawn from your specs │ │      ◍════╗ ← meridian route │
│  · sales │       │ [◍c7f3] [◍a1d0] …      │ │    · ╱    ◍(beacon)          │
│          │       └────────────────────────┘│      ·         ·             │
│ ▤ Tenants│  c7f3-0421 · $0.0032 · 412 ms   │  (camera framed on lit nodes;│
│          │  └──── mono margin ─────         │   inactive nodes dim)        │
│          │ ─────────────────────────────── │                              │
│          │ ask a question ______________ ↵ │                              │
│          │ (ruled input; beacon underline) │                              │
└──────────┴────────────────────────────────┴──────────────────────────────┘
```

---

## 4. Signature element — the "Living Atlas"

Documents are **nodes** in a constellation; **threads** connect related
documents. Node positions come from a precomputed layout of document embeddings
(e.g., UMAP / force layout), so *spatial proximity ≈ semantic proximity* — the
map is truthful, not decorative. Rendered in WebGL (react-three-fiber):
instanced points for nodes, line segments for threads, driven by real retrieval
events streamed from the API.

**Ambient idle state (landing + chat when quiet):** the field rotates very
slowly (~1 revolution / 3–4 min). Nodes are `atlas-ink` cores sized by chunk
count. Latent relationships are drawn as faint **graphite** threads at low
opacity — quiet structure. No beacon, no meridian at rest.

**A question, step by step (chat page):**

1. **Ask.** User types in the ruled input and hits enter. The input's rule
   sprouts a **beacon** underline that begins to travel (a survey line being
   drawn) = *retrieval in progress*. A new question entry appends to the journal
   with a mono timestamp; agent status reads `triangulating…` in mono.
2. **Focus handoff.** The atlas's ambient rotation *damps to near-still* over
   ~400 ms. Ambient motion yields so the meaningful motion can be read — the map
   holds its breath.
3. **Nodes ignite.** As the retriever returns candidate chunks, their parent
   **nodes light `beacon` amber**, ramping in order of arrival/relevance. A small
   mono count ticks up. The camera eases (dolly + slight orbit, ~600–900 ms, no
   bounce) to frame the lit cluster.
4. **Routes light up.** Threads between co-retrieved nodes turn **`meridian`**
   and draw from node to node like plotted routes; thread brightness ∝ retrieval
   weight. This is the map's core promise — the route lighting up.
5. **Answer streams + bidirectional citations.** The LLM streams into the
   journal. Inline **beacon** citation chips appear as sources are used. Reading
   / hovering a citation pulses its node brighter and traces its thread; the link
   between text and map runs both ways. The mono margin shows chunk IDs and a
   running token cost ticking.
6. **Complete.** Final cost + latency print in the entry's mono margin
   (surveyor's annotation). Lit nodes hold beacon briefly, then fade; meridian
   threads dim back to latent graphite over ~1.5 s.
7. **Settle.** The camera pulls back to the establishing wide shot and ambient
   rotation resumes at idle speed. Just-visited nodes keep a **faint beacon rim**
   for the rest of the session — pencil marks left on the chart — so the
   conversation's path across the territory stays legible, optionally
   accumulating into a visible route.

**Reduced-motion mode:** honors `prefers-reduced-motion` — no continuous
rotation; camera *cuts* instead of easing; nodes/threads cross-fade their state
colors. Fully functional, just still.

---

## 5. Self-critique against the three forbidden defaults

Checking explicitly: **(1) cream + high-contrast serif + terracotta** — avoided:
the paper is a *cool sage-linen* (`#D9DCD1`, green-grey — not warm cream); the
display face is Fraunces at a *low-contrast* optical size tracked like a map
cartouche, not a sharp Didone; and there is no terracotta anywhere — the only
warm hues are muted structural `brass/pewter` chrome and the *reserved
functional* `beacon` amber, which is a state signal, not a decorative brand
accent. **(2) near-black + single neon accent** — avoided: the base is a *light*
linen surface, and instead of one neon pop we run a disciplined semantic system
(cool pewter chrome plus two low-frequency, meaning-bearing states); beacon and
meridian are never used as blanket accents. **(3) broadsheet hairline newspaper**
— avoided: although hairlines exist (neatlines, graticule), the governing form is
a *map sheet* with an asymmetric title block and a dominant 3D field plus mono
marginalia; there are no justified columns, drop caps, or rule-separated
headline decks, and the page is spatial rather than editorial-column. It also
sidesteps the *generic sidebar+cards+gradient-blob dashboard*: no card grid, no
gradient blob, and the "hero" / right panel is a truthful data view (the atlas),
not ornament — the chat layout is a survey table, not a widget board.

---

## 6. Where motion must NOT appear

The signature motion earns its meaning by **scarcity**. If everything animates,
the atlas stops signifying "retrieval." So these surfaces stay deliberately quiet
— "the archive / the register": mono-heavy, hairline-ruled tables, instantaneous
(≤100 ms) or no hover states, no rotation, no glow, no beacon/meridian (except a
single *static* legend key), no entrance animations, no parallax:

- Document list / territory index
- Settings
- Member management
- Billing / usage tables
- Auth screens

Even inside the chat page, the transcript text itself does not animate beyond
token streaming; the *only* things allowed to move are the Living Atlas and the
citation↔node coupling. Everything else holds still on purpose.

---

*Next step on approval: lock fonts + tokens into the web app's Tailwind theme,
then build the ambient Living Atlas as an isolated component before wiring it to
retrieval.*
