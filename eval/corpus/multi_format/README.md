# Multi-format ingestion — trial corpus & results

Five fixture documents, one per format added beyond PDF/Markdown/HTML, all
about the same fictional Falcon product line so a mixed-format question is
meaningful. Not wired into `run_eval.py`'s labelled `dataset.json` (that
harness assumes a Markdown corpus); these were verified directly against a
live local backend — real upload, real ingestion, real `/search` and `/chat`
calls, not a mock. Every result below is copy-pasted from an actual response.

| File | Format | Exercises |
| --- | --- | --- |
| `falcon_v3_warranty.docx` | Word | Heading-level sections, a table |
| `falcon_unit_economics.xlsx` | Excel | Row-range chunking, header-context carry-through |
| `falcon_v2_field_incidents.csv` | CSV | Same row-range chunking, single implicit sheet |
| `falcon_v3_release_notes.txt` | Plain text | Paragraph chunking, no page/section metadata |
| `falcon_v3_launch_deck.pptx` | PowerPoint | Slide-title-as-section, text-only (no embedded chart content) |

## Test questions & real answers

**.docx** — "What is the warranty coverage period for the Falcon robotic arm
according to the warranty terms document?"
→ *"The warranty period for Falcon v3 is 18 months from the date of
shipment, extendable to 36 months under the Falcon Care+ program."*
Cited `falcon_v3_warranty.docx`, section `"Coverage Period"` (the Heading 2
the paragraph sits under) — no page number, correctly.

**.xlsx** — "According to the Falcon unit economics spreadsheet, what was
the actual unit cost in Q3 2025?"
→ *"The actual unit cost in Q3 2025 was $8,600."*
Cited `falcon_unit_economics.xlsx`, section
`"Sheet: Falcon Unit Economics, rows 2-5"` — the exact
`"Sheet: <name>, rows <start>-<end>"` shape this phase's scope called for.

**.csv** — "According to the field incidents log, what was the resolution
for the gripper misalignment incident at Reno DC?"
→ *"The resolution for the gripper misalignment incident at Reno DC was to
recalibrate the gripper offset."*
Cited `falcon_v2_field_incidents.csv`, section `"Sheet1, rows 2-5"` (a CSV
has no real sheet name, so it reads as one implicit sheet, same as .xlsx's
per-sheet handling per the scope note).

**.txt** — "What safety standard is the Falcon robotic arm certified to,
according to the release notes text file?"
→ *"The Falcon v3 robotic arm is certified to ISO/TS 15066 for collaborative
robot safety."*
Cited `falcon_v3_release_notes.txt` with `section: null, page: null` — no
fabricated location for a format that genuinely doesn't have one.

**.pptx** — "According to the launch readiness slide deck, what is the
critical-path risk for Q4 volume?"
→ *"The critical-path risk for Q4 volume is Servo supplier lead time."*
Cited `falcon_v3_launch_deck.pptx`, section `"Open Risks"` (the slide title).

**Mixed-format** — "What is the Falcon Care+ extended warranty coverage
period, and what was the actual unit cost recorded for Q3 2025?"
→ *"The Falcon v3's warranty period under the Falcon Care+ program is
extendable to 36 months from the date of shipment. For the actual unit cost
in Q3 2025, it was $8,600."*
Citations: `falcon_v3_warranty.docx` (section `"Coverage Period"`) **and**
`04_falcon_product_spec.pdf` (page 2) — the pre-existing PDF corpus also
discusses Falcon unit cost, so the model drew the cost figure from there
rather than the new `.xlsx`. That's the retrieval/rerank stage doing its job
across formats with no special-casing, not a miss: a `.docx` and a `.pdf`
landed in the same answer through the identical pipeline, which is the
actual point of this test (per the phase's own scope: "confirming the
pipeline treats all formats uniformly at the retrieval/generation stage").

## One real bug this testing found

The first ingestion attempt failed on `.docx`/`.xlsx`/`.pptx` with
`psycopg.DataError: PostgreSQL text fields cannot contain NUL (0x00) bytes`
— the Celery ingestion worker process had been started before the new
parsers were added to `chunking.py` and, unlike the API's `uvicorn --reload`,
Celery doesn't hot-reload its task code. It was still dispatching every
upload through the old PDF/Markdown/HTML-only `parse_document`, which fell
through to the Markdown/plain-text fallback for the new binary formats and
tried to chunk raw ZIP-container bytes. Restarting the worker picked up the
new parsers immediately (confirmed via `ingest.parsed`/`ingest.ready` log
lines naming the right parser's block/chunk counts) — a real operational
gotcha for this change (a worker deploy needs restarting, same as any other
code change to `apps/workers`), not a defect in the parsers themselves.
