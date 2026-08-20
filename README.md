# ASME CIE 2026 Student Hackathon, Problem 1

**Predicting a complete computer numerical control (CNC) machining process
plan from computer-aided design geometry alone.**

Given a finished part as a boundary representation, we predict the ordered
sequence of machining operations, the in-process workpiece after each cut, the
tool used for each operation, and the numerical control code that drives the
machine.

| | |
|---|---|
| **Held-out score** | **52.25 / 100** on 400 parts no model was trained on, confirmed at **51.7 / 100** across all 2,000 held-out parts (tighter interval, same conclusion, see below) |
| **Expected test score** | **about 48 / 100**, and section [What we expect to score](solution/METHODS.md#what-we-expect-to-score-on-the-test-set-and-why-it-is-lower) explains why we report the lower number |
| **Test submission** | 30 of 30 parts, **0 failures**, **120 of 120 artifacts pass the official validator**, 13.1 seconds total |
| **Tests** | 96, all passing |

Full write-up: **[solution/METHODS.md](solution/METHODS.md)**.

---

## Terms used below

Spelled out once, because several recur.

* **CNC**: computer numerical control, the machine type this problem targets.
* **CAM**: computer-aided manufacturing, the software category that produces
  machining plans. This dataset was generated with Siemens NX CAM.
* **STEP**: Standard for the Exchange of Product model data, the neutral
  computer-aided design file format (`.stp`) carrying the part geometry.
* **BRep**: boundary representation, the exact description of a solid's faces,
  edges, and vertices. Supplied here as a STEP file.
* **IPW**: in-process workpiece, the shape of the partly machined block after a
  given operation.
* **NC code**: numerical control code, the instruction list a machine executes,
  delivered as `.ptp` files.
* **IoU**: intersection over union, the volume overlap measure used to score the
  medium and hard tiers.

---

## 1. Approach

The pipeline is **deterministic end to end, with two learned decision points.**
Geometry is never predicted; it is computed exactly. Only the *plan* is learned.

```
STEP  ──►  RECOGNISE  ──►  DECIDE  ──►  COMPUTE  ──►  4 deliverables
           features        the plan     the shapes
           computed        LEARNED      computed
```

Three feature types become seven operation types, and one feature usually needs
several operations:

| We recognise a | The machine performs | Dataset label |
|---|---|---|
| hole | spot drill, drill, deep-hole drill, hole mill, bore | `SPOT_DRILLING`, `DRILLING`, `DEEP_HOLE_DRILLING`, `HOLE_MILLING`, `BORING_REAMING` |
| pocket | mill the floor and the walls | `FLOOR_WALL` |
| chamfer | mill the contour, using a chamfer tool | `AREA_MILL` |

Two structural findings shaped the design before any model was trained.

**The main operation label carries no independent information.** `AREA_MILL`
occurs 20,067 times and so does `mill_contour`; `FLOOR_WALL` and `mill_planar`
are both 18,560; the five hole-making sub-labels sum to exactly the
`hole_making` total. The sub-label determines the main label with certainty, so
a model only needs to predict one of them. That removes an entire error mode.

**A plan is not sorted, it is grouped by tool.** Operations come in tool blocks,
so predicting a global sort order is the wrong problem. We predict block order
instead.

---

## 2. Techniques used

### Parsing, with no CAD kernel

The corpus is **74.8 percent planar and 25.2 percent cylindrical surfaces, and
0 percent anything else**, so a direct ISO 10303-21 entity-graph reader is
sufficient. `parsing/step.py` is about 430 lines and needs no geometry kernel.
This keeps the whole pipeline installable from pip and fast: 0.3 seconds per
part end to end.

### Feature recognition

Holes are cylindrical faces with a closed boundary edge; pocket floors are
horizontal planes strictly inside the stock; chamfers are slanted planes; corner
blends are partial cylinders. Recognition is validated continuously against
statistics published in the dataset paper that our recogniser never sees:

| Metric | Ours | Paper |
|---|---:|---:|
| Holes per part | 2.283 | 2.330 |
| Hole diameter mean, mm | 16.97 | 17.47 |
| Blind hole share | 0.502 | 0.502 |
| Block length, width, height means | 345, 341, 97 | 350, 351, 100 |

### The two learned components

Both are `HistGradientBoostingClassifier` from scikit-learn. Both fall back to a
hand-written rule if no model file is present.

| Decision | Inputs | Classes | Rule | Model |
|---|---:|---:|---:|---:|
| Hole to its chain of operations | 10 | 15 | 0.374 | **0.970** |
| Part to its tool block order | 11 | 10 | 0.349 | **0.896** |

Two further decisions stayed rule based **because the rules won**, which we
report rather than hide. A classifier on pocket geometry scored 0.859 against
0.865 for the rule, and chamfers are already exact at one operation per face.
The pocket model's failure turned out to be the most useful result in the
project: it was evidence about our inputs, not about pockets, and tracking it
down found a variable-shadowing bug that was silently discarding a third of all
pocket floors.

### Exact geometry, one engine for two tiers

The rubric scores a tool path against the difference between consecutive
workpieces. That is an identity, so a single engine serves both the 35-point and
25-point tiers:

```
V_k  =  IPW_(k-1) \ IPW_k  ≡  volume swept by operation k
```

Every cutter is a **convex** solid of revolution, so the region swept along a
straight move is exactly the convex hull of the tool at both ends,
`K ⊕ [a,b] = conv((K+a) ∪ (K+b))`. That makes the sweep exact rather than
sampled, and cuts tool placements per part from about 4,944 to 272. Booleans use
`manifold3d` through `trimesh`.

Validated against ground truth on a real chamfering operation: metadata reports
53,100.9 mm³ removed, our swept volume gives 53,101.6, which is **IoU 0.99997**.

### A local reimplementation of the rubric

We built the grader before the predictor, so every change carried a number. The
rubric scores by **lookup band, not a continuous formula**, which makes the total
a step function of the geometry and changed what we worked on. Below 0.90 mean
overlap the workpiece tier pays nothing at all, so fixing operation *counts*
mattered more than any geometry work in the first two iterations.

---

## 3. Data filtering and augmentation

Reported in full, as the tutorial asks.

**Filtering applied to training data.** Nine holes, 0.04 percent of 22,500,
belonging to three operation chains that occur fewer than five times in the
entire corpus, were removed. Such chains cannot be learned or fairly evaluated,
and a class with a single member breaks the stratified split the gradient
booster uses internally. They were removed from **both halves of the split, not
from training alone**, so the reported accuracy is not flattered by quietly
dropping hard cases from the test side.

**Filtering applied when scoring.** Consecutive workpiece meshes are
re-triangulated between exports, so their boolean difference contains thin
sheets alongside the material actually removed. We measured sheets as thin as
**17 microns** spanning up to 92 mm. On a large operation this is irrelevant; on
a small one it dominates. For one spot-drilling operation the raw difference was
42.0 mm³ of which the real dimple was 3.3, so the noise was twelve times the
signal. We discard bodies thinner than 0.05 mm on any axis. **The filter is on
thickness, not volume**, because those sheets are thin but not small, and a
volume filter keeps exactly the wrong ones.

**Augmentation used: none.** We identified two valid augmentations and used
neither, because the training data proved sufficient. One tempting augmentation
is invalid and we want to be explicit about rejecting it: **uniform scaling is
not label preserving here**, because changing feature sizes changes tool
selection, which changes the labels.

**Modalities deliberately unused.** We read **none of the 50,000 rendered
images**. We measured what they could contribute and concluded they carry
nothing the boundary representation does not already have, so this is a discard,
not an oversight. One test part ships with a note to infer it without images;
our pipeline treats it identically to the other 29.

---

## 4. How we validated

Four layers, and two rules we treat as non-negotiable.

1. **Unit tests against closed forms**, not stored values. A cylinder of radius
   r and height h dragged a distance L must sweep `πr²h + 2rLh`. A test that
   merely pinned current behaviour would have let a systematic error through.
2. **Feature recognition against the dataset paper's published statistics**, as
   in the table above.
3. **Geometry against ground truth**, three independently derived quantities
   agreeing to five decimal places.
4. **End to end on held-out parts, with confidence intervals.**

**Split by part, never by feature.** Holes on one part share a block, a feature
mix, and a tool set, so splitting by hole would place near-duplicates on both
sides. The split is deterministic on part number: everything below 8,000 trains,
everything at or above 8,000 is never touched. Honest by construction rather
than by argument.

**Compare against the rule we already had, never against chance.** Beating
chance proves nothing when a working rule exists. Training refuses to save a
model that does not clear its rule.

Every configuration change is decided by a **paired comparison with a bootstrap
confidence interval**, and a change whose interval contains zero is dropped. This
mattered: measured sloppily on 20 parts by comparing averages, our best change
looked worth +3.31. Measured properly on 150 parts, scoring the same part before
and after, it was **+8.14 with a 95 percent interval of [+5.3, +11.1]**. Part-to-
part variation is roughly 21 points and swamps an 8-point effect unless you pair.

We quote held-out numbers, not in-sample ones. Scoring inside the training range
gives 36.85 where held-out parts give 31.22 at the same point in development.

---

## 5. Results

On 400 parts at or above index 8,000, which no model was trained on:

| Category | Available | Ours | Share |
|---|---:|---:|---:|
| Easy, operation sequence | 20 | 17.53 | 88% |
| Medium, in-process workpiece | 35 | 23.02 | 66% |
| Hard, tool selection | 20 | 10.91 | 55% |
| Hard, tool path geometry | 25 | 0.79 | 3% |
| **Total** | **100** | **52.25** | **52%** |

That 52.25 is measured on the 400 held-out parts used throughout development
(offset 8,000, limit 400). The other 1,600 held-out parts (offset 8,400 to
9,999) were never touched by any model or by any configuration decision, and
scoring them separately gives a second, independent check:

| | 400-part slice | 1,600-part reserve | All 2,000 combined |
|---|---:|---:|---:|
| Easy | 17.41 | 17.20 | 17.24 |
| Medium | 23.02 | 22.72 | 22.78 |
| Tools | 10.96 | 10.81 | 10.84 |
| **Total, of 75** | **51.40** | **50.73** | **50.87** |
| 95% CI | [49.69, 53.08] | [49.89, 51.60] | **[50.10, 51.65]** |

The two slices agree; the difference between them crosses zero on every tier
(unpaired bootstrap). So this is a confirmation, not a correction: the 400-part
figure was not a lucky draw, and the full 2,000-part estimate lands almost
exactly where it already was, with less than half the uncertainty. Adding the
~0.79 path-tier score, that is **51.7 / 100** across every held-out part we
have, next to the original **52.25 / 100** from the 400 alone.

Progress came in measured steps, each attributable to one diagnostic:
**21.97 → 28.07 → 40.75 → 49.5 → 51.4** on the 75 points we tracked during
development, the machine code tier having sat near zero throughout. That
progression is reported on the original 400-part slice, since it is what every
iteration in this project was actually measured against at the time.

**Two limits, and they are different in kind.** The workpiece tier is capped by
information the input does not contain: what remains is the order of features
*within* a single-tool block, and every candidate rule we tested sits at or
below chance. Tool path geometry has no such cap. Our engine scores **23.5 of
25 on ground-truth machine code and 0.79 on our own**, so the scorer is right and
the generator is not. Roughly 24 of our missing points sit there, we know what
each needs, and none of it is research.

### Test set

Generated by `scripts/predict_test_set.py`:

```
30 parts written, 0 failures, 13.1s total
PASS: 120   FAIL: 0        (official validate_submission.py, all four tiers)
```

Output lives in `solution/outputs/submission/` as `easy/` (30 JSON),
`medium/` (30 folders, 398 STL), `hard/` (30 JSON) and `hard_tool_path/`
(30 folders, 398 PTP).

We expect **about 48 rather than 52** on this set. The test parts are 1.44 times
more complex than our held-out sample, averaging 13.27 predicted operations
against 9.21, and our score falls as complexity rises with a correlation of
−0.329. Reweighting to the test set's actual complexity mix costs 3.71 points.
We report the lower number because it is the one we believe.

---

## 6. Code

About 10,500 lines of Python, 4,768 of which are the library itself.

```
solution/
  src/machineplan/
    parsing/step.py        direct STEP reader, no CAD kernel
    parsing/ptp.py         NC code parser
    parsing/dataset.py     streams the 5.2 GB corpus from the zip, never extracted
    features.py            feature recognition from the boundary representation
    predict.py             plan prediction, rules plus the two models
    models/                hole_chain.py, block_order.py
    geometry/sweep.py      exact convex-hull swept volumes
    geometry/tooling.py    tool solids of revolution
    generate.py            workpiece meshes and NC code
    scoring/               local reimplementation of the full rubric
  scripts/                 training, evaluation, and every diagnostic
  tests/                   96 tests
```

Diagnostic scripts that produce no submission output are kept deliberately,
because they are the evidence behind the design decisions.

### Reproducing

Python 3.12. Requires numpy, scipy, trimesh, manifold3d, shapely, rtree,
networkx, scikit-learn, joblib, pytest.

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt

python scripts/download_dataset.py        # resumable, checksum verified
python scripts/build_hole_dataset.py      # extract the training table
python scripts/train_hole_classifier.py   # fit and save, only if it beats the rule
python scripts/train_block_order.py       # fit and save the block-order model
python scripts/evaluate.py --offset 8000  # held-out score with confidence intervals
python scripts/predict_test_set.py        # write the test-set submission
python -m pytest tests -q                 # 96 tests
```

`--offset 8000` matters: it restricts evaluation to parts no model was trained
on. Every analysis in METHODS.md has a script that regenerates it.

**Determinism** is tested, not asserted. `tests/test_determinism.py` fingerprints
operation labels, tool choices, every mesh volume and face count, and every line
of emitted machine code, then checks two runs agree and that different parts
produce different fingerprints, so the test cannot pass vacuously.

---

## 7. Open questions for the organizers

Two ambiguities in the rubric materially affect scoring, and we have implemented
both readings rather than silently picking one.

1. **The point tables do not sum to their stated section budgets.** Tool
   selection is titled 20 points but its table tops out at 10; tool path geometry
   is titled 25 but its three tables sum to 30. We score the tables as printed
   and rescale, and made it a switchable option.
2. **The convention when predicted and true sequence lengths differ** is
   unstated. It is worth about 2.25 points on the medium tier without a line of
   code changing.

---

## Provided materials

Dataset: https://doi.org/10.5281/zenodo.21653081
Kickoff Slides: [Kickoff PPT](Hackathon_Kickoff_Problem1.pdf)
Data Tutorial: [Tutorial PPT](Tutorial_Hackathon_Problem1.pdf)
Rubrics: [Rubrics](Rubrics.pdf)
Dataset Description: [Dataset Description](Dataset_Description.pdf)
Test Data: `Test_Data/`, 30 parts
