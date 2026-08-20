# Findings Log — ASME CIE 2026 Hackathon, Problem 1

Working notes on the data, the metrics, and what they imply for modelling.
Raw material for the Round 1 presentation video and the Round 2 methods write-up.

> **Gitignored on purpose.** This is a lab notebook, not the deliverable.
> The public documentation the rubric grades ("clarity and completeness of the
> documentation provided") will be a curated document derived from this one —
> keep that distinction in mind when a finding here is provisional.

Each finding carries its evidence and a reproduce command so nothing has to be
taken on trust when it reaches a slide.

**Conventions.** `F-nnn` = finding, `Q-nnn` = open question.
Status: `confirmed` (measured on real data) · `provisional` (single sample or
inferred) · `open`.

---

## Contents

| ID | Finding | Status |
|---|---|---|
| [F-001](#f-001) | `o1` is fully determined by `o2` — never predict it | confirmed |
| [F-002](#f-002) | `OTHER` validates but cannot score | confirmed |
| [F-003](#f-003) | Medium IoU pays 15/35 for modelling no machining at all | confirmed |
| [F-004](#f-004) | Most operations are invisible to the medium metric | confirmed |
| [F-005](#f-005) | Medium and hard-toolpath are the same geometry problem | confirmed |
| [F-006](#f-006) | Rubric tables don't sum to their section budgets | confirmed |
| [F-007](#f-007) | Severe class imbalance in the operation vocabulary | confirmed |
| [F-008](#f-008) | Only BRep + images available at inference | confirmed |
| [F-009](#f-009) | Mesh booleans are exact enough for the 0.999 band | confirmed |
| [F-010](#f-010) | Ground truth is deterministic, and that is the stated target | confirmed |
| [F-011](#f-011) | Chamfer milling is 3D ramping, not 2.5-axis stepping | confirmed |
| [F-012](#f-012) | `.ptp` comments carry the operation label and tool id | confirmed |
| [F-013](#f-013) | The NC dialect is tiny, modal, and posts generic tool numbers | confirmed |
| [F-014](#f-014) | Every cutting tool is convex, making swept volume exact and cheap | confirmed |
| [F-015](#f-015) | Sweeping the full corpus costs ~50 h single-threaded | confirmed |
| [F-016](#f-016) | **Swept volume validated against ground truth at IoU 0.99997** | confirmed |
| [F-017](#f-017) | `operations.json` is far richer than documented | confirmed |
| [F-018](#f-018) | `details.txt` gives exact tool parameters — Q-006 resolved | confirmed |
| [F-019](#f-019) | The documented folder layout is wrong in two places | confirmed |
| [F-020](#f-020) | Mesh "repair" destroyed valid thin-wedge solids | confirmed |
| [F-021](#f-021) | **Sweep validated across all 7 subtypes: ≈23.5/25 weighted** | confirmed |
| [F-022](#f-022) | IPW differences carry 17-micron tessellation sheets | confirmed |
| [F-023](#f-023) | Three NC-parsing bugs, each silent and severe | confirmed |
| [F-024](#f-024) | Overcut and undercut were inverted vs. the rubric | confirmed |
| [F-025](#f-025) | Tiny-volume operations are the residual failure mode | confirmed |
| [F-026](#f-026) | Operation names are a 29-word feature taxonomy | confirmed |
| [F-027](#f-027) | Sequences are tool-blocked, not sorted — and what that buys | confirmed |
| [F-028](#f-028) | No augmentation or filtering used yet; what applies | open |
| [F-029](#f-029) | **The easy tier's real target is ~4.5 (label, count) pairs** | confirmed |
| [F-030](#f-030) | **No CAD kernel needed — the STEP is planes and cylinders** | confirmed |
| [F-031](#f-031) | Feature recognition reproduces the paper's statistics | confirmed |
| [F-032](#f-032) | ~~Hole diameter > largest tool ⟹ milled~~ | **REFUTED** by F-034 |
| [F-033](#f-033) | Only 14 operation chains cover every hole *(later: 15, F-051)* | confirmed, count updated |
| [F-034](#f-034) | What decides drilling strategy — and what still doesn't | partial |
| [F-035](#f-035) | **First end-to-end submission: 21.97/100, all formats valid** | confirmed |
| [F-036](#f-036) | Generated IPWs score worse than raw stock — *but see F-037* | superseded |
| [F-037](#f-037) | **Medium IoU ≈ length ratio (r = 0.999). Geometry is ~1%** | confirmed |
| [F-038](#f-038) | Count errors traced per label: 21.97 → 28.07 | confirmed |
| [F-039](#f-039) | Large bores are milled — the F-034 band missed the top end | confirmed |
| [F-040](#f-040) | **Blind-hole bottoms were counted as pockets: 44% → 68%** | confirmed |
| [F-041](#f-041) | Some pockets take two operations; no geometric predictor found | open |
| [F-042](#f-042) | **All 100 points measured: 38.24. Tool paths score ~2%** | confirmed |
| [F-043](#f-043) | Pecked holes need drilling on both sides of the peck | confirmed |
| [F-044](#f-044) | **Why medium cannot reach 80% by counting alone** | confirmed |
| [F-045](#f-045) | Chamfer removal is an exact half-space cut, not a wedge | confirmed |
| [F-046](#f-046) | Three rules matched the marginal and lost points | confirmed |
| [F-047](#f-047) | **A learned chain classifier beats hand-tuning 0.948 vs 0.391** | confirmed |
| [F-048](#f-048) | The same model **fails** on pockets — and that is informative | confirmed |
| [F-049](#f-049) | ⚠️ **An unstated rubric assumption is worth 26% of the medium tier** | confirmed |
| [F-050](#f-050) | Most tuning decisions were made inside the noise floor | confirmed |
| [F-051](#f-051) | Only 20% of the corpus was being used; the rest is free accuracy | confirmed |
| [F-052](#f-052) | Tool *type* is 100% correct; the whole tool loss is diameter | confirmed |
| [F-053](#f-053) | **Our fixed block order was right on 26.5% of parts** | confirmed |
| [F-054](#f-054) | The images cannot help — we are discarding the data, not missing it | confirmed |
| [F-055](#f-055) | 🔴 **One shadowed variable cost 8.72 points** | confirmed |
| [F-056](#f-056) | Construction points were inflating every bounding box | confirmed |
| [F-057](#f-057) | Pocket area clearing; why paths remain near zero | partial |
| [F-058](#f-058) | **Easy hits 87%. Medium's last 14 points are not geometry** | confirmed |
| [F-059](#f-059) | **Medium is capped by an ordering the geometry does not contain** | confirmed |
| [F-060](#f-060) | **The 400-part evaluation slice checks out against 1,600 more** | confirmed |
| [F-061](#f-061) | **A proper hyperparameter sweep would have shipped a worse hole model** | confirmed |
| [F-062](#f-062) | **Gradient boosting was never compared against other model families, until now** | confirmed |
| [F-063](#f-063) | **Feature importance: 4 inputs carry 95%, and 2 are dead weight** | confirmed |

---

<a id="f-001"></a>
### F-001 — `o1` is fully determined by `o2`, so only the subtype needs predicting
**Status:** confirmed · **Tier:** Easy · **Source:** Dataset_Description.pdf Tables 3–4

**Finding.** The main label carries no independent information. Cross-referencing
the two published frequency tables, the counts line up exactly:

| `o2` subtype | count | implied `o1` | `o1` count |
|---|---:|---|---:|
| `AREA_MILL` | 20,067 | `mill_contour` | 20,067 |
| `FLOOR_WALL` | 18,560 | `mill_planar` | 18,560 |
| `DRILLING` | 30,377 | `hole_making` | — |
| `SPOT_DRILLING` | 14,189 | `hole_making` | — |
| `DEEP_HOLE_DRILLING` | 4,467 | `hole_making` | — |
| `HOLE_MILLING` | 3,470 | `hole_making` | — |
| `BORING_REAMING` | 572 | `hole_making` | — |
| | | `hole_making` total | 53,075 |

`AREA_MILL` and `mill_contour` match to the unit; so do `FLOOR_WALL` and
`mill_planar`. The five hole-making subtypes sum to 30,377 + 14,189 + 4,467 +
3,470 + 572 = **53,075**, exactly the `hole_making` count.

**Implication.** The label space is 7 classes, not 3 × 7 = 21. A model should
predict `o2` and derive `o1` by lookup, which removes an entire error mode from
the easy tier at zero cost and slightly sharpens the F1 denominator.

**Slide potential.** Clean opening insight — "we reduced the label space before
training a single model." Table above renders directly.

**Implemented in** `src/machineplan/vocab.py` (`SUBTYPE_TO_MAIN`, `infer_main_label`).

---

<a id="f-002"></a>
### F-002 — `OTHER` passes validation but can only score as a miss
**Status:** confirmed · **Tier:** Easy · **Source:** `vocabularies.json` vs. Dataset_Description.pdf

**Finding.** The official `vocabularies.json` accepts `OTHER` for both `o1` and
`o2`, and `validate_submission.py` will happily pass a submission full of it.
The dataset contains **zero** `OTHER` labels across all 91,702 operations.

**Implication.** `OTHER` is a trap: it looks like a safe fallback for
low-confidence predictions but is strictly worse than guessing the majority
class. Never emit it. Any model with an abstain option must map abstention onto
a real label.

**Slide potential.** Good "reading the fine print" beat — validation passing is
not the same as scoring.

**Implemented in** `src/machineplan/vocab.py` (`VALIDATOR_O1` vs `DATASET_O1`).

---

<a id="f-003"></a>
### F-003 — The medium tier pays 15 of 35 points for modelling no machining at all
**Status:** confirmed · **Tier:** Medium · **Source:** measured on `sample_submission/medium/`

**Finding.** Measured against the real 7-operation sample sequence:

| Baseline | Mean IoU | Rubric points |
|---|---:|---:|
| Constant — submit the first IPW for every operation | 0.96996 | **15 / 35** |
| Lag-by-one — submit the previous operation's IPW | 0.99313 | **25 / 35** |
| Exact | 1.00000 | 35 / 35 |

The cause is that the whole plan removes only **600,142 mm³ from a 12,647,438 mm³
block — 4.75%**. Consecutive IPWs are therefore nearly identical, and IoU between
any two of them is high by construction.

**Implication.** Two things follow, and they pull in opposite directions:
1. A geometrically *approximate* IPW already scores respectably, so the medium
   tier is unlikely to be where a submission collapses.
2. The marginal 10 points from 25 → 35 demand near-exact geometry, which is by
   far the most expensive thing on the board.

Read as guidance on effort allocation, not as a shortcut — see F-010 on the
anti-hack clause. The honest framing for the write-up is that we *measured the
metric's sensitivity before optimising against it*, which is a defensible and
rigorous thing to have done.

**Slide potential.** Strong. A three-bar chart (0.970 / 0.993 / 1.000 with the
band thresholds overlaid) makes the cliff structure legible instantly, and it
sets up the argument for where we spent our compute.

**Caveat.** Single part, 7 operations. Dataset mean is 9.17 operations per part.
Re-run across the full dataset once downloaded and replace these numbers.

**Reproduce.** `.venv/Scripts/python scripts/baseline_probe.py`

---

<a id="f-004"></a>
### F-004 — Most individual operations are invisible to the medium metric
**Status:** confirmed · **Tier:** Medium · **Source:** measured on `sample_submission/medium/`

**Finding.** Reaching IoU 0.999 on a 12,647,438 mm³ block allows a total error
budget of about **12,647 mm³**. Per-operation material removal on the sample:

| Op | Removed (mm³) | vs. 0.999 error budget |
|---:|---:|---|
| 2 | 10,835.7 | below |
| 3 | 287,003.4 | **above** |
| 4 | 283,783.2 | **above** |
| 5 | 32.0 | below |
| 6 | 6,106.0 | below |
| 7 | 12,382.0 | below |

Four of the six measurable operations each remove less material than the error
budget for the top band. Operation 5 removes 32 mm³ — roughly 0.00025% of the
block, almost certainly a spot-drilling peck.

**Implication.** Geometric precision is worth paying for on the *few large
pocket operations* and nearly worthless on the *many small drilling operations*.
That is the opposite of where operation *count* sits (hole-making is 58% of all
operations), so the easy tier and the medium tier reward attention to different
parts of the plan. Worth stating explicitly in the write-up.

**Slide potential.** Pairs with F-003. A log-scale bar of per-operation removed
volume against a horizontal error-budget line tells the story in one image.

**Reproduce.** `.venv/Scripts/python scripts/baseline_probe.py`

---

<a id="f-005"></a>
### F-005 — Medium and hard-toolpath are the same geometry problem
**Status:** confirmed · **Tiers:** Medium (35) + Hard path (25) · **Source:** Rubrics.pdf

**Finding.** The rubric scores a submitted tool path by comparing its swept
volume against "the boolean difference of before/after IPW meshes". That is the
identity

```
swept_volume(operation k)  ==  IPW(k-1) - IPW(k)
```

which is exactly the quantity that separates consecutive medium-tier IPWs.

**Implication.** One removal-volume engine produces both deliverables: the medium
STLs are the running difference, and the hard tool paths are paths that sweep
those same volumes. **60 of the 100 points share a single backbone.** This is the
central architectural decision of the solution and should be the spine of the
presentation.

**Slide potential.** Highest of any finding here. One diagram — block, minus
volume, equals next IPW, with the same volume feeding the toolpath generator —
carries the entire method section.

**Implemented in** `src/machineplan/scoring/geometry.py` (`removed_volume`).

---

<a id="f-006"></a>
### F-006 — Two rubric tables don't sum to their stated section budgets
**Status:** confirmed · **Tier:** Hard · **Source:** Rubrics.pdf §3.1.3

**Finding.**
- "Tool selection (type and diameter) **(20 points)**" — the table's best row awards **10**.
- "Tool path geometry **(25 points)**" — IoU table tops out at **15**, and the
  over/under-cut table awards "Points (each)" up to **7.5**, i.e. 15 + 7.5 + 7.5 = **30**.

Section totals themselves are consistent (20 + 35 + 20 + 25 = 100); only the
sub-tables overshoot or undershoot. Band edges are separately ambiguous: 0.0–0.1
and 0.1–0.2 both contain 0.1.

**Implication.** The resolution changes the relative value of tool-type accuracy
versus tool-path precision, which changes where effort belongs. Our scorer
computes tables exactly as printed and then rescales to the stated budget
(`SCALE_TO_SECTION_BUDGET`), with boundaries resolved in the participant's
favour. Both choices are explicit rather than buried.

**Action.** → **Q-001**: ask the organizers.

**Implemented in** `src/machineplan/scoring/rubric.py`.

---

<a id="f-007"></a>
### F-007 — Severe class imbalance in the operation vocabulary
**Status:** confirmed · **Tier:** Easy · **Source:** Dataset_Description.pdf Table 4

**Finding.** Across 91,702 operations:

| Subtype | Count | Share |
|---|---:|---:|
| `DRILLING` | 30,377 | 33.1% |
| `AREA_MILL` | 20,067 | 21.9% |
| `FLOOR_WALL` | 18,560 | 20.2% |
| `SPOT_DRILLING` | 14,189 | 15.5% |
| `DEEP_HOLE_DRILLING` | 4,467 | 4.9% |
| `HOLE_MILLING` | 3,470 | 3.8% |
| `BORING_REAMING` | 572 | 0.6% |

The top three cover 75.2%. `BORING_REAMING` is 53× rarer than `DRILLING`.

**Implication.** Accuracy is a misleading training signal. The easy tier is
scored on multiset F1 and edit distance, both of which are sensitive to the rare
classes appearing in the right count and position. Expect to need class
weighting or resampling, and to report per-class recall rather than accuracy.

**Slide potential.** Standard but necessary — one bar chart establishing why we
weighted the loss.

---

<a id="f-008"></a>
### F-008 — Only the BRep and images exist at inference time
**Status:** confirmed · **Source:** Tutorial_Hackathon_Problem1.pdf p.3

**Finding.** The tutorial partitions the file types explicitly:
- Available at inference: `.stp` (BRep), `.png` (4 rendered views)
- Training only / prediction targets: `.stl` / `.stl.txt`, `details.txt`, `.ptp`

**Implication.** The input is one static design geometry; everything sequential
must be *generated*, not read. Notably the IPW chain has to be produced
autoregressively — each predicted IPW becomes the state for the next prediction,
so errors compound along the sequence. The four PNGs are a genuine second
modality and are free to use.

**Slide potential.** Frames the problem honestly: this is sequence generation
from a single static input, not per-step classification.

---

<a id="f-009"></a>
### F-009 — The mesh boolean backend is exact enough for the 0.999 band
**Status:** confirmed · **Tooling** · **Source:** verified locally 2026-08-19

**Finding.** `trimesh` 5.0 with the `manifold3d` backend returns exact volumes on
a known case: a 10×10×10 box minus a 5×5×20 box gives **750.0** against an
analytic 750, watertight. Voxel IoU at a 1 mm pitch on a 200–500 mm part
resolves only to ~1e-3 — which *straddles* the top medium band rather than
resolving it.

**Implication.** Exact mesh booleans are mandatory for scoring; voxel IoU is a
diagnostic fallback only. Anything that reports a voxelised IoU as a headline
number is unreliable at the band boundary that matters most.

**Implemented in** `src/machineplan/scoring/geometry.py` (`compare_volumes` vs `voxel_iou`).

---

<a id="f-010"></a>
### F-010 — The ground truth is deterministic, and reproducing it is the stated goal
**Status:** confirmed · **Source:** Kickoff p.12, Rubrics.pdf §3.2, Dataset_Description.pdf §7

**Finding.** Ground-truth plans come from deterministic rules in the Siemens NX
knowledge base, applied without human judgement. The kickoff states the goal is
"to learn the optimal sequence generated by deterministic rules within Siemens
Designcenter NX". The dataset provides exactly **one** valid sequence per part,
though the kickoff acknowledges machining admits many.

Set against that, Rubrics.pdf §3.2 warns: "Reverse engineering or hacky solutions
will be penalized."

**Implication.** These are reconcilable, and the distinction should be stated
plainly in the write-up rather than skirted:
- **Legitimate** — inferring and modelling the *machining rules* (tool-driven
  feature decomposition, precedence from feature interaction). This is the
  sanctioned target.
- **Penalised** — exploiting the *evaluation harness* or the *dataset's
  construction*: keying on part IDs, fitting to test-set artifacts, gaming IoU
  with degenerate meshes.

Because only one sequence is labelled per part, a genuinely valid alternative
plan scores as wrong. That is a real limitation to name in the Round 2
"generalizability and limitations" section, which explicitly asks for it.

**Slide potential.** The intellectual-honesty beat. Judges reward naming this
rather than pretending the metric is ground truth about machining.

---

<a id="f-011"></a>
### F-011 — Chamfer milling is 3D ramping, not 2.5-axis constant-Z stepping
**Status:** confirmed · **Tier:** Hard (path) · **Source:** parsed `sample_submission/hard_tool_path/…operation_01.ptp`

**Finding.** The natural way to compute a swept volume for 2.5-axis work is to
decompose the path into constant-Z passes, buffer each 2D polyline by the tool
radius, and extrude. Measured on the real sample AREA_MILL operation, that
assumption does not hold:

| Motion class | Count | Share |
|---|---:|---:|
| Ramping (X/Y **and** Z both change) | 250 | **91.9%** |
| Planar (constant Z) | 22 | 8.1% |
| Vertical (pure plunge) | 0 | 0% |

The path traces a chamfer along one block edge: X spans the full 339 mm of the
block, Y spans only 17.7 mm, Z spans 71.1–98.8 mm. The tool descends in a tight
arc at one end (X moves 0.34 mm while Z drops 2.6 mm), traverses the full length,
and arcs back up.

**Implication.** The cheap constant-Z buffer-and-extrude approach would
mis-model ~92% of this operation's motion. Since `AREA_MILL` is **21.9% of all
91,702 operations** — and appears to be the chamfering strategy throughout — the
swept-volume engine must handle general 3D sweeps as a first-class case, not a
fallback. Compounding it, a chamfer mill is a tapered tool, so the swept solid is
a cone frustum dragged along a 3D curve, not a cylinder.

This is the single largest piece of unbuilt work and the main risk to the
25-point tool-path score.

**Slide potential.** Good "the obvious approach doesn't work" beat, and it
justifies whatever the eventual engine costs. The 91.9% figure is the hook.

**Caveat.** One operation from one part. Confirm the ramping share across
operation types once the dataset lands — hole-making and `FLOOR_WALL` pocketing
are likely much closer to true 2.5-axis.

**Reproduce.** `.venv/Scripts/python scripts/inspect_ptp.py <file.ptp>`

---

<a id="f-012"></a>
### F-012 — `.ptp` comments carry the operation label and the tool library id
**Status:** confirmed · **Tiers:** Easy + Hard · **Source:** sample `.ptp`

**Finding.** Every tool path opens with a comment naming its operation subtype
and the NX tool library id:

```
(AREA_MILL , TOOL : UGT0205_001)
```

plus a header block giving `CREATED BY`, `DATE`, and `PARTNAME`.

**Implication.** Two uses. First, as training supervision: the `.ptp` files
independently label each operation's `o2` and its exact tool, so the toolpath
corpus can be joined to the operation sequence without relying solely on
`details.txt`. It also gives a cross-check on our reading of both formats — if
the `.ptp` comment and `details.txt` disagree, our parser is wrong.

Second, for *output*: our generated `.ptp` files should reproduce this comment
convention. The rubric says G-code is not compared textually, but a well-formed
header costs nothing and makes the submission legible to a human judge.

**Slide potential.** Minor, but supports a "we used every modality" point.

---

<a id="f-013"></a>
### F-013 — The NC dialect is tiny, heavily modal, and posts generic tool numbers
**Status:** confirmed · **Tier:** Hard (path) · **Source:** sample `.ptp`

**Finding.** The whole sample operation uses only twelve distinct codes:
`G0 G1 G17 G21 G43 G54 G90 G94`, `M2 M3 M5 M6`. No arcs (`G2`/`G3`) and no
canned cycles appear in this file, though both are expected in hole-making.

It is aggressively modal: `G1` is declared once at block N22 and 250 subsequent
blocks carry only the axis words that changed — many carrying a single word such
as `X0.621`. Feed (`F250.`) is stated once and persists.

Two details that matter for generation:
- The tool change posts as **`T00 M6`** with **`H0`** length compensation — a
  generic number, not a tool identity. Tool identity lives only in the comment
  (F-012), so a generated path must not rely on the `T` word to convey it.
- Cutting length is 4,781 mm against just 27 mm of rapids: the ground-truth paths
  are highly optimised, with almost no wasted air motion. Any path we generate
  will be compared on swept volume, not efficiency, but a path with wildly more
  rapid motion is a signal we've mis-modelled the strategy.

**Implication for parsing.** Modal state is the entire difficulty. Our parser
also had to get program-start seeding right: the first block that establishes all
three axes must emit *no* move, because machine position is unknown beforehand
and assuming an origin fabricates a long cut through the stock. Verified against
the real file — `N16` seeds X/Y, `N18` seeds Z, `N20` is the first genuine move.

**Slide potential.** Low on its own; useful as a credibility detail in the
methods write-up.

**Implemented in** `src/machineplan/parsing/ptp.py`, 20 tests in `tests/test_ptp.py`.

---

<a id="f-014"></a>
### F-014 — Every cutting tool is convex, which makes the swept volume exact
**Status:** confirmed · **Tiers:** Medium + Hard (path) · **Source:** derived, verified in tests

**Finding.** Every tool in the contest vocabulary is a solid of revolution about
the spindle axis, and every one is **convex**: an endmill is a cylinder, a
chamfer mill is a truncated cone on a shank, a drill is a cylinder with a
conical point (a bullet — still convex).

That matters because of a standard result: for a convex body `K` translated
along a segment from `a` to `b`, the swept region is the Minkowski sum of `K`
with the segment, which for convex `K` is exactly

```
conv( (K + a) ∪ (K + b) )
```

— the convex hull of the tool placed at both endpoints.

**Implication.** Each linear move can be swept **exactly** by a convex hull of
two tool placements, rather than approximated by stamping the tool at densely
sampled positions along the path. It is both more accurate *and* far cheaper:
272 hulls instead of ~4,944 tool placements for the sample operation. Residual
error enters only through arc chording and the revolve resolution (64 sections,
~0.16% radius deficit), both of which are tunable.

Convexity is load-bearing, so it is asserted directly in the test suite: every
tool's mesh volume must equal its own convex hull's. Any future tool with an
undercut profile (a T-slot cutter, say) breaks the identity and would need
decomposing into convex pieces first.

**Verified against closed forms.** A cylinder of radius `r` and height `h`
dragged a distance `L` must sweep `πr²h + 2rLh`; a plunge must sweep
`πr²(h + d)`; retracing a segment must not inflate the result; disjoint moves
must add. All hold to 0.5%.

**Slide potential.** High — this is the one genuinely elegant piece of
mathematics in the solution, and it explains why our geometry is exact where a
voxel or point-sampling approach would only be approximate. One diagram of a
tool at two positions with the hull drawn around it carries it.

**Implemented in** `src/machineplan/geometry/sweep.py` (`segment_sweep`),
25 tests in `tests/test_sweep.py`.

---

<a id="f-015"></a>
### F-015 — Sweeping the full corpus costs ~50 hours single-threaded
**Status:** confirmed · **Tier:** Hard (path) · **Source:** timed on the sample operation

**Finding.** The real AREA_MILL path (272 cutting segments) sweeps in **1.97 s**,
producing a watertight solid of 444,695 mm³ from 11,996 triangles. Extrapolated
across the dataset's **91,702 operations that is ~50 hours** of single-threaded
compute.

**Implication.** Three consequences:
1. Any pipeline that sweeps the whole corpus needs multiprocessing. The work is
   embarrassingly parallel per operation, so near-linear scaling is available;
   on 8 cores this is ~6 h, which is tractable overnight.
2. It is worth questioning whether the full corpus *needs* sweeping. Ground-truth
   removal volumes are obtainable far more cheaply as `IPW(k-1) − IPW(k)` (one
   boolean) than by simulating the tool path. Sweeping is needed to *score* our
   own generated paths, not to build training targets.
3. Round 2 explicitly grades "effectiveness and computational efficiency", so
   this number and what we did about it belong in the write-up.

**Also noted.** The raw sweep includes air: its bounds run X −10…349 against a
block starting at 0, and Z up to 119.6 against a stock top near 98.8. Comparing a
sweep to ground-truth removal requires clipping it to the stock actually present
(`material_removed`), or the IoU is meaningless.

**Slide potential.** Good efficiency beat, especially paired with whatever
speedup we land.

**Reproduce.** `.venv/Scripts/python scripts/sweep_demo.py`

---

<a id="f-016"></a>
### F-016 — The swept-volume engine reproduces ground truth at IoU 0.99997
**Status:** confirmed · **Tier:** Hard (path, 25 pts) · **Source:** `scripts/validate_sweep_against_truth.py`

**Finding.** The headline result so far. On `featured_part_00001` operation 1
(AREA_MILL, chamfer mill), three independently derived quantities agree:

| Source | Volume removed (mm³) | Error |
|---|---:|---:|
| `operations.json` → `volume_removed_mm3` | 53,100.9074 | — |
| `IPW(k-1).volume − IPW(k).volume` from the meshes | 53,101.0101 | 0.0002% |
| **Our swept volume, clipped to stock** | **53,101.5844** | **0.001%** |

Scored the way the rubric scores it — our swept solid against the boolean
difference of the before/after IPWs:

```
IoU 0.99997    overcut 0.00002    undercut 0.00001
```

That is the **top band on all three sub-metrics**: IoU ≥ 0.99 → 15 points,
overcut ≤ 0.05 → 7.5, undercut ≤ 0.05 → 7.5. **25 / 25 on this operation.**

Two corroborating details: our parsed cutting length is 4,781.058 mm against
the metadata's 4,781.061 mm, confirming the NC parser; and the raw sweep is
712,255 mm³, of which all but 53,101 mm³ is air — confirming that clipping to
the present stock is essential, not optional.

**Implication.** *Given the right operation, the right tool, and the right
sequence, the hard tool-path tier is solved.* The remaining hard-tier problem is
entirely one of **prediction** — deciding which operations, in what order, with
which tools — not of geometry. That is a major de-risking of 25 points and it
redirects effort squarely onto Phases 3 and 4.

By F-005 the same engine also produces the medium-tier IPWs, so the same
statement applies to much of that 35 points.

**Caveat.** One operation, of one type (chamfering), on one part. The next step
is to run this across a stratified sample covering all seven subtypes —
especially the drilling operations, which use canned cycles and tool geometries
this test did not exercise.

**Slide potential.** The strongest result available. A three-row table of
agreeing volumes plus the IoU figure is the "our method works" slide.

**Reproduce.** `.venv/Scripts/python scripts/validate_sweep_against_truth.py`

---

<a id="f-017"></a>
### F-017 — `operations.json` carries far more supervision than the docs suggest
**Status:** confirmed · **All tiers** · **Source:** real archive

**Finding.** Dataset_Description.pdf describes this file only as "CAM operation
sequence metadata". It actually contains, per part, a `machining_summary`
(`total_cutting_time_min`, `total_non_cutting_time_min`, `total_toolpath_time_min`,
`tool_changes`, `num_operations`) and per operation:

| Field | Example | Why it matters |
|---|---|---|
| `sequence_number` | `0` | 0-based order (submissions are 1-based — off-by-one risk) |
| `name` | `MILL_CORNER_NOTCH_RECTANGULAR` | **names the feature being cut** |
| `type` | `VolumeBased25DMillingOperation` | NX operation class |
| `tool_name` | `UGT0205_001` | joins to the tool library |
| `volume_mm3` | `12647438.334` | IPW volume *after* this operation |
| `volume_removed_mm3` | `53100.907` | **ground-truth removal, free** |
| `toolpath_cutting_length_mm` | `4781.061` | validates a generated path |
| `toolpath_time_min` | `19.127` | cutting/non-cutting split |

**Implication.** Three big ones:
1. `volume_removed_mm3` is a **free, exact scalar label** for every one of the
   91,702 operations — no mesh booleans needed to get it. A model can be
   supervised on removal volume directly, and it is the cheap sanity check on
   any generated tool path.
2. `name` fields such as `MILL_CORNER_NOTCH_RECTANGULAR` **leak the feature
   type**. This is the most direct evidence available of the feature→operation
   mapping that NX applied, i.e. the deterministic rules we are trying to
   recover (F-010). Mining the distribution of these names against part geometry
   is the highest-value analysis available.
3. `sequence_number` is **0-based** while submissions require 1-based
   `operation_number`. An easy silent off-by-one.

**Slide potential.** High for the methods section — "the labels were richer than
the documentation implied, and here's what we did with that."

---

<a id="f-018"></a>
### F-018 — `details.txt` gives exact tool parameters (resolves Q-006)
**Status:** confirmed · **Tier:** Hard · **Source:** real archive

**Finding.** Each operation's `details.txt` contains an NX report with a full
tool parameter block. For `UGT0205_001`:

```
Template Type: mill_contour        <- this is o1
Template Subtype: AREA_MILL        <- this is o2
Tool Type : Chamfer Mill
(D) Diameter          =  20.000 mm
(R1) Lower Radius     =   0.000 mm
(L) Length            =  75.000 mm
(C) Chamfer Length    =   8.500 mm
(B) Chamfer Angle     =  45.000 °
(FL) Tool Flute Length =  50.000 mm
```

**Our inferred geometry was exactly right.** The chamfer profile derived from
the tool *name* ("Chamfer Mill 20 x 3 x 45 deg." → 3 mm tip, 45° flank →
tip height `(10 − 1.5)/tan 45° = 8.5 mm`) matches the published
`(C) Chamfer Length = 8.5000 mm` to four decimal places.

The one correction: our default flute length was `diameter × 4 = 80 mm`; the
real `(FL)` is 50 mm. Defaults must be replaced with parsed values.

**Also note** `Template Type` / `Template Subtype` are literally `o1` and `o2`.
So `details.txt` is a third independent source of the operation labels, alongside
`operations.json` `name` and the `.ptp` comment (F-012) — three-way cross-check.

**Implication.** Q-006 is resolved: tool geometry comes from data, not guesswork.
Build a tool library by parsing `details.txt` once per distinct tool id (431 of
them) and cache it, rather than re-parsing 91,702 files.

---

<a id="f-019"></a>
### F-019 — The documented folder layout is wrong in two places
**Status:** confirmed · **Tooling** · **Source:** real archive vs. Fig. 1

**Finding.** Two mismatches between Dataset_Description.pdf Fig. 1 and the
archive:

| Documented | Actual |
|---|---|
| `part_00001/part_00001.stp` | `featured_part_00001/featured_part_00001.stp` |
| four images (3 wireframe + 1 shaded) | **five**: adds `isometric_wireframe` |

The `featured_part_` prefix explains why the contest's sample submissions are
named `featured_part_00001_*` — a detail that would otherwise look arbitrary.

**Implication.** Discovering structure from the archive's central directory
rather than hardcoding documented paths is what made the reader work first try.
Worth keeping that principle for the test set, whose naming is unknown.

There is also a **fifth input modality** available at inference that we had not
counted: an isometric *wireframe* view alongside the shaded one.

---

<a id="f-020"></a>
### F-020 — Unconditional mesh "repair" destroyed valid thin-wedge solids
**Status:** confirmed (fixed) · **Tiers:** Medium + Hard · **Source:** debugging F-016

**Finding.** Our `as_solid` helper applied `nondegenerate_faces()` and
`unique_faces()` culling to every mesh before any boolean. On a valid 90-triangle
chamfer removal volume this **deleted 5 legitimate faces** and turned a
watertight solid into a non-watertight one, which the boolean backend then
rejected outright.

The cause: a chamfer removal volume is a long thin wedge — 53,101 mm³ spread
along 339 mm — so it genuinely contains sliver triangles. Generic "cleanup"
cannot tell a sliver that is noise from a sliver that is the geometry.

**Implication.** Repair now escalates only when a mesh actually fails
`is_volume`, and stops as soon as it passes. Three regression tests pin it,
including one on a deliberately sliver-heavy wedge.

The broader lesson worth carrying: **this failed loudly, but the same bug
applied to a slightly-less-thin solid would have failed silently**, quietly
lowering IoU on exactly the thin-feature operations the hard tier is scored on.
Defensive preprocessing is not free.

**Slide potential.** A good "rigor" beat for Round 2, which explicitly grades
scientific rigor — it shows the validation caught a real defect.

---

<a id="f-021"></a>
### F-021 — The sweep holds across all seven subtypes (resolves Q-007)
**Status:** confirmed · **Tier:** Hard (path, 25 pts) · **Source:** `scripts/validate_sweep_by_subtype.py`

**Finding.** F-016 validated one *chamfering* operation. Stratifying over all
seven `o2` subtypes found that it did **not** initially generalise — and fixing
what broke produced this:

| Subtype | Corpus share | Initial IoU | Final IoU | Final points |
|---|---:|---:|---:|---:|
| `DRILLING` | 33.1% | *error* | **0.99671** | 25 / 25 |
| `AREA_MILL` | 21.9% | 0.99990 | **0.99990** | 25 / 25 |
| `FLOOR_WALL` | 20.2% | *error* | **0.99987** | 25 / 25 |
| `SPOT_DRILLING` | 15.5% | 0.65428 | 0.81623 | 17.1 / 25 |
| `DEEP_HOLE_DRILLING` | 4.9% | 0.00962 | **0.99394** | 25 / 25 |
| `HOLE_MILLING` | 3.8% | 0.64232 | **0.95387** | 20.8 / 25 |
| `BORING_REAMING` | 0.6% | 0.39117 | 0.37709 | 1.2 / 25 |
| **Unweighted mean** | | 0.644 | **0.926** | 21.7 / 25 |
| **Frequency-weighted** | | | | **≈23.5 / 25** |

Five of seven subtypes now exceed IoU 0.99, and those five account for **83.9%**
of all operations in the dataset.

**Implication.** The hard tool-path tier is genuinely solved for the operations
that dominate the corpus. Combined with F-005, the same engine underwrites the
medium tier. The remaining shortfall is confined to very small operations
(F-025), which are worth little in aggregate.

**The methodological point worth presenting:** the single-operation validation in
F-016 was *encouraging and misleading*. It happened to pick the one operation
type that already worked. Stratifying by subtype is what surfaced three separate
silent bugs (F-023). This is the argument for stratified validation over
spot-checks, and it belongs in the Round 2 rigor section.

**Caveat.** 2–3 operations per subtype, drawn from the first 120 parts. Scale to
a larger stratified sample before quoting these as corpus-wide numbers.

**Reproduce.** `.venv/Scripts/python scripts/validate_sweep_by_subtype.py`

---

<a id="f-022"></a>
### F-022 — IPW differences carry 17-micron tessellation sheets
**Status:** confirmed · **Tiers:** Medium + Hard · **Source:** body decomposition of real IPW differences

**Finding.** The IPW meshes are re-triangulated after every operation, so
`IPW(k-1) − IPW(k)` contains, besides the material actually removed, thin sheets
wherever a planar face was tessellated differently. Decomposing two real
differences on `featured_part_00001`:

| Operation | Bodies | Largest body | Largest as % of total |
|---|---:|---|---:|
| op 6, through-drilling | 20 | 6,123 mm³ — the real 9.4 mm hole | **99.8%** |
| op 5, spot-drilling | 18 | 3.26 mm³ — the real dimple | **7.8%** |

The noise bodies have extents like `0.017 × 70.9 × 37.9 mm` — **17 microns
thick**, spanning 71 mm. For the through-hole they are irrelevant. For the spot
drill the difference totals 42.0 mm³ of which only 3.3 mm³ is real: **the noise
is 12× the signal.**

Independent corroboration: our swept volume predicted 3.06 mm³ for that dimple
from first principles, against the 3.26 mm³ real body. **Our sweep was right and
the reference was wrong.**

**Implication.**
1. Locally, references must be denoised before scoring. Filtering is on
   **thickness, not volume** — those sheets are thin but *not* small (18 mm³ is
   far larger than the 3.3 mm³ dimple), so any volume-based filter keeps exactly
   the wrong bodies. Thickness is also physically defensible: the smallest tool
   in the library is 5 mm across, so nothing it removes is tens of microns thick.
2. For the **medium** tier this is harmless — 40 mm³ of noise against a 12.6 M mm³
   part is 3×10⁻⁶ of the IoU.
3. For the **hard** tier it may be unavoidable: if the graders compare against the
   raw difference, a *perfect* tool path scores IoU ≈ 0.07 on a spot-drilling
   operation. That affects ~15% of operations. → **Q-009**, worth raising with
   the organizers.

**Slide potential.** Strong. "Our answer disagreed with ground truth, and our
answer was right" is a memorable beat, and the 17-micron figure is vivid.

---

<a id="f-023"></a>
### F-023 — Three NC-parsing bugs, each silent and each severe
**Status:** confirmed (all fixed) · **Tier:** Hard · **Source:** surfaced by F-021

Stratified validation exposed three independent defects in the NC parser. None
raised an error; each simply produced wrong geometry.

**1. `G4` dwell read as motion.** `N26 G4 X.084` is a *dwell*: pause 0.084
seconds. The `X` is a duration, not a coordinate. The parser read it as an axis
word and dragged the drill 25 mm sideways at full depth, carving a trench through
solid material. Effect on `DEEP_HOLE_DRILLING`: **overcut 6.42, IoU 0.0096**.
Fixing it took that subtype to **IoU 0.9939**.

**2. `G73` missing from the canned-cycle set.** The cycle set covered G81–G89,
but NX also posts `G73` (high-speed peck). An unrecognised cycle fell through to
the "no motion mode" fallback, became a non-cutting *rapid*, and the operation
swept **nothing at all** — reported as "tool path contains no cutting moves".
This silently disabled `DRILLING`, **33.1% of the corpus**. Now IoU 0.9967.

**3. R-format arcs unsupported.** G-code allows an arc as either centre offsets
(`I`/`J`) or a radius (`R`). Only the former was handled, so an R-format arc got
no centre and was treated as a straight chord — collapsing a circular hole-milling
pass into a polygon. `HOLE_MILLING` **0.642 → 0.954**. (Convention: positive `R`
selects the minor arc, negative the major; two centres satisfy any chord.)

Separately, NX's `Tool Type` strings were not what the vocabulary suggested —
`Milling Tool-5 Parameters` for pocketing endmills and `Drilling Tool` for twist
drills — so those operations raised "unmapped tool type" until the map was
extended.

**Implication.** Every one of these was invisible to a single-operation check and
to the unit tests, which used synthetic paths. Only comparison against real
ground truth across *stratified* inputs found them. Each now has a regression
test naming the failure mode.

**Slide potential.** Good rigor material — concrete, specific, and each has a
number attached.

---

<a id="f-024"></a>
### F-024 — Overcut and undercut were inverted relative to the rubric
**Status:** confirmed (fixed) · **Tier:** Hard · **Source:** re-reading Rubrics.pdf §3.1.3

**Finding.** The rubric defines: "Overcut refers to the volume of material
removed that should not have been removed, while undercut refers to the volume of
material that should have been removed but was not." Our implementation had these
the wrong way round — `overcut` computed `|G \ P|` (missed material) and
`undercut` computed `|P \ G|` (excess material).

**Implication.** Because both feed the *same* band table, the total score was
unaffected — which is exactly why it survived. But every diagnostic reading was
mislabelled, and any write-up built on them would have made the opposite claim
about a submission's failure mode. Fixed, with a test for each direction.

**The lesson:** a bug that does not change the bottom line is the hardest kind to
notice and the easiest kind to publish.

---

<a id="f-025"></a>
### F-025 — Tiny-volume operations are the residual failure mode
**Status:** confirmed · **Tier:** Hard · **Source:** F-021 results

**Finding.** After all fixes, the two weak subtypes are precisely the ones that
remove almost nothing:

| Operation | Removed volume | IoU |
|---|---:|---:|
| `SPOT_DRILLING` (part 00001 op 5) | 5.15 mm³ | 0.555 |
| `SPOT_DRILLING` (part 00004 op 2) | 2.30 mm³ | 0.896 |
| `BORING_REAMING` (part 00086 op 4) | 3.70 mm³ | 0.377 |
| `SPOT_DRILLING` (part 00004 op 1) | 4,193 mm³ | 0.998 |

The pattern is unambiguous: the same subtype scores 0.998 on a 4,193 mm³
operation and 0.555 on a 5 mm³ one. **Volume, not operation type, predicts
accuracy.**

At these scales three effects that are negligible elsewhere all bite at once:
residual tessellation noise (F-022), the 64-section revolve discretization
(~0.16% radius error), and sub-millimetre depth conventions.

**Implication.** Worth bounding rather than chasing. `BORING_REAMING` is 0.6% of
operations; `SPOT_DRILLING` is 15.5% but many of its instances are larger and
score well. Options if it proves worth it: raise revolve resolution for small
tools, and check whether the drill-tip depth convention is off by a fraction of
the point length. Not a priority against the prediction work.

---

<a id="f-026"></a>
### F-026 — Operation names are a closed 29-word feature taxonomy (resolves Q-008)
**Status:** confirmed · **All tiers** · **Source:** `scripts/analyze_sequences.py`, all 10,000 parts

**Finding.** Across all 91,702 operations there are only **29 distinct operation
names** (after stripping `_1`, `_2` repeat suffixes) and **4 `type` values**.
The names encode the *feature* and the *strategy*, not just the operation class:

| Name | Count | Share | Distinct tools |
|---|---:|---:|---:|
| `AREA_MILL` | 20,067 | 21.9% | **1** |
| `SPOT_DRILL` | 14,189 | 15.5% | **2** |
| `DRILL_BLIND_HOLE_INTO_CENTER` | 10,498 | 11.4% | 187 |
| `MILL_RECTANGULAR_POCKET` | 6,676 | 7.3% | 53 |
| `DRILL_TO_ENLARGE_THROUGH_HOLE` | 6,430 | 7.0% | 87 |
| `GUN_DRILL_THROUGH_HOLE` | 4,430 | 4.8% | 15 |
| `MILL_CORNER_NOTCH_RECTANGULAR` | 4,311 | 4.7% | 35 |
| `MILL_SLOT` | 4,146 | 4.5% | 36 |
| … 21 more, the smallest with 2 operations | | | |

These map **directly onto the generative feature taxonomy** in
Dataset_Description.pdf §6.1.2: pockets are corner / edge / center / slot, and
holes are through / blind. `MILL_CORNER_NOTCH_RECTANGULAR` is a corner pocket;
`MILL_SLOT` is a slot; `DRILL_TO_ENLARGE_THROUGH_HOLE` is a second pass on an
existing through-hole.

`Geometry Group` corroborates it with 39 values such as `POCKET_RECTANGULAR_STRAIGHT`,
`CORNER_NOTCH_RECTANGULAR`, `SLOT_RECTANGULAR`, `FG_CHAMFER_SURFACE`.

**Implication.** The feature→operation mapping we are trying to recover is
**directly observable in the labels**, not something to infer indirectly. That
makes a rules/geometry approach far more tractable than it looked.

The tool column matters too: `AREA_MILL` uses exactly **one** tool across all
20,067 instances, and `SPOT_DRILL` only two. Together that is 37.4% of all
operations where tool prediction is nearly deterministic — worth a large share of
the 20-point tool score for almost no modelling. By contrast
`DRILL_BLIND_HOLE_INTO_CENTER` spans 187 tools, because drill diameter tracks
hole diameter continuously.

**Slide potential.** High. The name table plus "these *are* the features" is the
bridge from data exploration to method.

---

<a id="f-027"></a>
### F-027 — Sequences are tool-blocked, not sorted
**Status:** confirmed · **Tier:** Easy (20 pts) · **Source:** `scripts/analyze_grouping.py`, all 10,000 parts

**Finding.** Three hypotheses, tested corpus-wide:

| Hypothesis | Holds for |
|---|---:|
| Ordered chamfers → pockets → holes | 54.45% |
| Sorted by NX `Order Group` rank | 27.93% |
| **Each tool occupies one contiguous block** | **70.55%** |
| Each operation *name* occupies one contiguous block | 75.19% |

And within the 29.45% that revisit a tool, most revisit only once: **85.3% of all
parts are within a single extra tool run** of perfectly blocked.

A hard cross-check validates the reading: `machining_summary.tool_changes` equals
`(tool blocks − 1)` for **10,000 of 10,000 parts** — no exceptions.

**Interpretation.** The plan is not sorted by any fixed key. It is
**tool-change minimisation subject to precedence constraints** from feature
interaction: NX batches everything a tool can do, and revisits a tool only when
geometry forces it (drilling that must follow a pocket, for instance). The
earlier chamfer/pocket/hole and Order-Group hypotheses were both shadows of this.

**Implication — this decomposes the easy tier.** The 20 points split into two
sub-scores that need very different things:

* **F1 (10 pts) is order-invariant.** It scores the *multiset* of operations. So
  half the easy tier requires no sequencing at all — only predicting which
  operations occur and how many times.
* **Levenshtein (10 pts)** then reduces to ordering a handful of tool blocks
  rather than sequencing up to 38 individual operations. Parts have a median of
  4 tool blocks.

That is a much smaller problem than "generate a sequence of up to 38 labels", and
it suggests a **set-prediction plus constrained-ordering** architecture rather
than free autoregressive generation.

**Slide potential.** Very high — three hypotheses tested and rejected/refined on
real data, ending in a structural insight that reshapes the model. This is the
data-science narrative of the project.

---

<a id="f-028"></a>
### F-028 — No augmentation or filtering used yet; what actually applies
**Status:** open (planning) · **All tiers**

**Finding.** As of this point **no data augmentation, resampling, or quality
filtering has been applied.** Work so far has been measurement infrastructure and
geometry validation. This is recorded explicitly because
Tutorial_Hackathon_Problem1.pdf p.9 requires that any filtering or augmentation
be reported clearly.

The one data-quality intervention made is **thickness-based denoising of IPW
differences** (F-022), which is a scoring-side correction rather than a training
filter — but it must still be disclosed.

**What applies, and why:**

*Augmentation — likely valid*
- **Prefix / state expansion.** Every prefix of a plan is a legitimate machining
  state, so next-operation prediction gets **91,702 (state, next-op) pairs**
  rather than 10,000 sequences. Largest single multiplier available, and free.
- **Cuboid symmetry.** The stock is a rectangular block, so 4 rotations about Z
  × 2 mirrors give up to **8× label-preserving transforms** — *provided* the
  sequence does not depend on absolute coordinates. F-027 suggests it does not
  (order tracks tools, not position), but this is **untested** and must be
  verified before use. → Q-010.

*Augmentation — invalid here*
- **Uniform scaling.** Changes feature sizes, which changes tool selection and
  therefore the labels. Not label-preserving. Rejected.

*Filtering*
- The organizers already filtered to >99% material removed and final IoU >0.999,
  so the corpus is clean by construction. Aggressive further filtering is
  unlikely to help and risks distribution shift against the test set.
- 187 parts have a single operation; 366 have one tool block. Worth flagging as
  degenerate for sequence training, not necessarily removing.

*Imbalance* (F-007)
- 53× between `DRILLING` (33.1%) and `BORING_REAMING` (0.6%). Class weighting or
  stratified batching, and **report per-class recall rather than accuracy** —
  the easy tier's F1 is sensitive to rare classes appearing in the right count.

*Leakage — the real risk*
- `.stl`, `.ptp` and `details.txt` are **training targets, not inputs**
  (Tutorial p.3). Only the BRep and the five images exist at inference. It would
  be very easy to build features from `operations.json` or `details.txt` and
  score brilliantly on a split that means nothing. Any feature extractor must be
  auditable against that boundary.

*Validation design*
- Parts were generated with sequential seeds (12345 + i), so a random split is
  sound, but should be **stratified by operation count and feature composition**
  given the long tail (1–38 operations).

---

<a id="f-029"></a>
### F-029 — The easy tier's real target is ~4.5 (label, count) pairs (resolves Q-010)
**Status:** confirmed · **Tier:** Easy (20 pts) · **Source:** `scripts/analyze_ordering_rule.py`, `scripts/analyze_label_runs.py`

**The question that started this.** Symmetry augmentation (up to 8×) is only
valid if rotating a part leaves its operation sequence unchanged. We cannot
re-run NX on a rotated part, so the proxy was: *what rule orders operations that
share a tool?* Axis-sorted ordering would break under rotation; nearest-neighbour
travel would survive it.

**First answer: no rule fits.** Over 438 same-tool blocks:

| Candidate rule | Match | Chance baseline (3-point block) |
|---|---:|---:|
| nearest-neighbour | 40.2% | ~50% |
| sorted by Y | 37.2% | ~33% |
| sorted by X | 30.1% | ~33% |

Every candidate sits **at or below chance**. Travel is also 18% longer than a
greedy tour, with 59% of blocks worse than greedy — so it is not path-optimised
either. Within-block order appears to follow the CAD feature-creation order,
which is not recoverable from geometry at inference time.

One real pattern did emerge: `featured_part_00015`'s five points lie on a circle
at ~72° intervals, drilled in angular order — a circular hole pattern machined
around its ring.

**Second answer: the question does not matter.** Levenshtein scores the sequence
of **(o1, o2) labels**, not which physical hole each operation targets. So
permuting operations *inside* a block only changes the score if the block carries
mixed labels. Measured over 1,745 multi-operation blocks:

- **97.65% are label-homogeneous.**
- The 2.35% that are mixed are almost always the same case: one endmill doing a
  pocket (`FLOOR_WALL`) and then a hole (`HOLE_MILLING`).

So within-block ordering is **irrelevant to the easy-tier score**, and the
unrecoverable feature-creation order costs us nothing.

**What the target actually is.** Collapsing consecutive identical labels:

| Quantity | Value |
|---|---:|
| Mean operations per part | 9.24 |
| Mean label *runs* per part | **4.46** |
| Median label runs | 4.0 |
| Compression (runs / operations) | 0.537 |

Run lengths: 46.0% are singletons, 24.7% are pairs, 15.1% are triples, with a
tail out to 8.

**Implication.** The easy tier is a much smaller problem than "generate up to 38
labels in order". The prediction target is roughly **4.5 (label, count) pairs**:

* **F1 (10 pts)** needs only the multiset — the counts, not the order (F-027).
* **Levenshtein (10 pts)** needs the run order plus the counts. Note the
  normalisation is still over the full sequence length, so counts matter to the
  distance even though ordering within a run does not.

That is a compact structured output, and it argues for predicting
`(label, multiplicity)` pairs directly rather than autoregressive token
generation.

**On augmentation (Q-010).** Rotation cannot break the label sequence by
reordering within homogeneous blocks. The residual risk is whether rotation
changes *block* order — but block order is driven by tool-change minimisation and
precedence (F-027), both rotation-invariant, and tool choice depends on feature
size, also rotation-invariant. So **symmetry augmentation is sound for easy-tier
labels**, with the honest caveat that block-order invariance is argued rather
than directly tested.

**Slide potential.** High, and it is a good scientific-method beat: the
hypothesis test failed, the failure was informative, and re-framing the question
dissolved it. "We spent an hour proving a question didn't matter" is a better
story than a lucky guess.

---

<a id="f-030"></a>
### F-030 — No CAD kernel needed: the STEP is planes and cylinders (resolves Q-005)
**Status:** confirmed · **All tiers** · **Source:** `scripts/analyze_step.py`, 40 parts

**Finding.** The BRep is the only real geometric input at inference, so reading
it is unavoidable; the question was whether that meant taking on OpenCascade
(`cadquery-ocp`, ~400 MB). Counting surface entities across a sample:

| Surface type | Share |
|---|---:|
| `PLANE` | 74.79% |
| `CYLINDRICAL_SURFACE` | 25.21% |
| everything else | **0%** |

No splines, cones or tori. Curves are `LINE` 78.2%, `CIRCLE` 20.9%, `ELLIPSE`
0.9% — the ellipses arising where a chamfer plane cuts a cylindrical hole. Files
average **25 KB**.

**Implication.** A targeted reader is enough, and preferable: no heavy
dependency, faster, and fully understood. `parsing/step.py` resolves the entity
reference graph and extracts faces with surface geometry and boundary vertices
in ~300 lines, with zero parse failures across 400 parts.

The assumption is load-bearing, so `StepModel.surface_type_census()` exists to
re-check it on the unreleased test set. If a spline surface ever appears, the
reader silently sees fewer faces rather than failing — that is the risk to watch.

**Slide potential.** Good engineering-judgement beat: "we measured before
reaching for the standard 400 MB answer."

---

<a id="f-031"></a>
### F-031 — Feature recognition reproduces the paper's published statistics
**Status:** confirmed · **All tiers** · **Source:** `scripts/validate_features.py`, 400 parts

**Finding.** Holes and corner blends are recognised from the BRep and validated
against corpus statistics in Dataset_Description.pdf that the recognizer never
sees:

| Metric | Ours | Paper |
|---|---:|---:|
| Holes per part (mean) | 2.283 | 2.330 |
| Hole diameter mean (mm) | 17.04 | 17.47 |
| Hole diameter min / max (mm) | 5.0 / 50.0 | 5.0 / 50.0 |
| **Blind share** | **0.502** | **0.502** |
| Block length / width / height (mm) | 346 / 341 / 98.6 | 350 / 351 / 100.1 |

Zero parse failures across 400 parts, and the holes-per-part distribution spans
0–6 exactly as published. The blind/through split agreeing to three decimals is
the strongest single confirmation.

**The discriminator that made it work.** Holes and pocket corner blends are
*both* cylindrical faces bounded by `CIRCLE` curves — a 90° fillet arc is a full
circle entity trimmed by its vertices, so the curve type distinguishes nothing.
The first attempt tested exactly that and over-detected holes **2.6×** (6.16 per
part). The correct signal is a **closed** boundary edge, whose start and end
vertex are the same instance: a hole wall wraps 360°, a fillet does not.

Separately, taking bounds over every `CARTESIAN_POINT` inflated block height from
~100 mm to ~136 mm, because placement origins are construction geometry sitting
outside the solid. Bounds now use vertex points only.

**Implication.** The front of the pipeline works, and it is the piece everything
else depended on: sequence, tool and IPW prediction all start from these
features. Combined with F-026's 29-name taxonomy, the feature→operation mapping
is now attackable from both ends.

**Caveat.** Pockets and chamfers are not yet recognised as such — only holes and
corner blends. Pocket type (corner / edge / center / slot) still needs the planar
face topology.

---

<a id="f-032"></a>
### F-032 — Hole diameter above the largest tool means the hole was milled
**Status:** confirmed · **Tiers:** Easy + Hard · **Source:** the 18% "unmatched" cases in F-031

**Finding.** Cross-checking every recognised hole against the tool diameters
actually used on its part, 81.9% match directly. The 18.1% that do not are
systematically the *same situation*:

| Part | Hole | Tools available |
|---|---:|---|
| `featured_part_00004` | D15.90, D14.70 | 10.0, 12.0, 20.0 |
| `featured_part_00007` | D16.30 ×3 | 10.0, 12.0, 20.0 |
| `featured_part_00008` | D30.50 | 20.0, 25.0 |

In every case the hole is **larger than any drill on the part**. These are
`HOLE_MILLING` operations: an endmill spiralling round a bore too large to drill,
exactly as Dataset_Description.pdf §2 describes ("a hole with a large diameter
might be machined with an endmill instead of a drill").

**Proposed rule (since REFUTED — see F-034):**

> ~~if a hole's diameter exceeds the largest available drill, it is bored by
> `HOLE_MILLING` with a smaller endmill; otherwise it is drilled.~~

> ### ⚠️ This finding was wrong. Corrected by F-034.
>
> It was inferred from **8 examples** in a validation listing. Tested properly
> against 1,120 position-matched holes, it fails outright: the largest drill in
> use is **50 mm**, while every milled hole is between **12.3 and 19.9 mm** —
> so **100% of milled holes lie inside the drillable range**. The 8 cases that
> suggested the rule were parts whose *own* tool set happened to be small; the
> rule generalised the part to the library.
>
> A second hypothesis — that milling is chosen when no drill of the exact size
> exists — also fails: **82.5%** of milled holes have a matching drill size
> available (158 distinct drill diameters are in use).
>
> **Kept rather than deleted**, because the reasoning error is the instructive
> part: a plausible mechanism, a small sample, and confirmation from cases
> selected *because* they were anomalies. See F-034 for what actually holds.

---

<a id="f-033"></a>
### F-033 — Only 14 operation chains cover every hole in the corpus
**Status:** confirmed, count later updated · **Tiers:** Easy + Hard · **Source:** `scripts/mine_hole_rules.py`, 500 parts

**Update.** This measurement used 1,120 holes from 500 parts. F-051 later
re-extracted the full corpus (22,491 holes, all 10,000 parts) and found a
**15th chain**, rare enough not to appear in the earlier sample. The shipped
classifier (F-047) is trained on 15 classes, confirmed against the model file
directly. The count below is left as originally measured, since it is the
evidence that motivated treating this as a small-label-set classification
problem in the first place; treat "14" as this sample's figure and "15" as the
corpus figure everywhere else in this document.

**Finding.** Drilling operations name their XY position in the `.ptp`, and
`features.py` recovers each hole's XY from the BRep. Matching them assigns
operations to *individual holes*, and it works: **1,120 of 1,136 holes matched
(98.6%)** and **2,567 of 2,589 hole operations (99.2%)**.

That yields, per hole, the exact ordered chain NX applied — and across 1,120
holes there are only **14 distinct chains**:

| Chain | Count | Share |
|---|---:|---:|
| `DRILLING` | 293 | 26.2% |
| `SPOT_DRILLING → DRILLING` | 281 | 25.1% |
| `SPOT_DRILLING → DRILLING → DEEP_HOLE_DRILLING → DRILLING` | 137 | 12.2% |
| `SPOT_DRILLING → DRILLING → DRILLING` | 114 | 10.2% |
| `HOLE_MILLING` | 90 | 8.0% |
| `SPOT_DRILLING → DRILLING → DEEP_HOLE_DRILLING → DRILLING → DRILLING` | 84 | 7.5% |
| `SPOT_DRILLING → DRILLING → HOLE_MILLING` | 50 | 4.5% |
| `HOLE_MILLING → BORING_REAMING` | 21 | 1.9% |
| `DRILLING → DRILLING` | 15 | 1.3% |
| 5 rarer chains | 36 | 3.2% |

**Implication.** This is the shape of the whole easy-tier prediction problem for
holes. Rather than generating a sequence, a model needs only to **classify each
recognised hole into one of 14 chains**, then concatenate. Combined with F-029
(the target is ~4.5 label runs) and F-027 (blocks are tool-grouped), the plan
assembles from per-feature classifications.

Position matching is also directly reusable at *submission* time: it is how a
predicted per-hole chain becomes an ordered part-level plan.

**Slide potential.** Very high. "1,120 holes, 14 chains" is the single most
compelling number for arguing this is rule recovery, not open-ended generation.

---

<a id="f-034"></a>
### F-034 — What decides drilling strategy, and what still does not
**Status:** partial · **Tiers:** Easy + Hard · **Source:** `scripts/mine_hole_rules.py`, 1,120 matched holes

**What holds.**

*Pecking follows slenderness.* `DEEP_HOLE_DRILLING` has the highest depth/diameter
ratio of any subtype — mean **6.27** against 4.45 for plain `DRILLING` — and never
appears below 12.1 mm diameter. Aspect ratio is the discriminator, as the physics
implies: deep narrow holes need chip evacuation.

*Multiple passes follow diameter.* Holes drilled in one pass average 16.6 mm;
2- and 3-pass holes start at **12.10 mm** minimum, and 4-pass holes at **19.30 mm**.
Large holes get a pilot drill then progressive enlargement.

| Passes | n | Diameter mean | Diameter min |
|---:|---:|---:|---:|
| 1 | 624 | 16.56 | 5.00 |
| 2 | 136 | 16.85 | 12.10 |
| 3 | 145 | 17.32 | 12.10 |
| 4 | 84 | 23.81 | 19.30 |

*Spot drilling is a tendency, not a rule.* Holes that get a `SPOT_DRILL` average
14.10 mm; those that don't average 22.03 mm. Through holes get one 72.9% of the
time, blind holes 52.7%. Suggestive, but far from deterministic on diameter and
depth type alone — something else is involved.

**What does not hold — `HOLE_MILLING`.** Two hypotheses tested and both refuted:

1. *Diameter exceeds the largest drill* (the F-032 claim). The largest drill in
   use is 50 mm; every milled hole is 12.3–19.9 mm. **100% lie inside the
   drillable range.**
2. *No drill of that exact size exists.* **82.5%** of milled holes have a
   matching drill among the 158 distinct drill diameters in use.

What is true is narrower and unexplained: milled holes occupy a **tight
12.3–19.9 mm band** with a **low aspect ratio** (mean 2.77 against 4.45 for
drilling) — shallow, mid-sized holes. The mechanism is still open. Plausible
remaining candidates, untested: the hole sits inside a pocket so its entry face
is not the top plane; it intersects another feature; or a flute-length constraint
applies. → **Q-013**.

**Implication.** Three of the five hole subtypes have workable predictors.
`HOLE_MILLING` is 3.8% of operations and `BORING_REAMING` 0.6%, so the residual
is small — but `SPOT_DRILLING` at 15.5% is only partly explained, and that one
matters.

**Slide potential.** Good, and honest: two named hypotheses refuted with numbers
is stronger evidence of rigor than a tidy rule asserted without a test.

---

<a id="f-035"></a>
### F-035 — First end-to-end submission: 21.97/100, all four formats valid
**Status:** confirmed · **All tiers** · **Source:** `scripts/run_baseline.py`, 12 parts

**Finding.** The pipeline runs end to end for the first time:
BRep → features → plan → IPW meshes + NC code → files → score.

| Tier | Score | Notes |
|---|---:|---|
| Easy | **10.00 / 20** | |
| Medium | **5.00 / 35** | see F-036 |
| Tools | **6.97 / 20** | |
| Tool paths | — / 25 | not scored yet; needs per-operation sweeps |
| **Total** | **21.97 / 100** | of 75 attempted |

**All four deliverables pass the official `validate_submission.py`** — easy JSON,
medium STL directory, hard tools JSON, hard PTP directory. 252 files across 12
parts in 8.2 s, zero failures. That was the main point: the format contract is
now proven by construction rather than by reading the validator.

**Where it already works.** Operation *count* is close — predicted 9.50 per part
against an actual 8.92. And composition beats ordering exactly as F-027 predicted:
F1 runs 0.93 / 0.88 / 0.93 on parts whose normalised Levenshtein is 0.52–0.85. We
pick roughly the right *bag* of operations and put them in the wrong *order*.

Simple parts already score full marks: `featured_part_00003` (1 operation) took
20/20 easy, 20/20 tools, 25/35 medium at IoU 0.9978.

**Where it fails.** Feature-heavy parts degrade badly — `featured_part_00008`
predicted 11 operations against an actual 5 (F1 0.25); `featured_part_00007`
predicted 13 against 8. The predictor over-generates on pocket-heavy parts,
most likely because every recognised floor patch becomes its own `FLOOR_WALL`
operation regardless of whether NX would batch them.

**Implication.** There is now a number to improve and a harness that measures it.
Ordering and pocket over-generation are the two clearest easy-tier targets;
F-036 is the medium-tier one.

---

<a id="f-036"></a>
### F-036 — Our generated IPWs score worse than submitting raw stock
**Status:** confirmed · **Tier:** Medium (35 pts) · **Source:** F-035 run vs. the F-003 baseline

**Finding.** F-003 measured that submitting the *unmachined* first IPW for every
operation scores mean IoU **0.970 → 15/35**. Our generated IPWs score mean IoU
**0.79 → 5/35**. On `featured_part_00001`: generated 0.8646 against the
do-nothing baseline's 0.970.

**We are actively worse than doing nothing.**

IPW error is two-sided, and we incur both kinds:

- **Over-cutting.** Pocket removal is approximated by the axis-aligned bounding
  box of each recognised floor patch. Real pockets have filleted corners and
  non-rectangular footprints, so the box removes material that should remain.
- **Under-cutting.** Chamfers are recognised but deliberately not cut, because
  resolving the wedge needs the block edge each chamfer sits on, which the
  recognizer does not yet supply.

Doing nothing incurs only the second kind — and since the block is only ~4.75%
machined (F-003), the null baseline sits near IoU 0.97 by construction.

**Implication — strategic, and it changes the plan.** For the medium tier an
*approximate* cut is worse than *no* cut until the approximation is tight. Given
the band table bottoms out at 0.90, the right sequencing is:

1. Take the null baseline as the floor — 15/35 for free.
2. Replace a feature's removal with a computed one **only when that removal is
   exact**, feature by feature. Holes are exact today (analytic cylinders);
   pockets and chamfers are not.

That is a per-feature opt-in rather than an all-or-nothing switch, and it makes
the score move monotonically upward as recognition improves instead of
oscillating.

**Caveat.** This leans on F-003's null-baseline figure, measured on a single
part. Re-measure across the corpus before trusting the 15/35.

**Slide potential.** Strong and counter-intuitive — "our first real attempt
scored below doing nothing, and understanding why told us how to sequence the
rest of the work."

> ### ⚠️ Superseded by F-037.
> The observation (cutting everything scored below cutting nothing) is real, but
> the *explanation* was wrong. It attributed the gap to over- and under-cutting
> geometry. Measuring all four cutting policies side by side shows they span just
> **5.00–5.83 points**, while sequence-length error swings IoU from 0.998 to
> 0.445. The geometry was never the dominant term. See F-037.

---

<a id="f-037"></a>
### F-037 — Medium IoU is a function of sequence length, not geometry
**Status:** confirmed · **Tiers:** Medium (35 pts) + Easy · **Source:** `scripts/compare_cut_policies.py`, 12 parts

**Finding.** Four IPW cutting policies were measured on identical parts:

| Policy | Mean points | Mean IoU | Parts ≥ 0.90 |
|---|---:|---:|---:|
| cut nothing (null) | 5.42 | 0.7796 | 4/12 |
| **holes only** | **5.83** | 0.7798 | 4/12 |
| holes + pockets | 5.00 | 0.7735 | 4/12 |
| everything | 5.00 | 0.7735 | 4/12 |

The entire policy space spans **0.83 points**. Cutting geometry barely matters.

What *does* matter is sequence length. Against the ratio of predicted to true
operation count:

| Part | Predicted / true | min/max | Measured IoU | Error |
|---|---:|---:|---:|---:|
| 00003 | 1 / 1 | 1.000 | 0.998 | −0.002 |
| 00006 | 3 / 3 | 1.000 | 0.982 | −0.018 |
| 00009 | 23 / 22 | 0.957 | 0.948 | −0.009 |
| 00012 | 13 / 12 | 0.923 | 0.914 | −0.009 |
| 00001 | 8 / 7 | 0.875 | 0.845 | −0.030 |
| 00005 | 8 / 10 | 0.800 | 0.794 | −0.006 |
| 00002 | 4 / 6 | 0.667 | 0.652 | −0.015 |
| 00004 | 6 / 10 | 0.600 | 0.600 | +0.000 |
| 00008 | 11 / 5 | 0.455 | 0.445 | −0.010 |

```
Medium IoU  ≈  min(n_predicted, n_truth) / max(n_predicted, n_truth)

Pearson r = 0.9990     mean |error| = 0.011     max |error| = 0.030
```

**Why this holds.** Consecutive IPWs are nearly identical — the whole plan removes
only ~4.75% of the block (F-003) — so any *aligned* operation scores IoU ≈ 1
almost regardless of what we cut. Unaligned operations (predicted-but-absent, or
true-but-missing) score 0 by the union-of-indices rule (Q-002). The mean is
therefore just the fraction of operations that line up.

The residual is consistently **negative and about 0.01** — and *that* is the real
geometry term. It is what separates 0.99 from 0.999, and it is the only thing
standing between 25/35 and 35/35 once length is correct.

**Implication — this reprioritises the whole project.**

1. **Medium and easy are the same problem.** Both are gated on predicting the
   right number of operations. Work on operation count pays into 55 points at
   once, not 20.
2. **Geometry work on the medium tier is premature.** Exact pocket removal,
   chamfer wedges, better fillets — all of it buys ~0.01 IoU while length error
   costs up to 0.55. Deferred until length is right.
3. **There is a sharp target.** IoU ≥ 0.90 needs a length ratio ≥ ~0.91; the top
   band needs exact length *plus* the geometry term. Our current mean ratio is
   ~0.78.
4. **F-036's prescription was right for the wrong reason.** "Holes only" does
   win, but by 0.4 points, not the 10 that were claimed.

**Caveat.** 12 parts, and the relationship is derived from a scoring rule we
chose (Q-002: unaligned operations score 0). Under a different mismatch
convention — truncation, or DTW alignment — the coefficient would change, though
the qualitative point would not.

**Slide potential.** The strongest analytical result in the project. One
scatter plot of length ratio against IoU with r = 0.999 makes the case that we
found the metric's actual driver instead of optimising the obvious thing.

---

<a id="f-038"></a>
### F-038 — Count errors traced per label: 21.97 → 28.07
**Status:** confirmed · **Tiers:** Easy + Medium · **Source:** `scripts/diagnose_counts.py`, 200 parts

**Finding.** Acting on F-037 (count is the objective), attributing the error per
`o2` label made the fix obvious. The initial diagnosis over 200 parts:

| Label | Predicted | True | Delta |
|---|---:|---:|---:|
| `DRILLING` | 769 | 580 | **+189** |
| `SPOT_DRILLING` | 249 | 279 | −30 |
| `BORING_REAMING` | 0 | 19 | −19 |
| `HOLE_MILLING` | 69 | 85 | −16 |
| `AREA_MILL` | 419 | 419 | **±0** |
| `FLOOR_WALL` | 362 | 352 | +10 |
| **Total** | 1,969 | 1,823 | **+146** |

`DRILLING` alone exceeded the entire net error. The cause: every hole above
12.1 mm was given a pilot plus a finish pass, yielding ~2.4 passes per hole
against a true mean of 1.69 (F-034) — and since the 1-, 2- and 3-pass diameter
means are nearly identical (16.6 / 16.9 / 17.3 mm), diameter never justified it.

Three changes followed, each measured:

| Change | Effect |
|---|---|
| Pilot pass only above 19.3 mm (was 12.1) | `DRILLING` +189 → −20 |
| Spot-drill threshold 18 → 20 mm | `SPOT_DRILLING` −30 → +4 |
| Add `BORING_REAMING` above 18 mm (13.5 first, over-generated 3×) | −19 → −6 |

Net count error fell from **+146 to −16** (0.9% of 1,823). `AREA_MILL` was
exactly right throughout — one operation per recognised slanted face, 419 of 419.

**The lesson that cost the most time.** Aggregate accuracy is not per-part
accuracy. After the fixes the totals matched almost exactly, yet the mean length
ratio moved only 0.8202 → 0.8222, because per-part errors of opposite sign
cancel in the aggregate. Since F-037 scores each part independently, the
distribution is what matters, not the mean. Per-part diagnosis (F-039) is what
finally moved it.

**Score progression this session:** 21.97 → 24.27 → **28.07** / 100.

---

<a id="f-039"></a>
### F-039 — Large bores are milled; the F-034 band missed the top end
**Status:** confirmed · **Tiers:** Easy + Medium · **Source:** per-part inspection of `featured_part_00008`

**Finding.** With aggregate counts correct but per-part still wrong, inspecting
the worst part was decisive. `featured_part_00008` predicted 11 operations
against a true 5:

```
recognised: 3 holes D30.50 through, aspect 3.7; 2 chamfer faces
PRED : DRILLING x9, AREA_MILL x2
TRUTH: HOLE_MILLING x3, AREA_MILL x2
       names: AREA_MILL, AREA_MILL_1, MILL_THROUGH_HOLE_FROM_SOLID_MATERIAL x3
```

NX **mills** all three 30.5 mm bores. Our rule drilled each in three passes.

F-034's milling band (12.3–19.9 mm) came only from position-matched holes and
missed the large end entirely — a sampling artefact, not a property of the data.
This partially rehabilitates the intuition behind the refuted F-032: large holes
*are* milled. What F-032 got wrong was the threshold (the largest *drill*, 50 mm)
and the mechanism.

**Two attempts, both measured.** Relaxing the aspect limit to 4.0 across the
whole diameter range raised the length ratio (0.822 → 0.838) but wrecked the
labels — `HOLE_MILLING` +85, `DRILLING` −231 — because it swept in ordinary
drilled holes. Treating the large end as its own case
(`diameter ≥ 26 mm ⟹ milled`, aspect ignored) kept the labels sane and still
fixed the part.

**Result on the affected parts.** `featured_part_00008` went from 11/5 operations
(easy 0/20, IoU 0.446) to **5/5** (easy 20/20, IoU 0.9812, medium 20/35).
`featured_part_00001` went 8/7 → **7/7**, IoU 0.9659, medium 15/35.

**Implication.** Two disjoint milling regimes exist — a mid-band with low aspect,
and large bores regardless — and neither mechanism is understood (Q-013). The
current rule reproduces the behaviour without explaining it, which is worth
stating plainly in the write-up rather than dressing up as a derived law.

---

<a id="f-040"></a>
### F-040 — Blind-hole bottoms were being counted as pockets
**Status:** confirmed (fixed) · **Tiers:** Easy + Medium · **Source:** `scripts/diagnose_pockets.py`, 150 parts

**Finding.** `FLOOR_WALL` had a net error of only +0.05 per part yet was **wrong
on 58% of parts** — over-counting as often as it under-counted, so the bias
vanished from every aggregate statistic while the per-part damage stayed.

Splitting the error by sign exposed the cause immediately. Recognised floors on
`featured_part_00019`:

```
z=65.4  5x0   z=66.2  5x0   z=90.8  5x0     vs truth: 0 pockets
```

Footprints of `5x0`, `8x0`, `4x0`, `2x0` — degenerate. A **blind hole ends in a
flat circular face lying strictly between the stock bottom and top**, which is
exactly the test used for a pocket floor. Every blind hole was being counted as a
pocket.

**Fix.** Two conservative filters: reject floors with either footprint side below
2 mm (a real pocket spans 204–42,349 mm²), and reject any floor whose footprint
sits inside a recognised hole's circle.

| Metric | Before | After |
|---|---:|---:|
| Parts with exact `FLOOR_WALL` count | 44.0% | **68.0%** |
| `FLOOR_WALL` absolute error per part | 0.880 | **0.515** |
| Parts with wrong `FLOOR_WALL` | 115/150 | **69/150** |
| Over-counting cases | 47 parts | **0** |
| Total absolute count error per part | 3.505 | 2.885 |
| Mean length ratio | 0.822 | **0.853** |

**The methodological point.** This is the second time aggregate statistics hid a
real defect (see F-038). Net error is a *sum of signed* mistakes; the score is a
*sum of absolute* ones. Measuring `|error|` per part rather than the net is what
made a 58% failure rate visible at all — and it took a purpose-built diagnostic,
not the existing one, to see it.

**Slide potential.** Strong. The `5x0` footprint against "truth: 0 pockets" is a
vivid one-line illustration of why aggregate validation is not enough.

---

<a id="f-041"></a>
### F-041 — Some pockets take two operations, and geometry does not say which
**Status:** open · **Tier:** Easy + Medium · **Source:** `scripts/diagnose_pockets.py`

**Finding.** After F-040 removed all over-counting, the residual is **purely
under-counting**: 20.7% of parts need one more `FLOOR_WALL` than they have
recognised floors, 7.3% need two more, 4.0% need three. Recognised floors run
1.220 per part against 1.693 true operations — a ratio of **1.39**.

Two candidate predictors were tested and neither separates the groups:

| Group | n | Depth fraction (mean) | Footprint (mean) |
|---|---:|---:|---:|
| Needs more operations | 85 | 0.263 | 13,931 mm² |
| One operation is right | 98 | 0.289 | 15,325 mm² |

Essentially identical on both axes — if anything the pockets needing *more* work
are slightly *shallower* and *smaller*, the opposite of the intuition.

**Remaining hypotheses, untested.** The most plausible is a corner-radius
constraint: an interior corner of radius `r` admits only an endmill of diameter
≤ 2r (Dataset_Description.pdf §6.2), so a large pocket with tight corners may be
roughed with one tool and cleaned with a smaller one — two operations. The corner
blends are already recognised (`PartFeatures.blends`), so this is directly
testable. Nesting (13.2% of pockets) is a second candidate.

**Deliberately not fitted.** Since no predictor separates the groups, adding an
extra operation to an arbitrary 39% of pockets would match the marginal count
while leaving per-part absolute error unchanged or worse — and F-037 scores per
part. Guessing here would inflate an aggregate statistic without earning a point.

---

<a id="f-042"></a>
### F-042 — All 100 points measured at last: tool paths are ~2% of theirs
**Status:** confirmed · **Tier:** Hard (path, 25 pts) · **Source:** `scripts/run_baseline.py` with sweep scoring wired in

**Finding.** Tool-path scoring is now inside the baseline loop: each emitted
`.ptp` is parsed back, swept with its declared tool, clipped to the stock present,
and compared against the denoised IPW difference — the same route the rubric
takes. Round-tripping our own output also proves it is parseable.

First full measurement (8 parts):

| Tier | Score | % of tier |
|---|---:|---:|
| Easy | 14.50 / 20 | 73% |
| Medium | 12.50 / 35 | 36% |
| Tools | 10.77 / 20 | 54% |
| **Tool paths** | **0.47 / 25** | **2%** |
| **Total** | **38.24 / 100** | |

**The tool paths are not working.** For context, F-021 measured the *same sweep
engine* at ≈23.5/25 when fed ground-truth operations, tools and paths. The engine
is fine; the paths we generate are not.

**Three variants tried, all equivalent to zero:**

| Chamfer path variant | Paths score |
|---|---:|
| Path collapsed to the origin (an actual bug) | 1.72 |
| Tool run along the edge at chamfer mid-height | 1.25 |
| Positioning move only, no cut | 0.47 |

The spread is noise on 8 parts, and every variant is ~2–7% of the tier. Notably
the *buggy* version scored highest, which is a warning rather than a result: the
principled version was kept, because retaining a bug that wins by 1.2 points on 8
parts is how a submission stops generalising.

**Why the generator is inadequate**, in order of cost:

1. **Pockets get a single perimeter pass.** That sweeps a thin ring at final
   depth, not the pocket volume — a near-total undercut on 20.2% of operations.
   Real area clearing (stepped-down zigzag or spiral passes) is the fix and is
   substantial work.
2. **Chamfers have no correct path.** A 45° chamfer mill is 20 mm across, so
   placing its tip on the edge line buries the body in the block and overcuts
   badly. A correct path must offset the tool so its conical flank lies *on* the
   chamfer surface, which needs to know which side of the strip is the block
   edge — topology not yet resolved.
3. **Drilling is probably close** (canned cycles at the right XY and depth) but
   its contribution is diluted by the two above.

**Implication.** The tool-path tier is the largest single block of unclaimed
points (24.5 of 25) and the geometry to claim it already exists and is validated.
This is now the highest-value work on the board, ahead of further count tuning —
but it is *generation* work, not tuning, and should be scoped as such.

**Slide potential.** Good honesty beat, and the F-021 contrast is the point: the
engine scores 23.5/25 on real paths and 0.5/25 on ours, which locates the problem
precisely.

---

<a id="f-043"></a>
### F-043 — Pecked holes carry drilling on both sides of the peck
**Status:** confirmed · **Tiers:** Easy + Medium · **Source:** F-033 chains, verified by measurement

**Finding.** `DRILLING` was under-generated by 0.610 per part. Re-reading the
F-033 chains showed why: every chain containing `DEEP_HOLE_DRILLING` brackets it
with drilling passes on *both* sides —

```
SPOT -> DRILL -> DEEP_HOLE -> DRILL              12.2% of holes
SPOT -> DRILL -> DEEP_HOLE -> DRILL -> DRILL      7.5% of holes
```

— and we emitted only the trailing one, because the leading pass was gated on
diameter ≥ 19.3 mm while most pecked holes are narrower (that is what makes them
slender enough to peck).

Making a pilot pass unconditional for pecked holes:

| Metric | Before | After |
|---|---:|---:|
| `DRILLING` net error per part | −0.610 | **−0.140** |
| `DRILLING` absolute error per part | 1.170 | **0.840** |
| Parts with wrong `DRILLING` | 115/200 | **88/200** |
| Mean length ratio | 0.8525 | **0.8707** |
| Medium score (12 parts) | 9.17 | **12.50** / 35 |

**Implication.** The chain table in F-033 is a *specification*, not a summary —
reading each chain literally as a template is more reliable than deriving
per-operation rules from marginal statistics.

---

<a id="f-044"></a>
### F-044 — Why medium cannot reach 80% by counting alone
**Status:** confirmed · **Tier:** Medium (35 pts) · **Source:** score decomposition across the session

**Finding.** Medium is now 12.50/35 (36%). Reaching 80% means 28/35, which given
the band table requires most parts to score 25–35, i.e. **mean IoU ≥ 0.99**.

Decomposing what stands in the way, measured on the 12-part set:

| Part | Predicted / true ops | IoU | Points |
|---|---:|---:|---:|
| 00003 | 1 / 1 | 0.9978 | 25 |
| 00005 | 10 / 10 | 0.9914 | 25 |
| 00006 | 3 / 3 | 0.9825 | 20 |
| 00008 | 5 / 5 | 0.9812 | 20 |
| 00011 | 15 / 15 | 0.9805 | 20 |
| 00007 | 8 / 8 | 0.9803 | 20 |
| 00012 | 11 / 12 | 0.9121 | 10 |
| 00010 | 9 / 8 | 0.8841 | **0** |
| 00001 | 8 / 7 | 0.8453 | **0** |
| 00002 | 4 / 6 | 0.6525 | **0** |
| 00004 | 6 / 10 | 0.5995 | **0** |

**Two separate ceilings, and counting only lifts the first.**

1. **Count accuracy** decides whether a part scores *anything*. The four parts at
   zero are all length mismatches. Fixing every count would move them to ~20 —
   worth roughly +7 points of the tier average.
2. **Geometry accuracy** then caps how much. Six parts already have *exact*
   counts and still sit at **0.980–0.982**, which is band 0.98–0.99 = 20 points,
   not 25 or 35. Perfect counting everywhere would therefore land near
   **20/35 (57%)**, not 80%.

The residual ~0.018 is the material we do not cut: chamfers (skipped entirely,
21.9% of operations) and pockets (cutting them measured *worse* than not, because
the recognised footprint over-cuts — 11.25 against 12.50 of 35, and rounding the
corners with the recognised blend radii changed it by 0.0001).

**Implication — 80% on medium requires exact removal geometry, not tuning.**
Specifically: chamfer wedges resolved against the block edge they sit on, and
pocket footprints recovered as true outlines rather than bounding boxes. Both are
topology work on the STEP reader, and both are prerequisites, not refinements.
Stating the ceiling explicitly is more useful than iterating against it.

**Slide potential.** Good — a clean decomposition of a score into "what gates it"
versus "what caps it" is exactly the analysis a methods section wants.

---

<a id="f-045"></a>
### F-045 — Chamfer removal is an exact half-space cut, not a wedge
**Status:** confirmed · **Tier:** Medium · **Source:** `machineplan.generate._chamfer_solid`

**Finding.** Chamfers had been skipped entirely (F-042) because reconstructing the
wedge appeared to need the block edge each chamfer sits on — topology the reader
does not resolve. That framing was wrong.

**A chamfer face is a plane, and the material it removes is exactly the stock
lying on that plane's outward side.** No edge, no wedge construction: slicing the
stock by the plane gives the removal solid outright. Two details make it robust:

- Anchor the plane on a **vertex of the face**, not the STEP placement origin,
  which for a plane may sit anywhere on the surface including outside the solid.
- Resolve orientation **by measurement** — a STEP face normal may point either
  way, so cut both sides and keep the smaller. A chamfer is 2–30 mm on a
  200–500 mm block, so the larger piece is always the part being kept.

**Effect.** Cutting chamfers moved the best policy from "holes only" to
"everything", measured over 30 parts:

| Policy | Points (30 parts) |
|---|---:|
| nothing (null) | 11.67 |
| holes only | 12.17 |
| holes + pockets | 12.17 |
| holes + chamfers | 12.67 |
| **everything** | **13.17** |

Medium on the 12-part set went 12.50 → **13.33 / 35**.

**Implication.** Pockets remain the weak link — they still cost points in
isolation. The same reframing may apply: a pocket's walls and floor are planes
too, so its removal might be an intersection of half-spaces rather than an
extruded outline. Untested.

---

<a id="f-046"></a>
### F-046 — Three rules matched the marginal and lost points
**Status:** confirmed · **Method** · **Source:** three measured experiments this session

**Finding.** Three plausible rules were implemented, measured, and reverted. All
three improved an *aggregate* statistic while making the *score* worse:

| Rule | Aggregate effect | Score effect |
|---|---|---|
| Split wide-cornered pockets into two operations | `FLOOR_WALL` net error −0.515 → **−0.015** | parts wrong 69 → **86**; ratio 0.8707 → 0.8649 |
| `SPOT → DRILL → HOLE_MILLING` for all mid-band bores | closes a known 4.5% chain | medium 13.33 → **12.08**; ratio 0.8707 → 0.8557 |
| Chamfer path along the edge at mid-height | plausible tool motion | paths 1.72 → **1.25** (overcut) |

The pattern is identical each time. A signal that is real but weak — pockets
needing a second operation measure size/2r 4.58 against 3.91; 36% of milled bores
take the drill prefix — is applied to *every* member of the group. It fixes the
population mean and breaks individual parts, and F-037 scores parts individually.

**The rule this yields:** a predictor is only worth adopting if it separates the
two groups, not if it merely reproduces their ratio. Where no separator exists,
emitting the majority chain unprefixed beats splitting on a coin-flip.

Each reverted rule is documented **in the code at the point of decision**, with
its measurement, so the next person does not re-derive and re-try it.

**Slide potential.** High for the Round 2 rigor section — three named hypotheses,
each measured and rejected on evidence, is the strongest available demonstration
that the tuning was disciplined rather than opportunistic.

---

<a id="f-047"></a>
### F-047 — A learned chain classifier beats hand-tuning, 0.948 against 0.391
**Status:** confirmed · **Tiers:** Easy + Medium + Tools · **Source:** `scripts/train_hole_classifier.py`

**Finding.** F-046 recorded three hand-built rules that each matched a marginal
and lost points, because no threshold I could find separated the groups. The
boundaries exist; hand-tuning simply could not locate them. A gradient-boosted
classifier over the same geometry finds them.

Trained on 4,228 holes from 1,531 parts, evaluated on **1,382 holes from 511
parts never seen in training** (split by *part*, since holes on one part share a
block, feature mix and tool set):

| Predictor | Chain accuracy | Mean \|count error\| per hole |
|---|---:|---:|
| Majority class | 0.261 | — |
| Hand-written rules | 0.391 | 0.635 |
| **Gradient boosting** | **0.948** | **0.082** |

A **7.7× reduction in operation-count error**, which is exactly the quantity
F-037 showed drives the medium tier.

**Where the rules were blind.** Per-chain recall on held-out holes:

| Chain | n | Rules | Model |
|---|---:|---:|---:|
| `DRILLING` | 361 | **0.000** | 0.934 |
| `SPOT_DRILLING\|DRILLING` | 335 | 0.997 | 0.982 |
| `SPOT\|DRILL\|DEEP_HOLE\|DRILL` | 191 | 0.770 | 0.990 |
| `SPOT\|DRILL\|DRILL` | 144 | 0.097 | 0.910 |
| `HOLE_MILLING` | 101 | 0.228 | 0.980 |
| `SPOT\|DRILL\|HOLE_MILLING` | 48 | **0.000** | 0.979 |
| `HOLE_MILLING\|BORING_REAMING` | 21 | **0.000** | 1.000 |

The rules scored **zero** on the single most common chain — plain `DRILLING`,
361 holes — because they always prepend a spot drill below 20 mm. They also
scored zero on the two chains that Q-013 and F-046 had failed to characterise.

**End-to-end, on parts never used for training** (3000–3020):

| Tier | Rules | Classifier |
|---|---:|---:|
| Easy | 11.10 | **12.70** |
| Medium | 9.25 | **10.75** |
| Tools | 7.49 | **7.77** |
| **Total** | **27.91** | **31.22** |

**Honesty note on the numbers.** Scoring parts 1–12 gives 36.85, but those parts
are inside the training set. The held-out figure of 31.22 is the one to quote,
and the gap between them (≈5.6 points) is a fair estimate of how optimistic
in-sample evaluation is here. `run_baseline.py --offset` exists to make the
held-out run the easy one to reproduce.

**What the model does not do.** It predicts *which* operations occur, not what
they cut with; tool sizes still come from geometry (the final drilling pass opens
the hole to its finished diameter, earlier passes are pilots). And it covers only
holes — pockets and chamfers remain rule-based, which is where the residual count
error now lives.

**Method note.** The rule path is kept as a fallback, so the pipeline runs from a
clean checkout with no model artifact. Feature extraction lives in the model
module and is imported by the dataset builder, so training and inference cannot
drift apart.

**Slide potential.** The strongest result in the project. Three hand-built rules
failed, the failure was diagnosed as "the separator exists but is not
hand-findable", and a classifier on the same features recovered it — with the
held-out comparison to prove it.

---

<a id="f-048"></a>
### F-048 — The same model fails on pockets, and the failure locates the real problem
**Status:** confirmed · **Tier:** Easy + Medium · **Source:** `scripts/train_pocket_classifier.py`

**Finding.** F-047 worked so well on holes that the obvious move was to repeat it
for pockets, where F-041 had left counting unsolved. It does not work, and the
way it fails is more useful than a marginal win would have been.

Trained on 2,343 floors, tested on 786 from held-out parts:

| Predictor | Accuracy | Mean \|count error\| |
|---|---:|---:|
| **"always 1" (current rule)** | **0.865** | **0.178** |
| Gradient boosting | 0.859 | 0.181 |

The model is *worse* than the trivial rule, and its recall on the cases that
matter is near zero: **0.091 on 2-operation floors, 0.000 on 3- and
4-operation floors.** The guard in the training script refused to save it.

**Why this differs from holes.** For holes, F-046's diagnosis was "the separator
exists but is not hand-findable" — and a classifier found it immediately. For
pockets the diagnosis is different: **the information is not in the recognised
geometry at all.** Twelve features (footprint, depth, corner radius, reach ratio,
boundary contacts, nesting, aspect) carry no signal about whether NX splits a
pocket into two operations.

**Where the pocket error actually lives.** Attributing operations to floors by
depth and overlap:

| | Share |
|---|---:|
| Recognised floors taking exactly 1 operation | 86.9% |
| Recognised floors taking 2+ | 13.1% |
| **`FLOOR_WALL` operations matching *no* recognised floor** | **22.5%** |

So the under-counting splits roughly 45/55 between mis-counting pockets we find
and **never finding the pocket at all**. The second is the larger half, and it is
a *recognition* problem that no counting model can reach.

**And it is not a merging artefact.** The obvious suspect was that
bounding-box-contact merging was fusing distinct pockets. Tightening the merge to
require 30% area overlap measured **exactly neutral** — 1.220 floors per part and
68.0% exact counts, unchanged. Those pockets' floor faces are never detected in
the first place.

**Implication.** Further pocket work belongs in `features.py`, not in a model:
find the horizontal faces currently being missed. Until then "one operation per
recognised floor" is the right rule, and it is now backed by a measurement rather
than by not having tried anything else.

**Slide potential.** Strong, precisely because it is a negative result with a
diagnosis attached. "We applied the same method that had just worked, it failed,
and the failure told us the problem was upstream" is a better methods story than
a second success would have been.

---

<a id="f-049"></a>
### F-049 — ⚠️ An unstated rubric assumption is worth 26% of the medium tier
**Status:** confirmed · **Tier:** Medium (35 pts) · **Source:** `scripts/sensitivity_alignment.py`

**Finding.** The rubric says medium IoU is "averaged across all operations" but
never defines what happens when the predicted sequence has a different length
from the truth (**Q-002**). Our scorer assumed the strict reading: score over the
union of indices, so an unmatched operation contributes IoU 0.

That assumption turns out to be enormous. Scoring the same 40 held-out parts
under both readings:

| Convention | Mean points | Mean IoU | Parts ≥ 0.90 |
|---|---:|---:|---:|
| **union** (our assumption) | **13.25** / 35 | 0.8735 | 23/40 |
| **truncate** to the shorter | **22.25** / 35 | 0.9821 | **39/40** |

**A 9-point swing — 26% of the tier — from a convention the rubric does not
state.** Half the parts (20 of 40) have a length mismatch, so it applies broadly.

**And it invalidates the reasoning, not just the number.** The correlation between
operation-count ratio and IoU:

| Convention | r |
|---|---:|
| union | **+0.9918** |
| truncate | **+0.1142** |

F-037 concluded "medium IoU *is* the count ratio, so counting is the objective",
and that conclusion drove priorities for hours. It is **true only under our
assumed convention**. Under truncation, count barely matters and the tier becomes
geometry-driven — the opposite prescription.

**Implication.** This is now the highest-value open item in the project, ahead of
any tuning:

- If the graders **truncate**, our medium score is understated by ~9 points and
  effort should move from counting to removal geometry.
- If they use the **union**, current priorities are right.
- A third reading (DTW alignment, or scoring only the final IPW against the BRep)
  would give yet another answer.

**Action: ask the organizers.** No amount of local work resolves it, and the
answer changes what to build next. Until then the scorer supports both via
`score_medium(..., alignment=...)` and defaults to the pessimistic one, so we are
never flattering ourselves.

**Slide potential.** Very high, and unusually creditable: identifying that your
own headline metric rests on an unstated assumption, quantifying the exposure,
and reporting the pessimistic figure is exactly the scientific rigor Round 2
grades.

---

<a id="f-050"></a>
### F-050 — Most tuning decisions were made inside the noise floor
**Status:** confirmed · **Method** · **Source:** `scripts/evaluate.py`, 150 held-out parts

**Finding.** Until now every configuration choice was a point estimate on 8–30
parts with no error bar. Measuring properly on **150 held-out parts** with a
bootstrap interval:

| Tier | Mean | 95% CI | sd |
|---|---:|---|---:|
| Easy | 13.24 | [12.40, 14.07] | 5.11 |
| Medium | 12.97 | [10.83, 15.17] | 13.34 |
| Tools | 6.49 | [5.53, 7.47] | 6.06 |
| **Total** | **32.70** | **[29.32, 36.17]** | 21.28 |

Medium carries a **±2.2 point** interval on 150 parts. Several decisions were
made on far less:

| Decision | Evidence at the time | Verdict now |
|---|---|---|
| Cut policy "everything" over "holes+chamfers" | 13.17 vs 12.67 on 30 parts | **unresolvable noise** |
| Rounded pocket corners | IoU 0.8856 → 0.8857 | unresolvable |
| Stricter floor merging | exactly neutral | correctly called |
| Boring threshold 13.5 → 18.0 | large per-label deltas on 200 parts | sound |

**What survives.** The classifier gain does, decisively. A *paired* comparison on
the same 150 parts — which removes between-part variance, the dominant term —
gives:

| Tier | Rules | Classifier | Diff | 95% CI |
|---|---:|---:|---:|---|
| Easy | 10.59 | 13.24 | +2.65 | [+1.95, +3.40] |
| Medium | 8.37 | 12.97 | +4.60 | [+2.60, +6.67] |
| Tools | 5.60 | 6.49 | +0.89 | [+0.42, +1.42] |
| **Total** | **24.56** | **32.70** | **+8.14** | **[+5.34, +11.06]** |

Every interval excludes zero. The earlier 20-part estimate of +3.31 *understated*
the gain by more than half, because unpaired comparison on few parts is dominated
by which parts happen to be easy.

**Implication.** Pairing plus bootstrap is now the standard for any configuration
choice, and small-sample point estimates are not evidence. The threshold
constants tuned on parts 1–200 should be re-tuned against a proper validation
split, since they are still fitted to data inside the training range.

---

<a id="f-051"></a>
### F-051 — Only 20% of the corpus was being used
**Status:** confirmed · **Method** · **Source:** audit prompted by "did we use the whole 5 GB?"

**Finding.** An audit of what the 5.2 GB dataset had actually contributed:

| Use | Parts | Share |
|---|---:|---:|
| Corpus statistics (F-026, F-027) | 10,000 | 100% |
| **Hole-chain classifier training** | **2,042** | **20%** |
| Pocket dataset | 2,500 | 25% |
| Feature-recognition validation | 400 | 4% |
| Count diagnostics | 200 | 2% |
| End-to-end evaluation | 150 | 1.5% |
| Swept-volume validation | ~18 operations | ~0.02% |

The classifier — the single strongest component — had seen **5,610 of roughly
23,322 holes**. And of five available modalities, the **50,000 PNG renders have
never been read at all**, despite being available at inference.

**Effect of using the full corpus.** Re-extracting all 10,000 parts gives 22,500
holes, 4× the previous training data:

| Training set | Holes | Chain accuracy (held out) |
|---|---:|---:|
| 2,042 parts | 5,610 | 0.948 |
| **All parts** | **22,491** | **0.970** |

**A split fix came with it.** The previous evaluation used parts 3000+ against a
model trained on a *random* part split of the first 2,500 — fine at the time, but
once training covers all 10,000 parts a random split leaves no range that is
provably unseen. The split is now deterministic on the part number: everything
below 8,000 trains, everything at or above is never touched, so
`run_baseline.py --offset 8000` and `evaluate.py --offset 8000` are honest by
construction rather than by argument.

**Definitive figure on 150 provably-unseen parts (8000+):**

| Tier | Mean | 95% CI |
|---|---:|---|
| Easy | 13.79 | [13.08, 14.51] |
| Medium | 12.20 | [10.20, 14.27] |
| Tools | 6.99 | [6.02, 8.00] |
| **Total (of 75)** | **32.98** | **[29.88, 36.23]** |

Mean length ratio **0.9146**, up from 0.8418 under the rules.

**Data filtering, disclosed per Tutorial p.9.** Nine holes (0.04%) in three
chains occurring fewer than five times were dropped from *both* halves — they
cannot be learned or fairly evaluated, and a single-member class breaks the
booster's internal stratified split. Dropping them from training only would have
flattered the reported accuracy.

**Still unused.** The 50,000 images, and the prefix/state augmentation
(91,702 (state, next-op) pairs) and symmetry augmentation (up to 8×) identified
in F-028. All three remain free upside.

---

<a id="f-052"></a>
### F-052 — Tool type is already perfect; the entire tool loss is diameter
**Status:** confirmed · **Tier:** Hard tools (20 pts) · **Source:** `scripts/diagnose_tools.py`, 400 held-out parts

**Finding.** The tools tier had never been analysed. Decomposing it over 3,740
operation slots:

- **Tool *type* is correct on 1,698 of 1,698 aligned slots — 100%.** Zero
  confusion of any kind. Since the rubric zeroes an operation outright on a type
  mismatch, that half of the tier is solved.
- **54.6% of slots are *misaligned*** — our operation *k* is a different kind of
  operation from truth's *k*. Those score zero however good the tool is, so they
  are a sequence problem wearing a tool problem's clothing. Perfect tool choice
  at current alignment caps the tier at **9.08 / 20**.
- The remaining loss is **diameter, on exactly two tool types**:

| Tool | Rel. error | Points/10 | Our dia | True dia |
|---|---:|---:|---:|---:|
| `chamfer_mill` | 0.000 | **10.00** | 20.00 | 20.00 |
| `spot_drill` | 0.000 | **10.00** | 12.00 | 12.00 |
| `twist_drill` | **0.598** | 4.27 | 16.85 | 14.11 |
| `end_mill` | **0.444** | 3.14 | 16.61 | 16.19 |

A 0.598 relative error is mis-assignment, not noise. Measuring the real ratio of
tool diameter to finished hole diameter over 1,200 parts gave a very regular
table (medians, `scripts/mine_tool_diameters.py`):

| Subtype | pos/of | n | median | sd |
|---|---|---:|---:|---:|
| `DRILLING` | 1/1 | 1,507 | 1.000 | 0.070 |
| `DRILLING` | 1/2 | 696 | 0.583 | 0.116 |
| `DRILLING` | 2/2 | 696 | 1.000 | 0.013 |
| `DRILLING` | 1/3 | 207 | 0.263 | 0.065 |
| `DRILLING` | 2/3 | 207 | 0.628 | 0.041 |
| `DRILLING` | 3/3 | 207 | **1.000** | **0.000** |
| `DEEP_HOLE_DRILLING` | 1/1 | 559 | **0.383** | 0.197 |
| `HOLE_MILLING` | 1/1 | 371 | **0.779** | 0.106 |
| `BORING_REAMING` | 1/1 | 65 | 0.993 | 0.004 |

**Two hand-guessed values were badly wrong.** `DEEP_HOLE_DRILLING` is a *small
pilot* drill — mean 8.18 mm across only 12 distinct sizes — and we were assigning
the finished hole diameter, a 2.6× over-estimate on 559 operations. `HOLE_MILLING`
uses 0.78 of the bore, not the 0.6 that was guessed.

Adopting the measured ratios took `twist_drill` from 0.598 → **0.438** error and
4.27 → **4.85** points. `end_mill` barely moved, because most `end_mill` slots are
pocket `FLOOR_WALL` rather than hole milling, and pocket endmill sizing is still a
crude 20/12/6 heuristic — the next thing to mine.

Also worth noting: the final drilling pass is *exactly* the finished diameter,
sd **0.000**. That is the one value in the whole project that needs no tolerance.

---

<a id="f-053"></a>
### F-053 — Our fixed block order was correct on 26.5% of parts
**Status:** confirmed · **All tiers** · **Source:** `scripts/mine_block_order.py`, all 10,000 parts

**Finding.** F-027 established that a plan is a sequence of contiguous tool blocks
whose order varies. The planner emitted a fixed chamfer → pocket → hole order.
Measured across every part:

| Order | Parts | Share |
|---|---:|---:|
| **HCP** (hole → chamfer → pocket) | 3,406 | **34.1%** |
| **CPH** (ours) | 2,647 | 26.5% |
| CP | 1,200 | 12.0% |
| HP | 623 | 6.2% |
| CH | 555 | 5.5% |
| HC | 526 | 5.3% |
| PH | 454 | 4.5% |
| single family | 589 | 5.9% |

**We were using the second-most-common order.** Simply switching the default to
`HCP` would have been better; but the order is also **highly predictable from
part geometry — 0.896 accuracy on held-out parts against 0.349 for always
guessing the modal order.**

**Why this matters beyond the easy tier.** A misordered block makes our operation
*k* a different kind of operation from truth's *k*, which zeroes that slot in the
**medium, tools and tool-path tiers as well** — F-052 measured only 45.4% of slots
aligned. Ordering is the single cross-cutting constraint in the project.

**Measured effect, and a mistake worth recording.** The first measurement showed
+2.09 [−1.42, +5.67] on 150 parts, not significant — and it was also *not
measuring what I thought*. The save step had been added to the mining script but
the script never re-run, so no model file existed and the planner was silently
using its fallback. That "+2.09" was the value of changing the fallback order
from `CPH` to `HCP`, nothing more. Training was split into
`scripts/train_block_order.py` so that whether a model was written is explicit
rather than implied.

With the model actually fitted and loaded, paired over **400 held-out parts**:

| Tier | Fallback (HCP) | **Model** | Diff | 95% CI | |
|---|---:|---:|---:|---|---|
| Easy | 13.53 | **15.56** | +2.04 | [+1.65, +2.40] | significant |
| Medium | 13.69 | **14.95** | +1.26 | [+0.82, +1.70] | significant |
| Tools | 7.67 | **10.24** | +2.57 | [+2.03, +3.10] | significant |
| **Total (of 75)** | 34.88 | **40.75** | **+5.87** | **[+4.62, +7.11]** | significant |

Every interval excludes zero. The tools tier gained most (+2.57) because
alignment was its binding constraint (F-052), which is exactly what the
cross-cutting argument predicted.

**Slide potential.** High — "we had been using the second-most-common ordering,
and the right one is predictable at 0.90" is a concrete, quantified miss.

---

<a id="f-054"></a>
### F-054 — The 50,000 images cannot help; we are discarding data, not missing it
**Status:** confirmed · **Method** · **Source:** direct test of the missing pockets

**The question.** Five renders per part — 50,000 images — sit entirely unused, and
F-048 had shown that 22.5% of `FLOOR_WALL` operations belong to pockets we never
detect. The natural suggestion is to bring in the images. So: is the information
we lack actually in them?

**The test.** For every `FLOOR_WALL` operation on 120 held-out parts, check
whether a horizontal planar face exists in the STEP at the depth the tool
reached, *before* any of our filtering:

```
234 FLOOR_WALL operations checked
  matched a recognised floor : 181  (77.4%)
  unmatched                  :  53
  -> 53 rejected by our own filter
  ->  0 with no horizontal face in the STEP at all
```

Every single missing pocket has a face sitting in the BRep — and they are large,
unmistakable ones: 79x149, 37x79, 79x99, 73x57 mm.

**Conclusion.** The images are lossy 2D renders *of the very geometry the BRep
states exactly*. They cannot contain a pocket the BRep does not. We are not
missing information; we are **throwing it away in our own filter**, and a vision
model would be an expensive, approximate way to recover something we already have
exactly.

**Where the images could still earn their place** — none of these are the current
bottleneck, but for completeness: as a cheap sanity check on feature recognition,
or as an input to a model if the BRep were ever unavailable or unparseable. They
are not a route to the missing pockets.

**Action.** Fix the floor filter. This is worth ~22% of the pocket operations and
it is a bug, not a modelling problem.

---

<a id="f-055"></a>
### F-055 — 🔴 One shadowed variable cost 8.72 points
**Status:** confirmed (fixed) · **All tiers** · **Source:** tracing F-054's rejected faces

**The bug.** `extract_features` reads the stock bounds into `bottom_z` / `top_z`,
then loops over faces. The **cylindrical** branch contained:

```python
bottom_z, top_z = face.z_range      # same names as the stock bounds
```

Since `model.faces` interleaves planar and cylindrical faces, every planar face
processed after the first hole was tested against **that hole's z-range** instead
of the block's. Most pocket floors fell outside it and were silently discarded.

**How it hid.** The symptom looked like a modelling problem, not a bug, and was
misdiagnosed twice:

- F-041 concluded "some pockets take two operations and no geometric predictor
  separates them" — the extra operations were mostly floors we never found.
- F-048 trained a classifier for that phantom effect, and it *correctly* failed
  (0.859 against a trivial rule's 0.865) because there was no signal to find.
- Even the tightened merge rule (F-040 follow-up) measured "exactly neutral",
  which was true and completely beside the point.

What finally exposed it was F-054's question: *are the missing pockets in the
STEP at all?* All 53 were — large faces, 79×149 mm — which turned a modelling
question into a debugging one.

**Effect of the one-line fix.**

| Metric | Before | After |
|---|---:|---:|
| Recognised floors per part | 1.220 | **1.680** (truth 1.693) |
| Parts with exact `FLOOR_WALL` count | 68.0% | **98.7%** |
| Mean length ratio | 0.9129 | **0.9788** |

End-to-end, paired over 400 held-out parts:

| Tier | Before | **After** | Diff | 95% CI |
|---|---:|---:|---:|---|
| Easy | 15.56 | **17.28** | +1.72 | [+1.40, +2.05] |
| Medium | 14.95 | **21.19** | +6.24 | [+5.28, +7.20] |
| Tools | 10.24 | **11.01** | +0.77 | [+0.57, +0.98] |
| **Total (of 75)** | 40.75 | **49.47** | **+8.72** | [+7.43, +10.05] |

**Easy reaches 86.4%**, past the 80% target.

**The lesson, and it is uncomfortable.** Hours went into modelling a phenomenon
that did not exist. Every measurement along the way was *correct*; the
interpretations were all downstream of corrupted inputs. Two safeguards would
have caught it sooner:

1. **Validate recognition against published statistics continuously, not once.**
   F-031 checked holes against the paper and passed. Pockets were never given the
   same treatment — and 1.22 floors per part against a published 1.85 was visible
   the whole time.
2. **When a model fails to find a signal, suspect the inputs before the theory.**
   F-048's failure was the loudest possible hint and was read as a finding about
   pockets rather than a symptom.

The variable is now `face_bottom_z` / `face_top_z`, with a comment naming what it
cost.

---

<a id="f-056"></a>
### F-056 — Construction points were inflating every bounding box
**Status:** confirmed (fixed) · **Tiers:** Medium + Hard · **Source:** chasing the 11× pocket overcut

**Finding.** `StepModel._loop_vertices` walked an edge loop and recorded *every*
`CARTESIAN_POINT` it reached. But the traversal also passes through `CIRCLE`,
`LINE`, `VECTOR` and `AXIS2_PLACEMENT_3D`, each of which references construction
points — arc centres, line origins, placement anchors — that need not lie on the
face or even inside the solid.

Two visible symptoms, both dismissed at the time as quirks:

- chamfer faces reporting a z-range of **63.5–127.7 mm on a 73.6 mm block**;
- pocket clearing paths covering roughly **11× the true footprint**
  (1,294,923 mm³ swept against 114,510 mm³ actually removed).

Recording only points reached through a `VERTEX_POINT` fixes both. Feature
statistics still match the paper afterwards — blind share exactly 0.502, holes
2.283 per part against 2.330 — so the change tightens the geometry without
distorting recognition.

**Effect, paired over 400 held-out parts:** medium **21.36 → 23.04**
(+1.68 [+1.15, +2.24], significant); total **49.76 → 51.42**
(+1.66 [+1.04, +2.30], significant).

**Worth noting how it was found.** A separate fix — bounding tool flute length to
the cut depth — was implemented first and measured **exactly neutral**, because
clipping the sweep to the stock already bounds it vertically. That neutral result
is what showed the overcut was *horizontal*, which led here. A change that earns
nothing can still be informative if you measure it.

---

<a id="f-057"></a>
### F-057 — Pocket area clearing, and why paths are still near zero
**Status:** partial · **Tier:** Hard paths (25 pts)

**What was built.** Pockets previously got a single perimeter pass, sweeping a
thin ring and leaving the interior untouched. They now get contour-parallel area
clearing: concentric offsets stepping inward from one tool radius inside the
wall, at 0.6 diameter engagement, capped at 40 rings.

**What it achieved: almost nothing — 0.50 → 0.62 of 25.** Per-operation
diagnosis on a 15-operation part shows why, and the causes are distinct:

| Symptom | Operations | Cause |
|---|---:|---|
| Sweep raised an error | 6 of 15 | chamfers emit no cutting move by design (F-042); some drilling passes hit air because an earlier pass already cleared the material |
| Truth removal is 0 mm³ | 4 of 15 | denoising removes the whole difference for very small operations (F-022) |
| Gross volume mismatch | 3 of 15 | clearing rings follow the floor's bounding box, not its true outline |
| Scored well | `IoU 0.949`, `0.381` | drilling, when aligned |

**What the tier actually needs**, now separable:

1. **True pocket outlines.** F-056 tightened the vertices feeding the bounding
   box, but a bounding box is still wrong for any non-rectangular pocket. The
   floor's ordered boundary polygon is available in the STEP and is not yet
   extracted.
2. **Chamfer paths with correct offset geometry** — a 45° chamfer mill must be
   positioned so its conical flank lies *on* the chamfer surface. Placing the tip
   on the edge line overcuts (measured, F-042).
3. **Per-operation alignment.** Even with correct geometry, a swept volume is
   compared against truth's operation *k*; our chains are 0.970 accurate but
   ordering within a hole's chain still differs (rows 9–13 show
   `DRILLING`/`DEEP_HOLE_DRILLING` transposed).

This is the largest block of unclaimed points on the board (24.4 of 25) and the
sweep engine that scores it is already validated at ≈23.5/25 on real paths
(F-021). The gap is entirely in generation.

---

<a id="f-058"></a>
### F-058 — Easy hits 87%; medium's last 14 points are not geometry
**Status:** confirmed · **Tiers:** Easy + Medium · **Source:** `scripts/diagnose_medium.py`, 400-part evaluations

**Target:** easy ≥16/20 and medium ≥28/35.

| Tier | Score | % | Target |
|---|---:|---:|---:|
| **Easy** | **17.41 / 20** | **87%** | ✅ met |
| Medium | 23.02 / 35 | 66% | ✗ short by ~5 |

**Where medium's error lives**, per operation over 400 held-out parts:

| Feature | n | Mean IoU | Overcut | Undercut |
|---|---:|---:|---:|---:|
| chamfer | 81 | 0.99515 | 0.00371 | 0.00129 |
| hole | 250 | 0.99295 | 0.00525 | 0.00197 |
| **pocket** | 82 | **0.97929** | 0.01231 | 0.00906 |

Mean part IoU **0.99102**; on parts with exactly the right operation count,
0.99282. The band distribution for those parts:

| Threshold | Points | Share of exact-count parts |
|---|---:|---:|
| ≥ 0.999 | 35 | **31.4%** |
| ≥ 0.990 | 25 | 71.4% |
| ≥ 0.980 | 20 | 91.4% |
| ≥ 0.950 | 15 | 100% |

**Three geometry refinements, all measured neutral.** Pockets carried both
overcut *and* undercut, which reads as a wrong footprint shape, so:

| Change | Result |
|---|---|
| Extract the floor's **true ordered boundary** from the STEP edge loop instead of a bounding box | 0.97929 → 0.97926 |
| Order pockets shallowest-first | 0.97929 → 0.97766 (worse) |
| Order pockets deepest-first | identical to arbitrary order |
| Model drilled blind holes with a **conical bottom** instead of a flat one | 0.99295 → 0.99289 |

The band shares did not move at all — 31.4% ≥ 0.999 throughout.

**Why the outline fix changed nothing, and it is the useful part.** Measuring the
recovered boundaries against their bounding boxes gave area ratios of
**0.983–1.000**. The pockets in this corpus really are near-rectangular, so the
box was already right to within 1.7%. A plausible diagnosis — "both overcut and
undercut means the shape is wrong" — was simply false, and only measurement
showed it.

**What this means for the 80% target.** Reaching 28/35 needs most parts above
IoU 0.999, i.e. under **0.1%** volume error — roughly 12,000 mm³ on a 12 M mm³
part. The current gap is 0.9%, and it is *not* distributed across features in a
way any per-feature fix addresses. Two candidates remain, both structural rather
than geometric:

1. **Which** pocket, not how many. Pocket *counts* are 98.7% exact (F-055), but a
   right count with the wrong pocket at a given index still costs a whole
   feature's volume at that step.
2. **Block order errors.** The order model is 0.896 accurate; the ~10% of parts
   it gets wrong have badly wrong intermediate IPWs regardless of geometry.

And the ceiling itself is uncertain: **F-049 showed an unstated rubric convention
(Q-002) is worth 26% of this tier.** Under the truncate reading the same output
scores 22.25 against 13.25 — so "medium at 80%" may be a question about the
scorer as much as about the solution.

---

<a id="f-059"></a>
### F-059 — Medium is capped by an ordering the geometry does not contain
**Status:** confirmed · **Tier:** Medium (35 pts) · **Source:** final-part IoU, three ordering experiments, family-order audit

**The decisive measurement.** The finished part is order-independent: it is the
stock minus the union of everything removed. Comparing it isolates *what* we cut
from *when* we cut it.

| Measure | Value | Parts ≥ 0.999 |
|---|---:|---:|
| **Final-part IoU** | **0.99650** | **27/40 (67.5%)** |
| Mean IoU across all indices | 0.99088 | 31.4% |

**We cut the right material and cut it in the wrong order.** If the sequencing
matched, roughly 67% of parts would reach the top band instead of 31%, worth
about 8 points of the tier.

**Which ordering, though.** Three levels were tested, and the error is not at the
first two:

| Level | Test | Result |
|---|---|---|
| Family order (chamfer / pocket / hole) | our emitted order vs truth, 80 parts | **95.0%** match on first appearance, **90.0%** on full run structure; mean runs 2.59 against 2.64 |
| Tool blocks within a family | large-first / small-first / first-use | 0.99078 / 0.99025 / **0.99088**, all within noise |
| Individual features within a same-tool block | see below | **not recoverable** |

So the residual sits at the finest level: which specific hole or pocket is
machined first inside a block that uses one tool.

**And that is precisely what F-029 already showed cannot be recovered.** Testing
candidate rules for within-block ordering across 438 blocks gave
nearest-neighbour 40.2% (chance about 50%), sorted-by-Y 37.2% and sorted-by-X
30.1% (chance about 33%). Every candidate sat at or below chance, and travel was
18% longer than a greedy tour. The order appears to follow the sequence in which
features were created in the original CAD model, which is not present in the
geometry we receive.

**The asymmetry worth stating.** F-029 concluded this did not matter, and for the
easy tier that was right: 97.65% of tool blocks carry a single label, so
permuting features inside one cannot change the label sequence or the Levenshtein
distance. But the medium tier compares the *workpiece* at each index, and
permuting features changes which material is gone at that step. The same
unrecoverable ordering is free in one tier and expensive in another.

**Consequence.** Medium is bounded near its current 23 out of 35 by information
that is absent from the input, not by anything we have failed to build. Reaching
28 would require predicting CAD feature creation order from the finished solid.

---

<a id="f-060"></a>
### F-060 — The 400-part evaluation slice checks out against 1,600 more
**Status:** confirmed · **Method** · **Source:** `scripts/evaluate.py --offset 8400 --limit 1600`

**The worry.** Every score in this document, and the whole progression from
21.97 to 51.40, was measured on the same fixed 400 parts (offset 8000, provably
unseen by training). Reusing one slice for every comparison is correct for the
paired methodology in F-050 — you need the same parts before and after a change
— but it leaves open whether that particular 400 happens to be an easy or hard
sample of the held-out range. Parts 8,400 to 9,999, 1,600 of them, had never
been scored at all, by us or by any model.

**The check.** Score all 1,600, and compare against the 400 as two independent
samples, not paired (they are disjoint parts, so pairing does not apply here;
this is an unpaired bootstrap on the difference of means).

| Tier | 400-slice | 1,600-reserve | Diff | 95% CI |
|---|---:|---:|---:|---|
| Easy | 17.41 | 17.20 | +0.21 | [-0.22, +0.64], crosses zero |
| Medium | 23.02 | 22.72 | +0.31 | [-0.82, +1.43], crosses zero |
| Tools | 10.96 | 10.81 | +0.15 | [-0.48, +0.80], crosses zero |
| **Total** | **51.40** | **50.73** | **+0.67** | **[-1.22, +2.55], crosses zero** |

Every interval crosses zero. The 400-part slice is not a lucky draw; it is
statistically indistinguishable from the 1,600 parts we never looked at.

**The better number.** Combining all 2,000 held-out parts (offset 8000-9999)
gives a tighter estimate than either slice alone, and it lands almost exactly
where the 400-part number already was:

| Tier | Combined, 2,000 parts | 95% CI |
|---|---:|---|
| Easy | 17.24 / 20 | [17.06, 17.42] |
| Medium | 22.78 / 35 | [22.33, 23.23] |
| Tools | 10.84 / 20 | [10.60, 11.09] |
| **Total** | **50.87 / 75** | **[50.10, 51.65]** |

The confidence interval on the total tightens from ±2.09 (400 parts, F-050) to
**±0.78** (2,000 parts), simply from more data, no methodology change.

**Implication.** This is a confirmation, not a correction. The 400-part figure
that every other finding in this document is built on was not an outlier draw,
and the honest reported number moves from 51.40 to 50.87, well inside the
400-part slice's own prior confidence interval. Nothing else changes.

---

<a id="f-061"></a>
### F-061 — A proper hyperparameter sweep would have shipped a worse hole model
**Status:** confirmed · **Method** · **Source:** ad hoc sweep script, prompted by a documentation review

**The gap.** Both shipped `HistGradientBoostingClassifier` models were carrying
hyperparameters (`max_iter=300` on both, `l2_regularization=1.0` on the hole
model) with no documented search behind them. `learning_rate=0.1` and
`max_leaf_nodes=31` are scikit-learn's defaults, untouched. Nowhere in this
document or METHODS.md was that stated, which reads as an oversight, because it
was one.

**The check.** A grid search over `learning_rate ∈ {0.05, 0.1, 0.2}`,
`max_leaf_nodes ∈ {15, 31, 63}`, `l2_regularization ∈ {0, 1.0}`, done the way a
tuning search should be done here: a third split carved out of the *training*
range only (parts 0-6,999 fit, 7,000-7,999 validate), so the parts-8,000-and-up
test set that every other number in this project rests on was never touched by
model selection.

| Model | Best-on-validation config | Validation gain | Refit, held-out test |
|---|---|---:|---:|
| Block order | matched the shipped config | +0.0046 | **0.8968 vs 0.8968 — no change** |
| Hole chain | `lr=0.05, leaves=15, l2=0` | **+0.0078** | **0.9415 vs 0.9701 — a 2.86-point loss** |

**The counter-intuitive result.** The hole-chain configuration that looked
better on 2,044 validation rows was **worse by nearly three points** on the
6,757-row held-out test once both were refit on the full training range and
compared honestly. The validation split has fifteen classes, several rare, so a
configuration can fit that split's particular noise and generalize worse
everywhere else. Block order showed no such effect and no gain either way.

**Learned.** This is F-050's lesson (a comparison on too little data is not
evidence) applied to model selection rather than feature engineering, and here
it would have actively misled us: naively trusting the validation winner would
have shipped a measurably worse model. The hyperparameters chosen originally,
without a formal search, turn out to be the right ones. The gap was real
(nothing justified the choice on paper), but the choice itself was not wrong,
and it is now backed by a measurement instead of an assumption.

---

<a id="f-062"></a>
### F-062 — Gradient boosting was never compared against other model families, until now
**Status:** confirmed · **Method** · **Source:** ad hoc family-comparison script, prompted by a documentation review

**The gap.** `HistGradientBoostingClassifier` was chosen for both models at the
start of the project and never revisited. No logistic regression, no k-nearest
neighbours, no plain decision tree, no random forest, no small neural network
was ever fit and measured. F-047 and F-053 justify learning *at all* against the
rule baseline; neither justifies gradient boosting specifically against any
other family. That is a real gap in the record, not just in the prose.

**The check.** Six families, fit on the same features and labels, selected on
the same training-range-only validation split as F-061 (parts 0-6,999 fit,
7,000-7,999 validate), so family selection cannot see the parts-8,000+ test set
either.

**Hole chain (10 inputs, 15 chain classes):**

| Model | Validation accuracy |
|---|---:|
| Majority class | 0.2613 |
| Logistic regression | 0.6967 |
| k-nearest, k=15 | 0.6893 |
| Random forest, 300 trees | 0.8527 |
| Small MLP (64, 32) | 0.7652 |
| Single decision tree | 0.9442 |
| **Gradient boosting (shipped)** | **0.9692** |

**Block order (11 inputs, 10 order classes):**

| Model | Validation accuracy |
|---|---:|
| Majority class | 0.3570 |
| k-nearest, k=15 | 0.7700 |
| Single decision tree | 0.8215 |
| Logistic regression | 0.8650 |
| Small MLP (64, 32) | 0.8776 |
| Random forest, 300 trees | 0.8947 |
| **Gradient boosting (shipped)** | **0.9016** |

Gradient boosting wins outright on both tasks, and was already the validation
winner in both, so no refit-and-recheck against the test set was needed the way
F-061 required for the losing hyperparameter case. Held-out test accuracy
reproduces exactly: **0.9701** hole chain, **0.8968** block order, matching every
number already reported elsewhere.

**Why, not just that.** Tree-based methods dominate on both tasks, and a single
undocumented decision tree alone reaches 0.9442 on hole chains, five points
below gradient boosting but thirty points above logistic regression and every
distance-based or linear method tried. That is consistent with the pipeline's
own rule-based components, which are themselves threshold logic on the same
features (`DEEP_HOLE_DIAMETER_RATIO`, `HOLE_MILLING_RANGE`, and so on): the true
decision structure here is axis-aligned thresholds, which is exactly the
inductive bias a tree has and a linear or distance-based model does not.
Boosting improves on one tree by correcting its errors sequentially; bagging
(random forest) does not help as much here, likely because ten features and
several rare classes leave little for row and feature subsampling to exploit.

**Implication.** The gap in the record was real: nothing on paper justified
gradient boosting over any alternative. The choice itself, now checked, was
right on both tasks and by a comfortable margin, so nothing about the shipped
pipeline changes. What changes is that this is now a measured conclusion rather
than an inherited default.

---

<a id="f-063"></a>
### F-063 — Feature importance: 4 inputs carry 95%, and 2 are dead weight
**Status:** confirmed · **Method** · **Source:** `sklearn.inspection.permutation_importance`, 10 repeats, held-out parts only

**The gap.** Both models were shipped without anyone ever asking which inputs
they actually use. For a data-mining submission that is a conspicuous omission:
feature importance is standard practice, and its absence meant we could not say
whether our engineered features earned their place.

**Method.** Permutation importance on the held-out range (parts ≥ 8,000), not
tree gain. Gain is biased toward high-cardinality continuous features;
permutation asks the honest question directly, how much held-out accuracy is
lost when this one column is shuffled. Ten repeats, standard deviations below.

**Hole chain classifier** (0.9701 held-out, 6,757 rows, 15 classes):

| Feature | Accuracy drop | sd | Share |
|---|---:|---:|---:|
| `diameter_mm` | **0.6333** | 0.0064 | **50.5%** |
| `aspect` | 0.2262 | 0.0043 | 18.1% |
| `depth_mm` | 0.1959 | 0.0033 | 15.6% |
| `through` | 0.1361 | 0.0035 | 10.9% |
| `stock_height` | 0.0369 | 0.0017 | 2.9% |
| `top_drop` | 0.0142 | 0.0011 | 1.1% |
| `in_pocket` | 0.0069 | 0.0006 | 0.6% |
| `depth_fraction` | 0.0034 | 0.0007 | 0.3% |
| `same_diameter_count` | −0.0002 | 0.0003 | none |
| `n_holes` | −0.0003 | 0.0006 | none |

**Block order classifier** (0.8968 held-out, 3,015 rows, 10 classes):

| Feature | Accuracy drop | sd | Share |
|---|---:|---:|---:|
| `n_holes` | **0.3044** | 0.0049 | **27.2%** |
| `n_floors` | 0.2192 | 0.0055 | 19.6% |
| `n_chamfers` | 0.2095 | 0.0042 | 18.7% |
| `mean_hole_depth` | 0.2033 | 0.0076 | 18.2% |
| `n_through` | 0.0965 | 0.0036 | 8.6% |
| `stock_height` | 0.0561 | 0.0036 | 5.0% |
| `max_hole_diameter` | 0.0272 | 0.0038 | 2.4% |
| `stock_length` | 0.0027 | 0.0023 | 0.2% |
| `stock_width` | 0.0004 | 0.0013 | 0.0% |
| `n_blends` | −0.0001 | 0.0014 | none |
| `max_pocket_depth` | −0.0013 | 0.0021 | none |

**Three things worth reading off these tables.**

**1. The model uses the same information the rules used, but finds better
boundaries in it.** The hole classifier's top four features, diameter, aspect,
depth, through, are exactly the four quantities the hand-written rules keyed on
(`SPOT_DRILL_MAX_DIAMETER`, `DEEP_HOLE_MIN_ASPECT`, `PILOT_MIN_DIAMETER`, and
the through/blind test). They carry **95.1%** of importance. So the model did
not discover new signal; it found a better decision surface in the same
four-dimensional space. That corroborates F-062 directly: the structure here
really is axis-aligned thresholds, which is why trees win and why a linear
model cannot compete.

**2. Q-013 gets a partial negative answer.** `in_pocket` and `top_drop` were
engineered specifically to test the hypothesis that `HOLE_MILLING` is selected
because a hole opens on a pocket floor rather than the top face. Together they
are worth **1.7%**. The hypothesis is not supported by the data. The mechanism
behind milled-hole selection remains unexplained, but this rules out the
leading candidate rather than leaving it open.

**3. Two features in each model are dead weight**, with importance at or below
zero: `same_diameter_count` and `n_holes` on hole chains, `n_blends` and
`max_pocket_depth` on block order. `n_blends` is a second, independent
confirmation that corner blends contribute nothing to the shipped pipeline;
they are recognised, they feed no operation, and now we know they do not even
help as a predictor. Block footprint (`stock_length`, `stock_width`) is
likewise irrelevant, which is intuitive: how the families are ordered depends
on how many of each feature exists, not on how wide the plate is.

**Not acted on.** Dropping the four dead features would simplify the models but
cannot improve them measurably, since each contributes about zero. Recorded as
future work rather than a change, because a refit and a re-validation is not
justified by an expected gain of nothing.
The honest options are to accept the ceiling, or to ask the organizers whether
the intended reading of the rubric is the one we assumed, since Q-002 alone is
worth 2.25 points here.

---

## Open questions

<a id="q-001"></a>
**Q-001 — Rubric sub-table totals.** *(blocking scoring fidelity, not progress)*
How do the hard-tier tables reconcile with their section budgets (F-006), and are
band edges inclusive of the upper or lower band? → Ask organizers.

<a id="q-002"></a>
**Q-002 — Medium tier with a wrong sequence length.** *(assumption documented)*
The rubric says IoU is "averaged across all operations" but doesn't define the
mismatch case. We score over the union of indices, so a missing or invented
operation contributes IoU 0. Alternative readings (truncate to the shorter, or
align by DTW) would score materially differently. → Ask organizers.

<a id="q-003"></a>
**Q-003 — Final IPW vs. BRep weighting.** *(assumption documented)*
"In addition final IPW will be compared against the target geometry" — is that
comparison folded into the mean, or scored separately? We fold it in. → Ask organizers.

<a id="q-004"></a>
**Q-004 — Test set.** *(external dependency)*
README says "Shared soon". Unknown size, part naming, and whether it is drawn
from the same generator seed range. Affects nothing yet.

**Q-006 — Tool geometry parameters are uncalibrated.** ✅ **RESOLVED** by F-018.
`details.txt` publishes exact `(D)`, `(C)`, `(B)`, `(FL)` values. Our inferred
chamfer geometry matched to four decimals; flute length needs correcting from
the parsed value. Build a tool library keyed on the 431 distinct tool ids.

**Q-007 — Does the sweep hold for drilling operations?** ✅ **RESOLVED** by F-021.
Not initially — it exposed three silent parsing bugs (F-023). After fixing them,
five of seven subtypes exceed IoU 0.99, covering 83.9% of the corpus;
frequency-weighted score ≈23.5/25.

<a id="q-009"></a>
**Q-009 — Do the graders denoise the IPW difference?** *(blocking ~15% of hard-tier score)*
Consecutive IPWs differ by 17-micron tessellation sheets as well as by real
material (F-022). On a small operation that noise is 12× the signal, so a
*perfect* tool path scores IoU ≈0.07 against the raw difference. If the official
scorer does not filter these, the tool-path score on small operations is
unattainable by any method. → Ask the organizers whether the reference volume is
cleaned, and how.

**Q-008 — What do the `operations.json` `name` fields cover?** ✅ **RESOLVED** by
F-026. A closed vocabulary of 29 names mapping directly onto the generative
feature taxonomy.

**Q-010 — Is the operation sequence invariant to cuboid symmetry?** ✅ **RESOLVED**
by F-029. Effectively yes, for the labels that are scored: 97.65% of same-tool
blocks are label-homogeneous, so reordering within a block cannot change the
label sequence. Block order itself depends on tool-change minimisation and
precedence, both rotation-invariant. Augmentation is sound; block-order
invariance is argued rather than directly tested.

<a id="q-011"></a>
**Q-011 — Can operation *counts* be predicted from feature geometry?** *(open, now the critical path)*
F-029 reduces the easy tier to ~4.5 `(label, count)` pairs. The counts are the
open part: how many `SPOT_DRILL` operations a part needs depends on how many
holes require centring, and how many `DRILL_TO_ENLARGE_*` passes depends on
diameter thresholds. → Mine the relationship between hole/pocket parameters and
operation multiplicity. **This is the next experiment.**

**Q-005 — STEP reading toolchain.** ✅ **RESOLVED** by F-030. Direct parsing; no
CAD kernel. Every surface in the corpus is a plane or a cylinder.

<a id="q-013"></a>
**Q-013 — What actually selects `HOLE_MILLING` and `SPOT_DRILLING`?** *(open, F-034)*
Two hypotheses for milling are refuted. Milled holes are 12.3–19.9 mm with low
aspect ratio, and the mechanism is unknown. Spot drilling correlates with small
diameter and through-holes but is not determined by them. → Test whether the hole
is nested inside a pocket (so its entry face is not the top plane), whether it
intersects another feature, and whether a flute-length limit binds. Needs Q-012's
pocket recognition first.

<a id="q-012"></a>
**Q-012 — Recognise pockets and chamfers, not just holes.** *(open, next)*
F-031 covers holes and corner blends. Pocket *type* (corner / edge / center /
slot) and chamfers still need planar-face topology — adjacency, which faces sit
below the top plane, which planes are at 45°. → Extend `features.py`; validate
against the paper's pocket-type mix (center 28.8%, corner 27.9%, edge 27.8%,
slot 15.5%) and chamfer count (16,280 across the corpus).

---

## Numbers worth reusing verbatim

| Quantity | Value |
|---|---|
| Parts | 10,000 (from 11,416 generated; 87.6% yield) |
| Total operations | 91,702 |
| Operations per part | mean 9.17, min 1, max 38, σ 5.21 |
| Features per part | mean 5.81, median 6, max 14 |
| Total features | 58,086 — 16,280 chamfers, 18,484 pockets, 23,322 holes |
| Block size | L,W ∈ 200–500 mm; H ∈ 50–150 mm |
| Block volume | mean 12,252,896 mm³ |
| Parts with all three feature types | 6,052 (60.5%) |
| Pocket relations | 85.5% standalone, 13.2% nested, 1.3% abutting |
| Hole depth types | 50.2% blind, 49.8% through |
| Dataset acceptance gate | >99% material removed **and** final IoU > 0.999 |
| Dataset zip | 5.2 GB, MD5 `831ccc4bd0ee62759ec383556b8c95da` |

The acceptance gate is worth noting: the organizers held their *own* generator to
IoU > 0.999, the same threshold as the top medium band. The band is achievable —
it is what a correct simulation produces.
