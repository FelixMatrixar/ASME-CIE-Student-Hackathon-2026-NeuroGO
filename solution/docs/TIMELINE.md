# Project Timeline — ASME CIE 2026 Hackathon, Problem 1

Chronological record of what was done, what it cost, and what it taught us.
Companion to [FINDINGS.md](FINDINGS.md), which holds the findings themselves;
this file holds the *narrative* — the order things happened in and why each step
followed the last.

> **Gitignored on purpose.** Working notes, not a deliverable. This is the raw
> material for the "how we worked" arc of the presentation and for the Round 2
> methods section, which grades reproducibility and rationale.

**How to use this for the presentation.** The interesting story is rarely the
final architecture — it's the decision points. Entries marked **◆ DECISION**
are the moments where the project could have gone another way, and those are the
slides that make a methods talk worth watching. Entries marked **▲ SURPRISE**
are where the data contradicted an assumption.

Timezone: UTC+07:00. Times before 21:54 are approximate (reconstructed from
session order); later entries are anchored to file and log timestamps.

---

## Session 1 — 2026-08-19 (Wed)

### 21:35 — Repo reconnaissance
Read every file in the contest repo: `README.md`, `validate_submission.py`,
`vocabularies.json`, all four sample submissions, and all four PDFs
(Kickoff, Tutorial, Rubrics, Dataset Description).

The PDFs needed `pymupdf` installed to extract text — no PDF renderer was
available in the environment. The `.pptx` links in the README point at files that
aren't in the repo; the user had already converted them to PDF locally.

**Learned:** full problem shape — three tiers (easy 20 / medium 35 / hard 45),
inputs are BRep + images only, ground truth is deterministic NX output.

### 21:48 — Validator sanity check
Ran `validate_submission.py` against all four provided samples (easy JSON,
medium STL directory, hard tools JSON, hard PTP directory). All four pass on
Python 3.12.8.

**Learned:** the format contract is confirmed working locally, so format errors
later will be ours, not the harness's. Also mapped the validator's quirks: it
dispatches `hard` on whether the path is a file (tools JSON) or a directory
(PTP), and it requires `operation_number` to run 1..N consecutively with
`summary.number_of_operations` matching the array length exactly.

### 21:50 — Environment audit
Python 3.12.8 present; **nothing** installed — no numpy, scipy, trimesh, torch,
sklearn, open3d, or any OpenCascade binding.

Checked disk: **35.5 GB free on C:, the only drive.**

**▲ SURPRISE — the disk is the binding constraint.** The dataset zip is 5.2 GB
and expands to an estimated 25–30 GB. Extracting would leave the machine nearly
full, with no room for the ~90,000 STL and PTP files a full submission generates.

**◆ DECISION — read the dataset from inside the zip, never extract it.**
`zipfile.ZipFile` supports random access via the central directory, so per-part
lazy reads keep the footprint at 5.2 GB. This constrains the whole data pipeline
design and was decided before any of it was written.

### 21:52 — Zenodo record inspected
Queried the Zenodo API for record 21653081. One file: `MachinePlan-10K.zip`,
5,209,843,207 bytes, MD5 `831ccc4bd0ee62759ec383556b8c95da`, CC BY 4.0.

Verified with a probe request that Zenodo honours HTTP `Range` (returned 206
with a correct `Content-Range`), so a resumable download is possible.

**Learned:** resume is safe, so the download can be interrupted at no cost — which
made it reasonable to start it immediately and work alongside it.

### 21:54:01 — Dataset download started (background)
`solution/scripts/download_dataset.py` — resumable, MD5-verified, retries with
backoff, stdlib-only so it runs on a bare machine. Logging to
`solution/logs/download.log`.

Sustained ~2.1 MB/s, ETA ~40 min.

**◆ DECISION — start the download and build the scorer in parallel** rather than
waiting. The scorer needs no dataset: the rubric is fully specified by
Rubrics.pdf, and the contest's own sample files are enough to test against.

### 21:56 — Virtualenv and geometry stack
Created `solution/.venv`, installed numpy 2.5.2, scipy 1.18.0, trimesh 5.0.0,
manifold3d, shapely, rtree, networkx, tqdm.

Verified the boolean backend on a known case: 10×10×10 box minus 5×5×20 box
returned volume **750.0** against an analytic 750, watertight.

**Learned (F-009):** exact mesh booleans are available and trustworthy. This
matters more than it sounds — the top medium band is IoU ≥ 0.999, and voxel IoU
at 1 mm pitch on a 200–500 mm part resolves only to ~1e-3, straddling that exact
boundary. Approximate methods cannot score this rubric.

### 22:00 — Rubric reimplemented
Wrote `machineplan.scoring`: `rubric.py` (all point tables), `easy.py`
(Levenshtein + multiset F1), `geometry.py` (exact volumetric IoU, over/undercut,
removed-volume), `medium.py`, `hard.py`.

**▲ SURPRISE — the rubric doesn't add up (F-006).** "Tool selection (20 points)"
is followed by a table topping out at 10; "Tool path geometry (25 points)" by
tables summing to 30. Band edges are ambiguous too (0.0–0.1 and 0.1–0.2 both
contain 0.1).

**◆ DECISION — score the tables exactly as printed, then rescale to the stated
section budget**, behind a `SCALE_TO_SECTION_BUDGET` flag so the raw numbers stay
inspectable. Boundary values resolve in the participant's favour. Logged as
Q-001 to raise with the organizers rather than silently assume.

### 22:01 — Label space reduced
While writing the vocabulary module, cross-referenced the two frequency tables in
Dataset_Description.pdf.

**▲ SURPRISE — `o1` is redundant (F-001).** `AREA_MILL` (20,067) matches
`mill_contour` (20,067) to the unit; `FLOOR_WALL` (18,560) matches `mill_planar`
(18,560); the five hole-making subtypes sum to exactly 53,075, the `hole_making`
count. The subtype determines the main label with certainty.

**◆ DECISION — predict `o2` only and derive `o1` by lookup.** Label space drops
from a nominal 21 pairs to 7 classes, and an entire error mode disappears before
any model exists.

Also noted (F-002) that `OTHER` is accepted by the validator but appears zero
times in the dataset — a trap for any abstain-style fallback.

### 22:03 — Test suite green
21 tests passing, covering edit distance, multiset F1 semantics, band-boundary
behaviour, exact/disjoint/partial-overlap IoU, over- vs undercut direction,
tier scoring, and mismatch handling.

Two tests run against the contest's own sample STLs. One asserts IPW volume
decreases monotonically across the sequence — a check on *our* understanding of
the file ordering as much as on the data. It passes, confirming the numbered STLs
are in machining order.

### 22:04 — Baseline probe
**▲ SURPRISE — the medium tier is far more forgiving than its band table suggests
(F-003).** Measured on the real sample sequence:

| Baseline | Mean IoU | Points |
|---|---:|---:|
| Constant (submit first IPW for every op) | 0.96996 | **15 / 35** |
| Lag-by-one | 0.99313 | **25 / 35** |
| Exact | 1.00000 | 35 / 35 |

Cause: the entire plan removes only **4.75%** of the block (600,142 of
12,647,438 mm³), so consecutive IPWs are nearly identical.

Follow-on (F-004): the 0.999 band allows ~12,647 mm³ of total error, and **four of
six measurable operations each remove less than that** — one removes just 32 mm³.

**Learned:** geometric precision is worth paying for on the few large pocket
operations and nearly worthless on the many small drilling ones — the inverse of
where operation *count* lives (hole-making is 58% of all operations). The easy and
medium tiers reward attention to opposite ends of the plan.

Framing note for the write-up: this is metric-sensitivity analysis done *before*
optimising, not a shortcut. Rubrics.pdf §3.2 penalises hacky solutions, and
F-010 sets out where that line sits.

### 22:05 — Findings and timeline started
Set up `solution/docs/` (gitignored) and a repo-root `.gitignore` covering the
dataset, generated geometry, working notes, venv, logs, and model checkpoints.

**◆ DECISION — keep working notes out of version control**, on the basis that
these are a lab notebook rather than the graded documentation. The Round 2
deliverable will be a curated document derived from these files, not these files
themselves.

### 22:10 — Working-notes infrastructure
Created `solution/docs/FINDINGS.md` and `solution/docs/TIMELINE.md`, plus a
repo-root `.gitignore`. Verified the ignore rules in a scratch git repo rather
than assuming — in particular that `!sample_submission/**` correctly re-includes
the sample `.stl`/`.ptp` files while `*.stl` still excludes generated predictions.
All 15 probe paths classified correctly.

### 22:20 — NC-code parser
Wrote `machineplan.parsing.ptp` and ran it against the real sample tool path.
274 moves recovered, 272 cutting, 4,781 mm of cutting against 27 mm of rapids.
20 new tests; suite now at **40 passing**.

**◆ DECISION — the first coordinate block seeds position and emits no move.**
Machine position is unknown at program start; treating that block as a move from
an assumed origin would fabricate a long cut straight through the stock and
corrupt any swept volume derived from it. Confirmed against the real file, where
`N16` seeds X/Y, `N18` seeds Z, and `N20` is the first genuine move. A test now
pins this, along with a continuity check asserting every move starts where the
previous one ended — that check is what would catch a dropped axis word.

**▲ SURPRISE — the 2.5-axis assumption breaks on chamfering (F-011).** The
obvious swept-volume method for 2.5-axis work is to slice the path into
constant-Z passes, buffer each 2D polyline by the tool radius, and extrude. On
the sample AREA_MILL operation, **91.9% of cutting moves ramp in X/Y *and* Z
simultaneously** — only 8.1% are constant-Z. The path is a chamfer along one
block edge (X spans the full 339 mm, Y only 17.7 mm).

**Learned:** since `AREA_MILL` is 21.9% of all operations, general 3D sweeping is
required, not an edge case. And a chamfer mill is tapered, so the swept solid is
a cone frustum dragged along a 3D curve. This is now the largest piece of unbuilt
work and the main risk to the 25-point tool-path score. Whether hole-making and
`FLOOR_WALL` pocketing are closer to true 2.5-axis is the first thing to check
when the dataset lands.

Also logged F-012: `.ptp` files carry `(AREA_MILL , TOOL : UGT0205_001)` in a
comment, giving free `o2` and tool-id supervision and a cross-check against
`details.txt`. And F-013: tool changes post as generic `T00`/`H0`, so tool
identity lives *only* in that comment — a generated path must not rely on the
`T` word to carry it.

### 22:35 — Swept-volume engine
Built `machineplan.geometry`: tool solids as solids of revolution
(`tooling.py`) and swept volumes (`sweep.py`). 25 new tests; suite now at
**64 passing**.

**◆ DECISION — sweep each move as a convex hull of two tool placements, not by
stamping the tool along a sampled path (F-014).** Every tool in the vocabulary is
convex, and for a convex body translated along a segment the swept region is
*exactly* the convex hull of the body at both endpoints. So each linear move is
computed exactly rather than approximated, at 272 hulls instead of ~4,944
stamps. Tests check against closed forms (`πr²h + 2rLh` for a drag,
`πr²(h+d)` for a plunge) rather than golden values, so a systematic error can't
slip through. Convexity is asserted directly — every tool must equal its own
convex hull.

**Learned:** this is the one genuinely elegant piece of maths in the solution and
should anchor the method section of the talk.

End-to-end run on the real chamfer path: **444,695 mm³**, watertight, 11,996
triangles, in **1.97 s**.

**▲ SURPRISE — that extrapolates to ~50 hours for the corpus (F-015).** At 91,702
operations, single-threaded sweeping is a 50-hour job. Two responses: the work is
embarrassingly parallel per operation (~6 h on 8 cores), and more usefully, most
of it is unnecessary — ground-truth removal volumes come far cheaper as
`IPW(k-1) − IPW(k)`, one boolean each. Sweeping is needed to *score* our own
generated paths, not to build training targets.

Also noted: the raw sweep includes air (bounds run X −10…349 on a block starting
at 0), so comparing to ground truth requires clipping to the stock present.

Logged **Q-006**: tool tip diameters, point angles and flute lengths are still
guesses inferred from tool *names* in Table 5. 25 points ride on them. First
thing to calibrate once the dataset opens.

### 22:45 — Zip reader and exploration script ready
Wrote `parsing/dataset.py` (lazy zip-backed reader, discovers layout from the
central directory rather than trusting the documented paths) and
`scripts/explore_dataset.py`, staged to run the moment the download completes.
Its purpose is to confirm or refute the assumptions baked into the parsers —
especially the three formats with no published spec: `details.txt`,
`part_XXXXX_operations.json`, and `*_text.stl.txt`.

### 22:55 — Dataset landed and verified
5.2 GB downloaded and MD5-verified in ~50 min. 30.3 GB free afterwards, which
confirms the read-from-zip decision was necessary rather than merely tidy —
extraction would not have fitted.

The zip reader indexed the archive in 3.2 s and the numbers match the paper
exactly: **10,000 parts, 91,702 operations, 1–38 per part, zero missing files.**

**Learned (F-019):** the documented folder layout is wrong in two places. Parts
are `featured_part_00001`, not `part_00001`, and there are **five** images per
part, not four (an `isometric_wireframe` the docs omit). Discovering structure
from the archive's central directory rather than hardcoding Fig. 1's paths is
what made the reader work first try — a principle worth keeping for the test set,
whose naming is unknown.

### 23:00 — The decisive experiment
`operations.json` turned out to publish `volume_removed_mm3` per operation
(F-017), which makes the hard tier directly falsifiable: sweep the real `.ptp`,
clip to stock, compare.

**▲ SURPRISE — it works, at IoU 0.99997 (F-016).** Three independently derived
quantities agree on operation 1 of `featured_part_00001`:

| Source | Volume removed (mm³) |
|---|---:|
| `operations.json` metadata | 53,100.9074 |
| IPW mesh difference | 53,101.0101 |
| **Our swept volume, clipped** | **53,101.5844** |

Scored as the rubric scores it: **IoU 0.99997, overcut 0.00002, undercut
0.00001** — top band on all three, i.e. **25/25** on this operation.

**Learned:** given the right operation, tool and order, the tool-path tier is
*solved*. What remains in the hard tier is **prediction, not geometry**. That
de-risks 25 points and redirects effort onto sequence and tool prediction. By
F-005 the same engine also drives much of the medium tier's 35.

Tool calibration (Q-006) resolved in the same run: `details.txt` publishes exact
`(D)`, `(C)`, `(B)`, `(FL)` parameters, and **our chamfer geometry inferred from
the tool name matched the published value to four decimals** (8.5000 mm). Only
the flute-length default was wrong (80 mm assumed, 50 mm actual).

### 23:05 — A real bug, caught by the validation
The IoU step crashed with "Not all meshes are volumes!". Diagnosis showed the
fault was **ours, not the data's**: `as_solid` culled 5 legitimate faces from a
valid 90-triangle solid and left it non-watertight.

**◆ DECISION — repair only what is actually broken (F-020).** A chamfer removal
volume is a long thin wedge and genuinely contains sliver triangles; generic
`nondegenerate_faces` cleanup cannot distinguish a sliver that is noise from a
sliver that *is* the geometry. Repair now escalates gently and stops as soon as
the mesh passes `is_volume`. Three regression tests added, one on a deliberately
sliver-heavy wedge.

**Learned:** this failed loudly, but on a slightly thicker solid the same bug
would have failed *silently*, quietly depressing IoU on exactly the thin-feature
operations the hard tier scores. Defensive preprocessing is not free. Suite now
at **67 passing**.

### 23:20 — Q-007: stratified validation across all seven subtypes
Built `validate_sweep_by_subtype.py` and a proper `details.txt` parser, then
swept 2–3 real operations of every `o2` subtype using **published** tool
parameters rather than derived ones.

**▲ SURPRISE — F-016 was encouraging and misleading.** The single operation it
validated happened to be the one type that already worked. Stratifying dropped
the mean IoU to **0.644**, with three subtypes erroring outright.

That failure was the most productive event of the session. It exposed **three
independent silent bugs** (F-023), none of which raised an error or failed a unit
test:

| Bug | Symptom | Fix effect |
|---|---|---|
| `G4` dwell read as an X move | drill dragged 25 mm sideways at depth; overcut 6.42 | DEEP_HOLE 0.0096 → **0.9939** |
| `G73` missing from cycle set | operation swept *nothing*; "no cutting moves" | DRILLING error → **0.9967** |
| R-format arcs unsupported | circular pass collapsed to a polygon | HOLE_MILLING 0.642 → **0.954** |

Plus NX tool-type strings that weren't what the vocabulary implied
(`Milling Tool-5 Parameters`, `Drilling Tool`).

Final: **mean IoU 0.926, five of seven subtypes above 0.99, covering 83.9% of the
corpus. Frequency-weighted ≈23.5/25.**

**Learned:** this is the argument for stratified validation over spot-checks, and
it is worth presenting as such — a single green result on real data proved almost
nothing.

**▲ SURPRISE — ground truth is noisy, and we were right (F-022).** Decomposing
IPW differences into connected bodies showed 18–20 components: one real feature
plus a spray of **17-micron-thick sheets** from re-tessellation. On the
spot-drilling operation the difference totalled 42.0 mm³ of which the real dimple
was 3.3 mm³ — noise 12× the signal. Our sweep had independently predicted
3.06 mm³ **from first principles**, so our answer was correct and the reference
was not.

**◆ DECISION — denoise references by thickness, never by volume.** The sheets are
thin but not small (18 mm³ against a 3.3 mm³ real feature), so a volume filter
keeps exactly the wrong bodies. Thickness is also physically defensible: the
smallest tool in the library is 5 mm across. The first attempt used a combined
volume-and-thickness rule, didn't fire at all, and was caught by its own test.

Logged **Q-009**: if the official scorer compares against the *raw* difference,
the tool-path score on small operations is unattainable by any method. Worth
asking the organizers.

**◆ Also fixed — overcut and undercut were inverted (F-024).** They fed the same
band table, so the total score never changed, which is precisely why it survived
this long. Every diagnostic reading had been mislabelled. A bug that doesn't move
the bottom line is the hardest to notice and the easiest to publish.

Suite now at **83 passing**, each new bug carrying a regression test that names
its failure mode.

### 23:45 — Q-008: what structure is in the sequences?
Prompted by a direct question — *had we used any augmentation, filtering, or
data-science technique?* **No, none.** Everything to this point was measurement
infrastructure and geometry. Recorded as F-028, both because it was a real gap
and because the tutorial requires disclosing any filtering or augmentation.

Rather than answer from theory, ran three hypotheses over all 10,000 parts.

**Hypothesis 1 — chamfers, then pockets, then holes** (mirroring the order the
CAD generator *adds* features). **54.45%.** Rejected. But the violators weren't
random: they ran the sequence in reverse.

**Hypothesis 2 — sorted by NX `Order Group`.** **27.93%.** Worse. Yet the
violation listings showed something: operations always appeared in *contiguous
runs* of the same group; only run order varied.

**Hypothesis 3 — each tool occupies one contiguous block. 70.55%**, and 85.3% of
parts are within a *single* extra run of perfectly blocked. Cross-check:
`machining_summary.tool_changes == tool_blocks - 1` for **10,000 of 10,000 parts**,
no exceptions — which validates the parsing as well as the hypothesis.

**◆ CONCLUSION (F-027): the plan is tool-change minimisation subject to
precedence constraints.** NX batches everything a tool can do and revisits a tool
only when feature geometry forces it. Hypotheses 1 and 2 were both shadows of
this.

**Learned — this decomposes the easy tier.** F1 (10 pts) scores the *multiset*,
so half the tier needs **no sequencing at all**. Levenshtein then reduces to
ordering a median of 4 tool blocks rather than sequencing up to 38 operations.
That argues for **set prediction plus constrained ordering** over free
autoregressive generation.

**▲ SURPRISE — the labels hand us the feature taxonomy (F-026).** Only **29
distinct operation names** exist across all 91,702 operations, and they name the
feature directly: `MILL_CORNER_NOTCH_RECTANGULAR`, `MILL_SLOT`,
`DRILL_TO_ENLARGE_THROUGH_HOLE`. They map onto the generative taxonomy in the
dataset paper (corner/edge/center/slot pockets, through/blind holes). The
feature→operation rules are *observable*, not merely inferable.

Also: `AREA_MILL` uses exactly **one** tool across all 20,067 instances and
`SPOT_DRILL` only two — 37.4% of operations where tool prediction is nearly
deterministic. Whereas `DRILL_BLIND_HOLE_INTO_CENTER` spans 187 tools, since
drill diameter tracks hole diameter.

Logged **Q-010**: cuboid symmetry could give 8× label-preserving augmentation,
and F-027 makes it plausible, but it is untested and must be verified first.

### 00:05 — Q-010: does ordering depend on coordinates?
Symmetry augmentation (up to 8×) hinges on whether rotating a part changes its
sequence. NX can't be re-run here, so tested the proxy: what rule orders
operations sharing a tool? Axis-sorting would break under rotation;
nearest-neighbour travel would survive.

**▲ SURPRISE — no rule fits, all at or below chance.** Across 438 same-tool
blocks: nearest-neighbour 40.2% (chance ~50%), sorted-by-Y 37.2%, sorted-by-X
30.1% (chance ~33%). Travel is 18% longer than a greedy tour. Within-block order
appears to follow CAD feature-creation order — **not recoverable from geometry**
at inference.

That looked like bad news for the Levenshtein sub-score.

**◆ RE-FRAME — the question doesn't matter.** Levenshtein scores the sequence of
*labels*, not which hole each operation targets. Permuting within a block only
matters if the block carries mixed labels. Measured: **97.65% of multi-operation
same-tool blocks are label-homogeneous** (the 2.35% exception is consistently one
endmill doing a pocket then a hole). So the unrecoverable ordering costs nothing.

**Learned (F-029): the easy tier is far smaller than it looks.** Collapsing
consecutive identical labels takes a part from **9.24 operations to 4.46 label
runs** (median 4). The target is roughly **4.5 `(label, count)` pairs**, not a
sequence of up to 38 tokens — which argues for predicting label/multiplicity
pairs directly rather than autoregressive generation.

Q-010 resolves in favour of augmentation: rotation can't break the sequence by
reordering within homogeneous blocks, and block order depends on tool-change
minimisation and precedence, both rotation-invariant. Recorded honestly that
block-order invariance is *argued*, not directly tested.

Logged **Q-011**: predicting the *counts* is now the critical path — how many
`SPOT_DRILL` passes a part needs, how many `DRILL_TO_ENLARGE_*` passes follow
from diameter thresholds.

**Method note worth presenting:** the hypothesis test failed, the failure was
informative, and re-framing dissolved the question. Worth an hour to prove a
question didn't matter.

### 00:30 — Q-005: the STEP toolchain, and the first real inference input
Closed the structural gap: everything until now concerned *targets*, but at
inference only the BRep and images exist.

**◆ DECISION — parse STEP directly; no CAD kernel.** Measured the surface
entities before reaching for OpenCascade (~400 MB): the corpus contains **only
`PLANE` (74.8%) and `CYLINDRICAL_SURFACE` (25.2%)** — no splines, cones or tori —
in files averaging 25 KB. A ~300-line targeted reader covers it, with no heavy
dependency and full understanding of the parse. `surface_type_census()` exists to
re-check the assumption on the unreleased test set.

Then built feature recognition on top and validated it against statistics in the
dataset paper that the recognizer never sees.

**▲ SURPRISE — the first attempt over-detected holes 2.6×** (6.16 per part
against a published 2.33), and 66% of "holes" matched no tool on the part.

Diagnosis: holes and pocket corner blends are *both* cylindrical faces bounded by
`CIRCLE` curves. A 90° fillet arc is a full circle entity trimmed by its
vertices, so the curve type distinguishes nothing at all. **◆ The correct
discriminator is a closed boundary edge** — start and end vertex the same
instance — because a hole wall wraps 360° and a fillet does not.

A second error surfaced alongside: taking bounds over every `CARTESIAN_POINT`
inflated block height from ~100 to ~136 mm, since placement origins are
construction geometry outside the solid. Bounds now use vertex points only.

After both fixes, every metric agrees with the paper:

| Metric | Ours | Paper |
|---|---:|---:|
| Holes per part | 2.283 | 2.330 |
| Diameter mean / min / max (mm) | 17.04 / 5 / 50 | 17.47 / 5 / 50 |
| **Blind share** | **0.502** | **0.502** |
| Block L / W / H (mm) | 346 / 341 / 98.6 | 350 / 351 / 100.1 |

Zero parse failures across 400 parts. The blind/through split agreeing to three
decimals is the strongest single confirmation.

**▲ SURPRISE — the leftover 18% was a finding, not an error (F-032).** Holes that
matched no tool were, in every case, *larger than any drill on the part*:
D15.90 against tools [10, 12, 20]; D30.50 against [20, 25]. Those are
`HOLE_MILLING` operations — an endmill spiralling a bore too large to drill.

**Learned:** that yields the first concrete feature→operation rule, recovered
from data rather than assumed:

> if a hole's diameter exceeds the largest available drill, it is milled;
> otherwise it is drilled.

The validation check was too strict, not wrong — and its failures were the
result. Suite now at **93 passing**.

### 00:55 — Q-011: mining the feature → operation rules
Drilling operations carry their XY in the `.ptp`, and the BRep gives each hole's
XY, so operations can be matched to *individual holes*. It worked better than
expected: **1,120 of 1,136 holes matched (98.6%)**, 99.2% of operations.

**▲ SURPRISE — 1,120 holes reduce to just 14 distinct operation chains (F-033).**
`DRILLING` alone (26.2%), `SPOT_DRILLING → DRILLING` (25.1%),
`SPOT_DRILLING → DRILLING → DEEP_HOLE_DRILLING → DRILLING` (12.2%), and a short
tail. Predicting a hole's operations is therefore a **14-way classification**,
not sequence generation — the strongest evidence yet that this is rule recovery.

**◆ F-032 IS REFUTED — and by my own experiment.** Yesterday's "hole diameter
exceeds the largest drill ⟹ milled" was inferred from **8 examples** in a
validation listing. Against 1,120 matched holes it fails completely: the largest
drill in use is 50 mm, every milled hole is 12.3–19.9 mm, so **100% of milled
holes are inside the drillable range**. The 8 cases came from parts whose *own*
tool set was small — I generalised the part to the library.

A follow-up hypothesis (milling when no drill of that size exists) also failed:
**82.5%** of milled holes have a matching drill among 158 distinct sizes.

The finding is marked refuted in place rather than deleted, because the reasoning
error is the instructive part: plausible mechanism, tiny sample, and confirmation
drawn from cases selected precisely *because* they were anomalies.

**Learned — what does hold (F-034):**
- **Pecking follows slenderness.** `DEEP_HOLE_DRILLING` has aspect ratio 6.27
  against 4.45 for plain drilling, and never appears below 12.1 mm.
- **Pass count follows diameter.** 1 pass averages 16.6 mm; 2–3 passes start at
  12.10 mm; 4 passes at 19.30 mm. Large holes get a pilot then enlargement.
- **Spot drilling is a tendency only.** 14.10 mm mean with a spot drill against
  22.03 mm without; through holes 72.9% vs blind 52.7%. Not deterministic —
  something else is involved, and at 15.5% of operations it matters.

Logged **Q-013**: what actually selects `HOLE_MILLING` and `SPOT_DRILLING`.
Both likely need pocket recognition (Q-012) — a hole nested in a pocket has its
entry face below the top plane, which would plausibly change the strategy.

### 01:25 — First end-to-end submission
**◆ DECISION — stop analysing, build a deliberately bad baseline.** Each analysis
was raising two more questions while the score stayed at zero. Built the missing
pieces in one pass: chamfer and pocket-floor recognition, a rule-based predictor
from F-033/F-034, IPW and NC generation, and the submission writer.

Result: **21.97 / 100** (easy 10.00/20, medium 5.00/35, tools 6.97/20; tool paths
not yet scored). 12 parts, 252 files, 8.2 s, zero failures.

**All four deliverables pass the official validator.** The format contract is now
proven by construction rather than by reading `validate_submission.py`.

**Learned — F-027 confirmed in practice.** F1 runs 0.93 / 0.88 / 0.93 on parts
whose Levenshtein is 0.52–0.85: we pick roughly the right *bag* of operations and
put them in the wrong *order*, exactly as the tool-blocking analysis predicted.
Operation count is already close — 9.50 predicted against 8.92 actual.

**▲ SURPRISE — our IPWs score worse than doing nothing (F-036).** Generated IPWs
average IoU 0.79 → 5/35. Submitting the *unmachined stock* for every operation
scores 0.970 → 15/35 (F-003). We are 10 points below the null baseline.

Cause: IPW error is two-sided and we incur both kinds. Pockets are over-cut
(approximated by the bounding box of each floor patch, ignoring fillets), while
chamfers are under-cut (recognised but not cut at all). Doing nothing incurs only
under-cutting, and the block is only ~4.75% machined, so the null baseline sits
near 0.97 by construction.

**◆ DECISION — make medium-tier cutting a per-feature opt-in.** Start from the
null baseline as a floor, and replace a feature's removal with a computed one
only when that removal is *exact*. Holes qualify today (analytic cylinders);
pockets and chamfers do not. This makes the score climb monotonically as
recognition improves rather than oscillate.

**Learned — the baseline earned its keep immediately.** It converted "we have no
submission" into a measured 21.97, proved the formats, confirmed a structural
prediction, and overturned the plan for the largest tier. None of that was
reachable by more analysis.

### 01:45 — Measuring the cut policy, and finding the real driver
Acted on F-036 by making IPW cutting a per-feature opt-in, then measured all four
policies side by side rather than assuming which was best.

**▲ SURPRISE — the policies are nearly identical.** Null 5.42, holes-only 5.83,
holes+pockets 5.00, everything 5.00. The whole policy space spans **0.83 points**.
The expected "+10 from adopting the null baseline" did not exist.

Digging into why produced the strongest analytical result of the project.

**◆ F-037: medium IoU is a function of sequence length, not geometry.**
Plotting IoU against the ratio of predicted to true operation count:

```
Medium IoU  ≈  min(n_pred, n_truth) / max(n_pred, n_truth)
Pearson r = 0.9990,  mean |error| = 0.011
```

Consecutive IPWs are nearly identical (the plan removes ~4.75% of the block), so
any *aligned* operation scores IoU ≈ 1 almost regardless of what we cut, while
unaligned ones score 0. The mean is just the fraction that line up.

**Learned — this reprioritises everything:**
- **Medium and easy are the same problem.** Both gated on operation *count*.
  Work there pays into 55 points at once, not 20.
- **Medium-tier geometry work is premature.** Exact pockets, chamfer wedges,
  fillets — all buy ~0.01 IoU while length error costs up to 0.55.
- The residual (consistently ≈ −0.01) *is* the geometry term. It is what
  separates 0.99 from 0.999 — and it only becomes worth chasing once length is
  right.

**F-036 marked superseded.** Its observation was real but its explanation was
wrong: it blamed over/under-cutting geometry when the dominant term was always
sequence length. Its prescription ("holes only") happens to be correct, but by
0.4 points rather than the 10 claimed.

Second time in this project that a confident causal story survived only until it
was measured properly (see also F-032). Both are worth keeping in the write-up.

### 02:10 — Fixing operation count: 21.97 → 28.07
Acted on F-037 by attributing count error per `o2` label over 200 parts. The
diagnosis was unambiguous: **`DRILLING` over-generated by +189 (0.94/part)** —
more than the entire net error of +146. `AREA_MILL` was exactly right (419/419).

Cause: every hole above 12.1 mm got a pilot *plus* a finish pass, ~2.4 passes per
hole against a true mean of 1.69 (F-034). And the 1-/2-/3-pass diameter means are
nearly identical, so diameter never justified it.

Three measured changes took net count error from **+146 to −16** (0.9%).

**▲ SURPRISE — aggregate accuracy is not per-part accuracy.** Totals now matched
almost exactly, yet the mean length ratio moved only 0.8202 → 0.8222. Per-part
errors of opposite sign were cancelling. Since F-037 scores each part
independently, the *distribution* matters, not the mean — an obvious point in
hindsight that cost real time.

**◆ Tested and refuted: does NX batch several holes into one operation?** A
plausible explanation for over-generation. Measured across 801 hole operations:
92.3% are single-point, and `DRILLING` / `SPOT_DRILLING` are **100%**
single-point. The multi-point cases are all `HOLE_MILLING`, where the points are
helical positions inside one bore. NX does not batch holes.

**◆ Per-part inspection found it instead (F-039).** `featured_part_00008`
predicted 11 against 5: three D30.5 through-holes that NX **mills**
(`MILL_THROUGH_HOLE_FROM_SOLID_MATERIAL`) and we drilled in three passes each.
F-034's milling band (12.3–19.9 mm) came only from position-matched holes and
missed the large end — a sampling artefact.

Two fixes tried and measured: relaxing the aspect limit across the whole range
raised the ratio but wrecked the labels (`HOLE_MILLING` +85, `DRILLING` −231);
treating large bores as their own case (≥26 mm ⟹ milled) kept both.

`featured_part_00008`: 11/5 → **5/5**, easy 0 → 20/20, IoU 0.446 → 0.9812.
`featured_part_00001`: 8/7 → **7/7**, IoU 0.9659.

**Score: 21.97 → 24.27 → 28.07 / 100.** Easy 10.00 → 12.33, medium 5.00 → 7.50,
tools 6.97 → 8.23. 93 tests green throughout.

This also partly rehabilitates the refuted F-032: large holes *are* milled. What
F-032 got wrong was the threshold and the mechanism, not the direction.

### 02:40 — Easy and medium: 28.07 → 30.76
**◆ DECISION — measure absolute per-part error, not net.** F-038 had already
shown aggregate accuracy hides per-part damage, so the diagnostic was extended to
report `|error|` per label. The result was stark: **net error 0.705/part against
absolute error 3.505/part — five-fold cancellation.**

That immediately named the target. `FLOOR_WALL` had a net error of +0.05 yet was
**wrong on 58% of parts**.

**▲ SURPRISE — blind-hole bottoms were being counted as pockets (F-040).** A
blind hole ends in a flat circular face strictly between the stock bottom and
top, which is exactly the pocket-floor test. `featured_part_00019` produced three
spurious floors with footprints `5x0`, `5x0`, `5x0` on a part with **no pockets
at all**.

Two conservative filters (reject degenerate footprints; reject floors inside a
recognised hole) took exact `FLOOR_WALL` counts from **44.0% → 68.0%** and
eliminated over-counting entirely.

Also retuned the large-bore milling threshold 26 → 30 mm, which had
over-corrected `DRILLING` from −0.1 to −0.985 per part.

| Metric | Start of stretch | End |
|---|---:|---:|
| Total score | 28.07 | **30.76** |
| Easy | 12.33 | **13.00** / 20 |
| Medium | 7.50 | **9.17** / 35 |
| Tools | 8.23 | **8.59** / 20 |
| Mean length ratio | 0.834 | **0.853** |
| Absolute count error/part | 3.505 | **2.885** |

**◆ Tested and NOT fitted (F-041).** The residual pocket error is now purely
under-counting — 1.39 true operations per recognised floor. Neither depth
(0.263 vs 0.289) nor footprint (13,931 vs 15,325 mm²) separates the pockets that
need a second operation. Rather than add an extra operation to an arbitrary 39%
of pockets — which would match the marginal while leaving per-part error
unchanged — the gap is left open and documented. Fitting a marginal without a
mechanism inflates a statistic without earning a point.

**Learned:** twice now, aggregate statistics concealed a defect that per-part
measurement exposed in minutes. Worth stating as a method in the write-up rather
than as an anecdote.

### 03:05 — Wiring in tool-path scoring: the last 25 points, finally measured
Wired sweep scoring into the baseline loop — parse each emitted `.ptp` back,
sweep it with its declared tool, clip to the stock present, compare against the
denoised IPW difference. Round-tripping our own output also proves it parses.

**▲ SURPRISE — tool paths score 0.47 / 25 (F-042).** For contrast, F-021 measured
the *same sweep engine* at ≈23.5/25 on ground-truth paths. The engine is fine;
what we generate is not.

Three chamfer-path variants were tried, and all are equivalent to zero:

| Variant | Paths |
|---|---:|
| Path collapsed to the origin (a bug) | 1.72 |
| Tool along the edge at mid-height | 1.25 |
| Positioning move only | 0.47 |

**◆ DECISION — keep the principled version, not the highest-scoring one.** The
*buggy* variant scored best. On 8 parts that spread is noise, and retaining a bug
because it wins by 1.2 points is exactly how a submission stops generalising.

**Learned — the diagnosis is precise now.** Pockets get a single perimeter pass,
which sweeps a thin ring instead of the pocket volume (20.2% of operations,
near-total undercut). Chamfers have no correct path: a 20 mm chamfer mill placed
on the edge line buries its body in the block and overcuts. Drilling is probably
close but diluted by the other two.

**First full 100-point score: 38.24** — easy 14.50/20, medium 12.50/35, tools
10.77/20, paths 0.47/25.

This stretch did not raise the score; it revealed that a quarter of it was
missing. Worth more than the tuning it displaced.

### 03:35 — Pushing easy and medium toward 80%
Target set: easy >16/20, medium >28/35.

**◆ F-043 — pecked holes need drilling on both sides.** Re-reading the F-033
chains literally (rather than deriving rules from marginals) showed every chain
containing `DEEP_HOLE_DRILLING` brackets it with drilling passes on both sides.
We emitted only the trailing one, because the leading pass was gated on diameter
≥19.3 mm — and pecked holes are narrow by definition.

Making the pilot unconditional for pecked holes: `DRILLING` absolute error
1.170 → **0.840**, length ratio 0.8525 → **0.8707**, **medium 9.17 → 12.50**.

**◆ Tested and reverted: splitting pockets on the reach ratio.** F-041 predicted
that fitting a weak signal would match the marginal while hurting per-part
accuracy. Implemented it and that is exactly what happened — `FLOOR_WALL` net
−0.515 → −0.015 (near perfect) but parts wrong 69 → **86**, and length ratio
0.8707 → 0.8649. Reverted, with the measurement recorded in the code.

**◆ Tested: exact pocket geometry.** Replaced bounding-box pocket removal with
true rounded prisms built from the recognised corner blends (erode-then-dilate).
Effect on medium IoU: **0.8856 → 0.8857**. The fillets were never the problem.

**▲ F-044 — medium cannot reach 80% by counting alone, and here is the proof.**
Six parts already have *exact* operation counts and still score IoU 0.980–0.982,
which is 20 points, not 25 or 35. So perfect counting everywhere lands near
**20/35 (57%)**. The residual ~0.018 is material we never cut: chamfers (skipped
entirely) and pockets (cutting them scores *worse* than not).

**Learned:** there are two distinct ceilings. Count accuracy decides whether a
part scores *anything*; geometry accuracy caps how much. We have been lifting the
first, and 80% needs the second — exact chamfer wedges and true pocket outlines,
both topology work on the STEP reader rather than tuning.

### 04:05 — Exact chamfer geometry, and three rules that failed
**▲ F-045 — the chamfer problem was mis-framed.** Chamfers had been skipped
because reconstructing the wedge seemed to need the block edge. It does not: a
chamfer face is a *plane*, and the material it removes is exactly the stock on
that plane's outward side. Slicing the stock gives it outright.

Two details made it robust — anchor the plane on a face **vertex** rather than
the STEP placement origin (which can sit outside the solid), and resolve normal
orientation **by measurement**, cutting both sides and keeping the smaller.

That moved the best cut policy from "holes only" to "everything" (13.17 against
12.17 over 30 parts), and medium 12.50 → **13.33 / 35**.

**◆ Three rules implemented, measured, reverted (F-046).** Each improved an
aggregate statistic and lowered the score:

| Rule | Aggregate | Score |
|---|---|---|
| Split wide-cornered pockets | `FLOOR_WALL` net −0.515 → −0.015 | parts wrong 69 → **86** |
| `SPOT → DRILL → HOLE_MILLING` for mid-band bores | closes a real 4.5% chain | medium 13.33 → **12.08** |
| Chamfer path along the edge | plausible motion | paths 1.72 → **1.25** |

Same failure each time: a real but weak signal applied to every member of a
group fixes the population mean and breaks individual parts — and F-037 scores
parts individually. Each reversion is documented in the code with its
measurement, so the next person does not re-derive it.

**Session totals for the two target tiers:**

| Tier | Session start | Now | 80% target |
|---|---:|---:|---:|
| Easy | 10.00 | **13.67 / 20** (68%) | 16.0 |
| Medium | 5.00 | **13.33 / 35** (38%) | 28.0 |
| Total (all four) | 21.97 | **36.38 / 100** | |

Medium has nearly tripled; both remain short of 80%, for the reason set out in
F-044 — six parts already have exact counts and still cap at IoU ~0.98.

### 04:40 — First machine learning in the project
Until now every rule was hand-tuned by eye against marginal statistics, and F-046
recorded three that failed that way. The diagnosis — *the separator exists but is
not hand-findable* — is a classification problem, with 10,000 labelled parts
sitting unused.

Extracted 5,610 position-matched holes from 2,042 parts into a training table.
Every feature derives from the BRep (diameter, depth, aspect, through/blind,
`top_drop`, in-pocket, hole count, same-diameter count); the chain label comes
from `details.txt`, which is a target and never an input.

**▲ F-047 — the model wins decisively.** On 1,382 holes from 511 parts never seen
in training, split by *part* rather than hole:

| Predictor | Chain accuracy | Mean \|count error\| |
|---|---:|---:|
| Majority class | 0.261 | — |
| Hand-written rules | 0.391 | 0.635 |
| **Gradient boosting** | **0.948** | **0.082** |

**Learned — the rules were blind where it mattered most.** They scored **0.000**
on plain `DRILLING`, the single most common chain (361 holes), because they always
prepend a spot drill below 20 mm. Also 0.000 on `SPOT|DRILL|HOLE_MILLING` and
`HOLE_MILLING|BORING_REAMING` — precisely the chains Q-013 and F-046 had failed to
characterise by hand.

**◆ DECISION — evaluate on parts outside the training range.** Scoring parts 1–12
gives 36.85, but those are in the training set. Added `--offset` to
`run_baseline.py` and re-ran both predictors on identical unseen parts:

| Tier | Rules | Classifier |
|---|---:|---:|
| Easy | 11.10 | **12.70** |
| Medium | 9.25 | **10.75** |
| Tools | 7.49 | **7.77** |
| **Total** | **27.91** | **31.22** |

The ≈5.6-point gap between in-sample and held-out is a fair measure of how
optimistic the earlier numbers were — worth stating rather than quietly quoting
the higher one.

The rule path is retained as a fallback so the pipeline runs from a clean
checkout, and feature extraction lives in the model module and is imported by the
dataset builder, so training and inference cannot drift.

### 05:00 — Extending the model to pockets: a useful failure
Repeated the F-047 recipe for pockets, where F-041 had left counting unsolved.
Extracted 3,129 recognised floors with their attributed operation counts.

**▲ F-048 — the model loses to the trivial rule.** On 786 held-out floors:
"always 1" scores accuracy 0.865 / count error 0.178; gradient boosting 0.859 /
0.181. Recall on the cases that matter is 0.091 for 2-operation floors and
**0.000** for 3- and 4-operation ones. The training script's guard refused to
save it.

**Learned — the two problems were never the same shape.** For holes the
diagnosis was "the separator exists but is not hand-findable", and a classifier
found it at once. For pockets, twelve geometric features carry *no* signal:
the information is not in the recognised geometry at all.

**Where the pocket error really lives:** 86.9% of recognised floors take exactly
one operation, but **22.5% of all `FLOOR_WALL` operations match no recognised
floor**. The under-count splits roughly 45/55 between mis-counting pockets we
find and never finding the pocket at all — and the larger half is a *recognition*
problem no counting model can reach.

**◆ Tested and neutral: stricter floor merging.** The obvious suspect was
bounding-box-contact merging fusing distinct pockets. Requiring 30% area overlap
measured **exactly neutral** (1.220 floors/part, 68.0% exact, unchanged). Kept
because it is the more defensible rule, with the neutral measurement recorded in
the code so nobody re-runs the experiment.

Further pocket work belongs in `features.py`, not in a model.

### 05:30 — "Are you sure the validation is good?"
A direct challenge, and the answer was no. Named the weaknesses before testing
them: sample sizes of 8–30 parts with no error bars, thresholds tuned on parts
1–200 that still run inside the "held-out" evaluation, the cut-policy comparison
run entirely in-sample, a single split and seed on the classifier, and — deepest —
a scorer built on an assumption the rubric never states.

Built `scripts/evaluate.py`: 150 held-out parts, bootstrap confidence intervals,
paired comparison.

**▲ F-050 — most tuning decisions were inside the noise floor.** Medium carries a
**±2.2 point** interval on 150 parts. The cut-policy choice ("everything" over
"holes+chamfers", 13.17 vs 12.67 on 30 parts) was unresolvable noise; so was the
rounded-corner change.

**What survives, decisively.** Paired comparison on the same 150 parts, which
removes the dominant between-part variance:

| Tier | Rules | Classifier | Diff | 95% CI |
|---|---:|---:|---:|---|
| Easy | 10.59 | 13.24 | +2.65 | [+1.95, +3.40] |
| Medium | 8.37 | 12.97 | +4.60 | [+2.60, +6.67] |
| Tools | 5.60 | 6.49 | +0.89 | [+0.42, +1.42] |
| **Total** | **24.56** | **32.70** | **+8.14** | **[+5.34, +11.06]** |

Every interval excludes zero. The earlier 20-part estimate of +3.31 *understated*
the gain by more than half — unpaired comparison on few parts is dominated by
which parts happen to be easy.

**▲▲ F-049 — the scorer rests on an unstated assumption worth 26% of the tier.**
Q-002 (how a sequence-length mismatch is handled) was never specified by the
rubric. Scoring the same 40 parts under both readings:

| Convention | Points | Mean IoU | r(length ratio, IoU) |
|---|---:|---:|---:|
| union (ours) | 13.25 | 0.8735 | **+0.9918** |
| truncate | **22.25** | 0.9821 | **+0.1142** |

**A 9-point swing, and it invalidates the reasoning rather than just the number.**
F-037's "medium IoU *is* the count ratio, so counting is the objective" holds only
under our convention. Under truncation the correlation collapses to 0.11 and the
tier becomes geometry-driven — the opposite prescription.

The scorer now supports both via `alignment=` and defaults to the pessimistic
one. This is the highest-value open item in the project and only the organizers
can settle it.

### 05:45 — "Did we use the whole 5 GB?"
No — and the tally is worth recording honestly:

| Use | Parts | Share |
|---|---:|---:|
| Corpus statistics | 10,000 | 100% |
| **Classifier training** | **2,042** | **20%** |
| Pocket dataset | 2,500 | 25% |
| Feature validation | 400 | 4% |
| Evaluation | 150 | 1.5% |

The classifier — the strongest component — saw 5,610 of roughly 23,322 holes.
And the **50,000 PNG images have never been touched at all**, an entire input
modality available at inference.

Re-extracted all 10,000 parts: **22,491 holes, 4× the training data.** Chain
accuracy **0.948 → 0.970**.

**◆ DECISION — split deterministically on the part number.** Once training covers
all 10,000 parts, a *random* part split leaves no range that is provably unseen,
so the earlier "held-out at offset 3000" evaluation would have become
contaminated. Now everything below part 8,000 trains and everything at or above
is never touched, making `--offset 8000` honest by construction rather than by
argument.

**Definitive figure, 150 provably-unseen parts:** **32.98 / 75**
[29.88, 36.23] — easy 13.79, medium 12.20, tools 6.99. Mean length ratio
**0.9146**, up from 0.8418 under the rules.

Disclosed filtering (Tutorial p.9): 9 holes (0.04%) in three chains occurring
fewer than five times, dropped from *both* halves so the accuracy is not
flattered.

### 06:15 — "Why not use the images?" and the biggest single gain yet
Two pushes from the user, both productive.

**"Why partial data?"** Honest answer: habit, not reasoning. Optimised for a fast
tuning loop (4 min vs 15 min extraction) and never revisited it. Re-extracted all
10,000 parts: chain accuracy **0.948 → 0.970**, plus a provably-disjoint holdout
(parts ≥ 8000 never trained on).

**Tools tier, analysed for the first time (F-052).** Tool *type* is correct on
**1,698 of 1,698** aligned slots — that half was already solved. The whole loss is
diameter, and mining the true ratios showed two hand-guesses were badly wrong:
`DEEP_HOLE_DRILLING` is a small *pilot* drill at 0.383 of the bore (we assigned
1.000, a 2.6× over-estimate on 559 operations) and `HOLE_MILLING` uses 0.779 (we
guessed 0.600).

**▲▲ F-053 — our fixed block order was right on 26.5% of parts.** The modal order
is `HCP` (hole → chamfer → pocket) at 34.1%; we had been emitting the
*second*-most-common. And order is **0.896 predictable** from part geometry.

**◆ A mistake worth recording.** The first measurement of this showed +2.09, not
significant — and was not measuring what I thought. The save step had been added
to the mining script but the script never re-run, so no model existed and the
planner silently used its fallback. That +2.09 was purely the value of changing
the fallback from `CPH` to `HCP`. Training is now split into
`train_block_order.py` so whether a model was written is explicit.

With the model actually fitted, paired over **400 held-out parts**:

| Tier | Fallback | **Model** | Diff | 95% CI |
|---|---:|---:|---:|---|
| Easy | 13.53 | **15.56** | +2.04 | [+1.65, +2.40] |
| Medium | 13.69 | **14.95** | +1.26 | [+0.82, +1.70] |
| Tools | 7.67 | **10.24** | +2.57 | [+2.03, +3.10] |
| **Total (of 75)** | 34.88 | **40.75** | **+5.87** | **[+4.62, +7.11]** |

All significant. Tools gained most, exactly as the cross-cutting argument
predicted — alignment was its binding constraint.

**▲ F-054 — the images cannot help.** Tested directly: of 234 `FLOOR_WALL`
operations, 53 matched no recognised floor — and **all 53 have a large horizontal
face sitting in the STEP** (79×149, 37×79, 79×99 mm) that our own filter rejects.
Zero cases of "no face in the BRep". The images are lossy renders *of* that
geometry; they cannot contain a pocket the BRep does not. We are discarding data,
not missing it, and the fix is a filter bug.

### 06:45 — 🔴 One shadowed variable, 8.72 points
F-054 had proved the missing pockets were *in* the STEP, so this became a
debugging task rather than a modelling one. Traced the filter stages: a direct
call to the hole-bottom filter kept 6 floors, but `extract_features` produced 3.
Replicating its loop by hand gave 11 floors where the real function gave 4 — in
the same process, on the same cached model.

**The bug.** `extract_features` reads the stock bounds into `bottom_z`/`top_z`,
then the **cylindrical** branch does:

```python
bottom_z, top_z = face.z_range      # same names as the stock bounds
```

`model.faces` interleaves planar and cylindrical faces, so every planar face
after the first hole was tested against *that hole's* z-range instead of the
block's, and most pocket floors were silently discarded.

**How badly it hid:**
- F-041 concluded "some pockets take two operations, no predictor separates
  them" — those extra operations were mostly floors we never found.
- F-048 trained a classifier for that phantom effect and *correctly* failed.
- The tightened merge rule measured "exactly neutral" — true, and irrelevant.

| Metric | Before | After |
|---|---:|---:|
| Floors per part | 1.220 | **1.680** (truth 1.693) |
| Exact `FLOOR_WALL` count | 68.0% | **98.7%** |
| Mean length ratio | 0.9129 | **0.9788** |

Paired over 400 held-out parts: **40.75 → 49.47 of 75, +8.72 [+7.43, +10.05]**,
every tier significant. Medium +6.24. **Easy reaches 17.28/20 = 86.4%**, past the
80% target.

**Learned — two safeguards would have caught it:** validate recognition against
published statistics *continuously* (holes were checked in F-031 and passed;
pockets never were, and 1.22 floors against a published 1.85 was visible the
whole time), and **when a model fails to find a signal, suspect the inputs before
the theory** — F-048's failure was the loudest possible hint and was read as a
finding about pockets instead.

Both learned models were trained on features computed *with* the bug
(`n_floors`, `in_pocket`), so both are being re-extracted and retrained.

### 07:20 — Retraining, area clearing, and a second geometry bug
Retrained both models on features corrected by F-055. Hole chains **0.970**
(count error 0.674 → **0.040**), block order **0.897**. End-to-end effect
**+0.28, not significant** — the corrupted features had not been hurting the
models much, which is worth knowing rather than assuming.

**Built pocket area clearing (F-057).** Contour-parallel offsets stepping inward
from the wall, replacing the single perimeter pass that swept a thin ring and
left the interior untouched. Paths moved **0.50 → 0.62 of 25** — essentially
nothing.

**◆ Tested and measured neutral: bounding flute length to the cut depth.** The
theory was that an 80 mm flute on a shallow pocket over-swept vertically. It
measured *exactly* neutral, because clipping to the stock already bounds the
sweep vertically. **That neutral result was the useful part** — it proved the
overcut was *horizontal*, and pointed straight at F-056.

**▲ F-056 — construction points were inflating every bounding box.**
`_loop_vertices` recorded every `CARTESIAN_POINT` it reached, but the traversal
passes through `CIRCLE`, `LINE` and `AXIS2_PLACEMENT_3D`, whose points are arc
centres and placement anchors that need not lie on the face. Symptoms visible for
hours and dismissed as quirks: chamfers reporting z 63.5–**127.7** on a 73.6 mm
block, and clearing paths covering **11×** the real footprint.

Restricting to points reached through a `VERTEX_POINT` fixed both, with feature
statistics still matching the paper (blind share exactly 0.502).

Paired over 400 held-out parts: medium **21.36 → 23.04** (+1.68 [+1.15, +2.24]),
total **49.76 → 51.42** (+1.66 [+1.04, +2.30]). Both significant.

**Session arc: 21.97 → 51.42 of 75.** Easy 17.41/20 (**87%**), medium 23.04/35
(66%), tools 10.96/20 (55%), length ratio **0.9811**.

### 07:50 — Easy to 87%; medium's remaining gap diagnosed
Target: easy ≥16/20, medium ≥28/35. **Easy met at 17.41/20 (87%).** Medium at
23.02/35 (66%).

Attributed medium's loss per feature: pockets 0.979 (worst), holes 0.993,
chamfers 0.995. Pockets carried *both* overcut and undercut, which reads as a
wrong footprint shape, so three fixes were built and measured:

| Change | Result |
|---|---|
| True ordered boundary from the STEP edge loop, not a bounding box | 0.97929 → **0.97926** |
| Pockets shallowest-first | 0.97766 (worse) |
| Pockets deepest-first | identical to arbitrary |
| Conical bottoms on drilled blind holes | 0.99295 → **0.99289** |

All neutral. The band shares never moved: 31.4% of exact-count parts ≥ 0.999
throughout.

**▲ Why the outline fix did nothing is the informative part.** Measuring the
recovered boundaries against their bounding boxes gave area ratios of
**0.983–1.000** — the pockets really are near-rectangular, so the box was already
right to 1.7%. The diagnosis "both overcut and undercut means the shape is wrong"
was plausible and false, and only measurement showed it.

**Learned — medium's last 14 points are structural, not geometric.** Reaching
28/35 needs most parts under **0.1%** volume error (~12,000 mm³ of 12 M). The
current 0.9% is not distributed in a way any per-feature fix reaches. What
remains: *which* pocket sits at each index (counts are 98.7% exact but identity
is not), and the ~10% of parts where the block-order model is wrong.

And the ceiling itself is uncertain — F-049 showed Q-002 is worth 26% of this
tier, so "medium at 80%" is partly a question about the scorer.

---

### 08:15 — Is the 400-part slice actually representative?
Every number since F-035 was measured on the same fixed 400 parts (offset 8000).
That is the right call for paired comparisons (F-050), but it left one honest
question unasked: is that particular 400 a lucky sample of the 2,000 held-out
parts, or a fair one? 1,600 parts (offset 8400-9999) had never been scored by
anything.

Re-downloaded the corpus (checksum verified, `831ccc4bd0ee62759ec383556b8c95da`)
and scored all 1,600. Unpaired comparison against the 400, since these are
disjoint parts:

| Tier | 400-slice | 1,600-reserve | Diff | 95% CI |
|---|---:|---:|---:|---|
| Easy | 17.41 | 17.20 | +0.21 | crosses zero |
| Medium | 23.02 | 22.72 | +0.31 | crosses zero |
| Tools | 10.96 | 10.81 | +0.15 | crosses zero |
| **Total** | **51.40** | **50.73** | **+0.67** | **crosses zero** |

**Learned — the 400 was fair, not lucky (F-060).** Every interval crosses zero.
Combining all 2,000 held-out parts gives a tighter, more honest headline number:
**50.87 / 75, 95% CI [50.10, 51.65]** — versus 51.40 with a ±2.09 interval
before. Same conclusion, half the uncertainty, for one 28-minute evaluation run.

---

### 08:40 — Caught: no hyperparameter tuning was ever documented
Fair callout — both gradient boosting models carried `max_iter=300` and one
carried `l2_regularization=1.0`, with no written search behind either, and
`learning_rate`/`max_leaf_nodes` were bare scikit-learn defaults. Nothing in
METHODS.md said so.

Ran a grid search properly: a validation split carved out of the *training*
range only (parts 0-6,999 fit, 7,000-7,999 validate), so the parts-8,000+ test
number stays untouched by model selection.

| Model | Best-on-validation gain | Refit, held-out test |
|---|---:|---:|
| Block order | +0.0046 | 0.8968 vs 0.8968 — no change |
| Hole chain | **+0.0078** | **0.9415 vs 0.9701 — a 2.86-point loss** |

**◆ DECISION — trust the test split, not the validation winner.** The hole-chain
configuration that looked better on 2,044 validation rows was worse by nearly
three points on the real held-out test once refit properly. Same lesson as
F-050, now applied to model selection: a small validation split is not evidence
either. The original, untuned hyperparameters turn out to be the right ones —
kept the shipped model unchanged, documented the sweep in METHODS.md and F-061
so the choice is measured rather than assumed.

---

### 09:05 — Second callout, and a bigger gap: why gradient boosting at all?
Fair again. Nothing anywhere compared `HistGradientBoostingClassifier` against
any other model family. F-047 and F-053 justify learning versus the rule; they
never justify this specific algorithm versus, say, a random forest or a plain
neural network.

Same protocol as the hyperparameter check: six families, fit on parts
0-6,999, chosen by validation accuracy on parts 7,000-7,999, so family choice
cannot peek at the parts-8,000+ test set either.

| Model | Hole chain val | Block order val |
|---|---:|---:|
| Majority class | 0.2613 | 0.3570 |
| Logistic regression | 0.6967 | 0.8650 |
| k-nearest, k=15 | 0.6893 | 0.7700 |
| Random forest, 300 trees | 0.8527 | 0.8947 |
| Small MLP | 0.7652 | 0.8776 |
| Single decision tree | 0.9442 | 0.8215 |
| **Gradient boosting** | **0.9692** | **0.9016** |

Gradient boosting won both, cleanly, so the held-out test figures reproduce
exactly what was already reported: 0.9701 and 0.8968.

**Learned (F-062).** Tree-based methods dominate everything else on both
tasks, and even a bare single decision tree beats every linear or
distance-based method by twenty to thirty points. Our own rule-based components
are threshold logic on these same features, so the real decision structure is
axis-aligned thresholds, which a tree represents natively and a linear model
does not. The choice of algorithm was never written down as a decision; it is
now, and it holds up.

---

## Running status

| Item | State |
|---|---|
| Dataset | **downloaded and verified**, 10,000 parts / 91,702 operations |
| Local scorer (all three tiers) | **done** |
| `.ptp` NC-code parser | **done**, cutting length matches metadata to 3 decimals |
| Swept-volume engine | **done, validated across all 7 subtypes: ≈23.5/25 weighted** |
| Zip-backed dataset reader | **done**, indexed the real archive first try |
| Tool geometry calibration | **resolved** (Q-006) — exact parameters in `details.txt` |
| `details.txt` parser | **done**, labels + tool parameters |
| Test suite | **83 passing** |
| Rubric ambiguities | logged as Q-001, need organizer ruling |
| Ground-truth denoising | **done**; Q-009 open — do the graders denoise too? |
| `operations.json` parser | prototyped in scripts, needs promoting to a module |
| Tool library (431 distinct tools) | not built |
| STEP/BRep reading | **done** — direct parser, no CAD kernel (F-030) |
| Hole recognition from BRep | **done**, matches published statistics (F-031) |
| Pocket / chamfer recognition | **first pass done** — floors and slanted planes; type taxonomy still crude |
| Rule-based predictor | **done (baseline)** — `predict.py` |
| IPW + NC generation | **done (baseline)** — `generate.py` |
| Submission writer | **done** — all four formats pass the official validator |
| **End-to-end score (held out)** | **51.42 / 75** on 400 parts ≥ 8000, provably unseen |
| — easy / medium / tools | **17.41/20 (87%)** · 23.04/35 (66%) · 10.96/20 (55%) |
| — paths | **~0.6 / 25** — generator inadequate (F-042, F-057) |
| — 95% CI on total | [49.70, 53.08] |
| — mean length ratio | **0.9811** |
| Hole-chain classifier | **0.970** held out, vs 0.374 for rules (F-047, F-051) |
| Block-order classifier | **0.896** held out, vs 0.349 modal (F-053) |
| Tool *type* accuracy | **100%** on aligned slots (F-052) |
| Chamfer removal geometry | **exact** (half-space cut, F-045) |
| Pocket removal geometry | approximate — the weakest link in medium |
| Tool-path generation | **broken** — engine is validated, generator is not (F-042) |
| Operation count | mean length ratio 0.853; absolute error 2.885 ops/part |
| `AREA_MILL` count | **exact on 200/200 parts** |
| `FLOOR_WALL` count | exact on 68% of parts (was 44%) |
| Tool-path scoring in the loop | not wired into `run_baseline.py` yet |
| Test set | not released ("Shared soon") |

## Where the project stands

The geometry is largely solved and validated. **What remains is prediction.**
Given the correct operations, order and tools, we can already produce
tool paths scoring 25/25 and the IPWs that follow from them. Effort should now
move to Phase 3 (recovering the rules) and Phase 4 (predicting from the BRep).

## Next up

Reordered after F-047/F-048, which changed what is worth doing.

1. **Pocket *recognition*, not counting (F-048).** 22.5% of `FLOOR_WALL`
   operations belong to pockets whose floor face is never detected — the largest
   remaining count error, and it lives in `features.py`. A model cannot reach it.
2. **Tool-path generation (F-042).** Still 0.00/25 held out, the biggest block of
   unclaimed points, and the sweep engine scoring it is already validated at
   ≈23.5/25 on real paths. Needs real area clearing for pockets.
3. **Tool selection (7.77/20)** — never analysed. F-026 says 37.4% of operations
   use a near-deterministic tool, so there is likely cheap ground here.
4. **Retrain the hole classifier on more parts** — it saw 2,042 of 10,000 and the
   chain tail may be under-covered.
5. Round 1 deliverables: 3-minute video, public methods write-up,
   `requirements.lock.txt`. None exist; Round 2 grades all of them.
6. Ask the organizers Q-001 (rubric arithmetic) and Q-009 (does the official
   scorer denoise the IPW difference — worth ~15% of the path tier).

### Earlier queue, still valid

Reordered after F-037. **Operation count is now the single objective** — it drives
the easy tier's 20 points *and* the medium tier's 35.

1. **Fix operation count.** Current mean length ratio ≈0.78; every 0.01 of ratio
   is worth ~0.35 medium points plus easy-tier gains. Two known defects:
   - over-generation on pocket-heavy parts (`00008`: 11 predicted vs 5 actual) —
     each recognised floor patch becomes its own `FLOOR_WALL` operation;
   - chamfer count is a guess (one `AREA_MILL` per slanted face).
   Validate against the paper's mix (center 28.8 / corner 27.9 / edge 27.8 /
   slot 15.5%; 16,280 chamfers) to find where the count is wrong.
2. **Easy: fix ordering.** F1 already 0.88–0.93 against Levenshtein 0.52–0.85 —
   the bag is right, the order is not. Model precedence instead of the fixed
   chamfer → pocket → hole block order.
3. **Wire tool-path scoring into `run_baseline.py`** so all 100 points are
   measured, not 75. The sweep engine already scores ≈23.5/25 given correct
   inputs (F-021) — worth knowing what it scores on *predicted* ones.
4. **Q-013 — what selects `HOLE_MILLING` and `SPOT_DRILLING`.** Now testable
   against pocket recognition: does the hole sit inside a pocket?
5. Scale the baseline well beyond 12 parts; the F-037 relationship should be
   re-fitted on a few hundred.
6. **Deferred until length is right (F-037):** exact pocket footprints with
   fillets, chamfer wedge geometry, higher revolve resolution. All worth ~0.01
   IoU each and worthless before then.
7. Round 1 deliverables — 3-minute video, methods write-up, reproducible docs —
   none exist yet, and Round 2 grades all of them.

---

## Template for new entries

```
### HH:MM — Short title
What was done.

**▲ SURPRISE / ◆ DECISION** — only when genuinely one or the other.

**Learned:** the takeaway, cross-referenced to F-nnn if it became a finding.
```
