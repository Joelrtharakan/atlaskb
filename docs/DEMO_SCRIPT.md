# AtlasKB Demo Script

Seven scenarios over the Northwind Robotics corpus (`eval/corpus/`), each
demonstrating one Trust Layer capability. **Every scenario below was actually
run against the live backend (local Ollama, `qwen2.5:3b`) while writing this
script** — the expected-behavior text describes what was *observed*, not what
was aspired to. Two scenarios needed their expectations corrected after the
first live run; that's recorded below rather than smoothed over.

**Corrections made while building this script, disclosed rather than
silently fixed**: the phase spec this script was written for claimed a
restricted "executive comp" document already existed in the corpus and could
be reused — it didn't (confirmed by listing `eval/corpus/` before writing
this). Built `northwind-exec-comp.md` for scenario 6. Also, scenario 2
(asking "what did the old version say" *directly in chat*) is **not** how
this demo works — Phase T9.3's adversarial testing found that chat retrieval
is always scoped to the current version only, so a direct historical
question gets a safe refusal, not the old content (an accepted, documented
limitation — see `eval/REPORT.md`). This script demos version history through
the surface that actually works for it — the document's version list — not
through a chat question that doesn't.

## One-time setup

1. Create (or reuse) a demo workspace as an admin user.
2. Upload every file in `eval/corpus/` (9 documents as of this writing:
   `zubrowka.md`, `grand-budapest.md`, `atlaskb-architecture.md`,
   `atlaskb-billing.md`, `northwind-pto-hr-policy.md`,
   `northwind-pto-eng-handbook.md`, `northwind-allhands-2025-04.md`,
   `northwind-exec-comp.md`, `northwind-onboarding-checklist.md`). Wait for
   all to reach `ready`.
3. **Restrict `northwind-exec-comp.md`** to the admin role: open its Access
   panel (or `PATCH /documents/{id}/access`) and grant `role: admin` only.
4. **Create a real second version** of the onboarding checklist: re-upload
   `northwind-onboarding-checklist.md` (same filename) with this v2 content —
   ```markdown
   # Onboarding Checklist — New Hires

   *Owner: People Operations. Last revised: 2026.*

   New hires should complete onboarding within their first 10 business days:
   workstation setup on day 1, access provisioning by day 3, a team
   introduction session by day 5, and a 30-day check-in with their manager.
   ```
   Confirmed via `GET /documents/{id}/versions`: 2 versions exist, v1
   superseded ("5 business days"), v2 current ("10 business days").
5. **Backdate the Engineering handbook** so it reads as stale/unverified —
   a demo-setup step, not something AtlasKB does automatically (real
   staleness accrues from real elapsed time; this fast-forwards it for a
   rehearsable demo). Run once, before rehearsing:
   ```sql
   UPDATE documents SET created_at = now() - interval '200 days'
   WHERE filename = 'northwind-pto-eng-handbook.md' AND workspace_id = '<your demo workspace id>';
   ```
   Do not call `/verify` on this document — leave `last_verified_at` null.
6. Add a second, non-admin (viewer) user to the same workspace via a real
   invite (`POST /workspaces/{id}/invites` → accept), for scenario 6.

## The seven scenarios

### 1. Normal RAG with citations
**Ask**: *"What is the capital of Zubrowka?"*
**Observed**: Answerable. "The capital of Zubrowka is Lutz." One citation,
one document (`zubrowka.md`). Exactly as expected — the clean baseline case.

### 2. Versioning — real history, not a chat trick
**Ask**: *"What's our new-hire onboarding checklist?"*
**Observed**: Answerable, reflects the **current** (v2) content — 10 business
days, includes the 30-day check-in — cited from the onboarding document only.
**Then, without asking chat**: open that document's detail page (or
`GET /documents/{id}/versions`) to show two real versions: v1 (superseded,
"5 business days") and v2 (current, "10 business days") — created by an
actual re-ingestion in setup step 4, confirmed via a live API call, not two
similarly-named files.
**Corrected expectation**: the *answer* stayed correctly scoped to the
onboarding document, but on the full 9-document corpus this question's
broader retrieval pass also pulled in PTO-related chunks, and the
conflict-detection banner ("Sources disagree: PTO Policy") appeared even
though it's irrelevant to what was asked. This is real, observed behavior —
retrieval precision on a small, generic-embedding corpus isn't perfect, and
conflict detection runs on everything *retrieved*, not just what's *cited*.
Narrate this openly if it happens rather than acting surprised: it's a
genuine, disclosed limitation (see `eval/REPORT.md`'s T9.2 ablation — this is
exactly the kind of retrieval-precision effect that study measured).

### 3. Conflict detection
**Ask**: *"How much PTO do employees get?"*
**Observed**: `conflicts` is non-empty — a "Sources disagree" banner names
the HR vs. Engineering Handbook disagreement. **Corrected expectation**: the
*answer text itself* did not always blend both figures — in the confirmed
run it stated only the HR figure (1.5 days/month, 18-day cap) without
mentioning Engineering's unlimited policy in the same sentence. The conflict
is still correctly surfaced as its own signal (independent of which source
the prose happens to lead with) — don't promise the audience the answer text
will read as a synthesis; the reliable part is the banner.

### 4. Staleness
**Ask**: *"What is the Engineering team's time off policy?"*
**Observed**: Answerable, cites only `northwind-pto-eng-handbook.md`
(evidence: `staleness: 1.0`). **Corrected expectation**: in earlier testing
(Phase T9.6) this question's answer carried an explicit text caveat
("according to an older, unverified document…"); re-run three times while
finalizing this script, it did not. The underlying signal is solid and
reliable — the evidence panel and the Atlas both correctly show this source
as stale (T9.6's brass-ring fix) regardless of the answer text — but whether
the *prose itself* adds a caveat sentence depends on exactly which chunks
land in the model's context, and isn't guaranteed on every run with the
local 3B model. Demo the evidence panel and Atlas staleness ring as the
reliable proof point; treat an in-prose caveat as a bonus if it appears, not
the headline.

### 5. Multi-hop reasoning
**Ask**: *"What retrieval method does AtlasKB use, and how many free queries
does it include per month?"*
**Observed**: Answerable, cites **both** `atlaskb-architecture.md` and
`atlaskb-billing.md`, 2 separate citation entries — one per claim, not one
blanket citation (Phase T2's claim-level citations, working as designed).
Same retrieval-precision note as scenario 2 applies: an unrelated "PTO
Policy" conflict banner may also appear on this corpus size.

### 6. Permission-restricted question
**Ask, as the viewer user from setup step 6**: *"What is the executive
compensation figure?"*
**Observed**: Not answerable — 0 citations, 0 documents cited. Confirmed the
rigorous way in earlier phases (T9.1/T9.3): the restricted chunk never
appears in this user's retrieved results at all, not just omitted from the
answer text.
**Then ask the same question as the admin user**: Answerable, cites
`northwind-exec-comp.md`, states the $6.8M figure correctly.

### 7. Genuinely unanswerable question
**Ask**: *"What is the boiling point of water at sea level?"*
**Observed**: Not answerable. "I cannot answer this question from the
available documents." No fabrication, no citations. Exactly as expected —
the second clean baseline case, bookending the conflict/staleness noise in
the middle scenarios.

## Honest summary

Scenarios 1, 6, and 7 are fully deterministic and reliable — lead or close
with these. Scenarios 2, 3, 4, and 5 all demonstrate real, working Trust
Layer capabilities (versioning, conflict detection, staleness, claim-level
citations), but on this 9-document demo corpus with the local 3B model, the
exact wording and whether an unrelated conflict banner also appears is not
perfectly deterministic run to run. That variability is itself consistent
with — not contradicting — what T9.1/T9.2's measured numbers already showed
(conflict-detection accuracy ~25–75% depending on configuration, not 100%).
Re-run this script before any live demo to know what today's exact wording
will look like; don't assume last week's rehearsal transcript is this week's.
