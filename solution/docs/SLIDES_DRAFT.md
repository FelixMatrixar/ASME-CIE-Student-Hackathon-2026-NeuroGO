# Presentation draft v6: 10 slides, 3 minutes

Changes from v5, all from review, and the last one was a genuine error.

**Vocabulary was inconsistent.** Features and operations were used
interchangeably. Slide 2 now states the mapping before anything depends on it,
and "chamfer milling", which is not a real operation name, is gone.

**Slide 4 showed four operation types after slide 2 promised seven.** It now
shows the recorded diagnostic in full.

**A part is not a feature.** Slide 5's ordering decision moved into its own
table so it cannot read as a fourth feature type.

**Slide 6 dropped a technical term cold.** It is now the story of nearly
discarding our best change by measuring it badly, and the jargon word "ships" is
gone from the whole deck.

**Two different scoring scales were being mixed.** This is the important one.
The progression 40.75, 49.47, 51.40 is out of **75**, not 100: it is the easy,
medium and tool tiers only, which is what we tracked during development because
the machine code tier sat near zero throughout and would have masked every
change. Our final figure across all four tiers is **52.2 out of 100**. Slide 9
now reconciles the two explicitly instead of quoting a 75-point number under a
100-point heading.

---

## Slide 1: Title and problem

**On screen**

> ASME CIE 2026 STUDENT HACKATHON &middot; PROBLEM 1
>
> # From Block to Part
>
> Recovering a complete machining process plan from boundary representation
> geometry alone.

| Given, per part | Predict, per part |
|---|---|
| Boundary representation, STEP file | Operation sequence, 20 pts |
| Five rendered views | In-process workpiece after each cut, 35 pts |
| | Tool type and diameter, 20 pts |
| | Machine code, 25 pts |

> **MachinePlan-10K: 10,000 parts, 91,702 operations, 5.2 gigabytes.**
> Ground truth comes from deterministic rules inside Siemens NX, so this is rule
> recovery, not open-ended design.

**Say:** Given only the finished CAD model, predict every operation that made it.
There is a correct answer, produced by a rule engine, and we recover those rules
from ten thousand worked examples.

---

## Slide 2: What we built

Layered. The three boxes read in three seconds from the back of a room. The
specification strip underneath is set small, and is there for a judge reading the
deck afterwards or pausing the video. It does not compete for attention, and the
presenter never reads it aloud.

**On screen, upper two thirds**

> THE SYSTEM
>
> ## Learning decides the plan. Geometry is computed exactly.

```
   STEP file  ─►  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐  ─►  4 files
                  │  RECOGNISE   │   │   DECIDE     │   │   COMPUTE    │
                  │   features   │──►│   the plan   │──►│  the shapes  │
                  │              │   │              │   │              │
                  │   computed   │   │   LEARNED    │   │   computed   │
                  └──────────────┘   └──────────────┘   └──────────────┘
                       grey               amber               grey
```

**Directly under the boxes, one line that the rest of the deck depends on**

> **3 feature types** become **7 operation types.** One feature usually needs
> several operations, so these are not two names for the same list.
>
> | We recognise a | The machine performs | The dataset calls it |
> |---|---|---|
> | **hole** | spot drill, drill, deep-hole drill, hole mill, bore | `SPOT_DRILLING`, `DRILLING`, `DEEP_HOLE_DRILLING`, `HOLE_MILLING`, `BORING_REAMING` |
> | **pocket** | mill the floor and the walls | `FLOOR_WALL` |
> | **chamfer** | mill the contour, using a chamfer tool | `AREA_MILL` |
>
> Note the last row: there is no operation called "chamfer milling". The
> operation is contour milling; *chamfer* is the tool it holds.

**On screen, lower third, small monospace, full disclosure**

| Stage | Implementation |
|---|---|
| **Parse** | Direct ISO 10303-21 entity-graph reader, about 300 lines. No CAD kernel. Corpus is 74.8% planar and 25.2% cylindrical surfaces, 0% anything else |
| **Recognise** | Holes: cylindrical faces with a closed boundary edge. Pocket floors: horizontal planes strictly inside the stock. Chamfers: slanted planes. Corner blends: partial cylinders |
| **Decide, learned 1** | `HistGradientBoostingClassifier`, 10 hole-geometry inputs &rarr; 15 operation-chain classes |
| **Decide, learned 2** | `HistGradientBoostingClassifier`, 11 part-geometry inputs &rarr; 10 tool-block-order classes |
| **Decide, rules** | One operation per pocket floor. One per chamfer face. Tool diameters from ratios mined over 1,200 parts |
| **Compute** | Exact mesh booleans via manifold3d. Swept volumes as convex hulls. Chamfer removal as a half-space cut |
| **Emit** | Sequence JSON, workpiece STL per operation, tool JSON, machine code PTP |

> Deterministic end to end: same input, same output, every run. Covered by tests.

**Say:** Three stages. We recognise features, machine learning decides the plan,
and every shape is computed exactly. Only the middle box is learned, and it is
two gradient boosting classifiers, nothing more exotic.

*Design note: the middle box is amber and clearly larger. Everything else grey.
The specification strip is set at roughly 60 percent of body size in monospace,
separated by a hairline rule, deliberately quiet. If it competes with the
diagram, shrink it further rather than cutting rows.*

---

## Slide 3: The grader, and what it measures

**On screen**

> METHOD
>
> ## We built the grader before the solution

Three metrics, stated:

> **Sequence**, edit distance normalised by length, plus multiset F1
>
> $$\hat{d}=\frac{d_L(P,G)}{\max(|P|,|G|)} \qquad F_1=\frac{2PR}{P+R}$$
>
> **Geometry**, volumetric intersection over union
>
> $$\mathrm{IoU}(A,B)=\frac{\mathrm{vol}(A\cap B)}{\mathrm{vol}(A\cup B)}$$
>
> **Machine code**, swept volume against material actually removed, plus
>
> $$\text{overcut}=\frac{\mathrm{vol}(P\setminus G)}{\mathrm{vol}(G)} \qquad
>   \text{undercut}=\frac{\mathrm{vol}(G\setminus P)}{\mathrm{vol}(G)}$$

**Then, how they combine, which is the part that shapes the whole project**

> The rubric scores by **lookup band, not a continuous formula**:
>
> $$S=\underbrace{\beta_L(\hat d)+\beta_F(F_1)}_{20}
>   +\underbrace{\beta_M(\overline{\mathrm{IoU}})}_{35}
>   +\underbrace{\tfrac{20}{10}\,\overline{\beta_D(e_k)}}_{20}
>   +\underbrace{\tfrac{25}{30}\big[\beta_I+\beta_O+\beta_U\big]}_{25}$$
>
> Every $\beta$ is a step function. For the workpiece score:
>
> | Mean IoU | ≥ 0.999 | ≥ 0.99 | ≥ 0.98 | ≥ 0.95 | ≥ 0.90 | below |
> |---|---|---|---|---|---|---|
> | **Points** | **35** | 25 | 20 | 15 | 10 | **0** |
>
> So the last 0.008 of overlap is worth ten points, and below 0.90 the category
> scores nothing at all.

> **One note on the numbers that follow.** The machine code tier, worth 25, sat
> near zero for the whole project, so during development we tracked the other
> **75 points**: sequence, workpiece, and tools. Every score on slides 4 through
> 7 is out of that 75. Slide 9 gives all 100. Both are measured on parts no model
> was trained on.

**Say:** The scoring is banded, not continuous, and that shaped what we worked
on. Below ninety percent overlap the workpiece category scores zero, so early on
getting the operation count right mattered far more than any geometry.

*Footnote on the slide, small: the two fractions are ours. The rubric's tool
tables do not sum to their stated section budgets, so we score them as printed
then rescale, and we have asked the organizers which reading they intend.*

---

## Slide 4: Baseline and the first diagnostic

**On screen**

> ITERATIONS 0 AND 1
>
> ## Build the worst complete thing, then attribute the error

> First end-to-end submission: **21.97 / 100**. Every format valid, deliberately
> unambitious. Its job was to expose where the error lives.

> Then we counted, over 200 parts, how many of each **operation type** we
> predicted against how many actually occur.

| Operation type | We predicted | Truth | Off by |
|---|---:|---:|---:|
| **Drilling** | 769 | 580 | **+189** |
| Spot drilling | 249 | 279 | &minus;30 |
| Boring | **0** | 19 | &minus;19 |
| Hole milling | 69 | 85 | &minus;16 |
| Pocket floors and walls | 362 | 352 | +10 |
| Chamfer contours | 419 | 419 | **0** |
| **Total** | 1,969 | 1,823 | **+146** |

> One row exceeds the entire net error: we gave two drilling passes to holes that
> need one. Chamfers were already exact, 419 of 419. And we emitted **no boring
> operations at all**, which is the thread slide 5 picks up.
>
> *Deep-hole drilling is the seventh type. It does not appear here because it
> occurs in neither our output nor the truth for these 200 parts.*
>
> **21.97 &rarr; 28.07** of the 75 points in play

**Say:** We built the worst thing that could produce all four outputs, on
purpose, and it scored twenty two. Then rather than asking which parts scored
badly, we asked which operation type was wrong. That points at one rule instead
of a whole pipeline.

---

## Slide 5: Where learning beat rules

**On screen**

> ITERATION 2
>
> ## Gradient boosting, on features the rules could not separate

> An additive ensemble of shallow trees, each fitted to the gradient of the loss
> left by the ones before it:
>
> $$F_M(x)=F_0(x)+\nu\sum_{m=1}^{M}h_m(x),\qquad
>   h_m\approx-\left[\frac{\partial L(y,F)}{\partial F}\right]_{F=F_{m-1}}$$
>
> Inputs are geometry only. Output is one of fifteen operation chains.
>
> $$x\in\mathbb{R}^{10}\;\longrightarrow\;c\in\mathcal{C},\quad|\mathcal{C}|=15$$

> Four decisions have to be made. **Three are per feature. One is per part.**
> For each we asked the same question: can a model beat our rule? Accuracy is on
> parts never trained on.

| For every **feature**, decide | Rule | Model | Which one we kept |
|---|---:|---:|---|
| Chamfer &rarr; its one operation | exact | not attempted | we use the rule |
| Pocket &rarr; its operations | **0.865** | 0.859 | we use the rule |
| Hole &rarr; its chain of operations | 0.374 | **0.970** | **we use the model** |

| For the **part** as a whole, decide | Rule | Model | Which one we kept |
|---|---:|---:|---|
| What order the tools run in | 0.349 | **0.896** | **we use the model** |

> The model is what finally emitted boring and deep-hole drilling: they only
> occur inside particular chains, and no threshold rule we wrote found them.
>
> **28.07 &rarr; 40.75** of 75

**Say:** Same test for every feature type. Two rules won and two models won, and
we kept whichever won. A hole is the hard case because it can take up to five
operations in sequence; a chamfer only ever takes one.

---

## Slide 6: What we trained on, and how we knew a change was real

This slide exists because we nearly threw away our best change by measuring it
badly. Tell it as that story, not as a statistics lesson. The data strip at the
top is read in one sentence and then left alone.

**On screen, a strip across the top, quiet**

| The corpus | The split |
|---|---|
| **10,000 parts, 91,702 operations, 5.2 GB.** We use every part. Training tables hold **22,500 holes**, matched to operations by where the tool actually goes, 98.6% matched | By **part**, never by feature, because holes on one part share a block and a tool set. Parts 0 to 7,999 train. Parts **8,000 and above are never touched**, and 400 of those are the test bench behind every number in this deck |

> Inputs are the boundary representation only. **We deliberately read none of the
> 50,000 rendered images**: we measured what they could add and it was nothing the
> geometry does not already carry. We also once trained on 20 percent of the
> corpus, and extracting all of it lifted hole chain accuracy from **0.948 to
> 0.970** with no change to the model.

**On screen, middle, the problem**

> HOW WE TESTED EVERY CHANGE
>
> ## Parts differ far more than our changes do

> Across 150 parts the score swings by about **21 points**, just because some
> parts are simple and some are not. A change worth 8 points is invisible against
> that. So comparing two averages tells you almost nothing.

**On screen, bottom half, the fix and the proof**

> **So we never compare averages.** We score **the same part** both ways and
> keep only the difference. The part's difficulty cancels out, because it is in
> both numbers.

```
   part 41    old ●────────────► new ●     +6
   part 42    old ●──────► new ●           +3
   part 43    old ●───────────► new ●      +5
                                            ...
                      average difference:  +8.14
                      and we resample it:  [+5.3, +11.1]
```

| The hole classifier from slide 5, measured two ways | Answer we got |
|---|---|
| 20 parts, averages compared | +3.31 |
| 150 parts, same part before and after | **+8.14**, 95% sure it lies in [+5.3, +11.1] |

*This is the classifier on its own. Slide 5's jump from 28.07 to 40.75 is larger
because it bundles several changes made in that iteration.*

> The sloppy measurement understated our best change by more than half. The
> interval stays above zero, so we kept it. A change whose interval contains zero
> gets dropped, and several did: rounding pocket corners moved overlap from
> 0.8856 to 0.8857, which is nothing.

**On screen, small print at the foot**

> $$\delta_i=s_i^{\text{new}}-s_i^{\text{old}},\qquad
>   \mathrm{CI}_{95}=\Big[q_{2.5}(\bar\delta^*),\;q_{97.5}(\bar\delta^*)\Big]$$
>
> Resample the per-part differences 5,000 times with replacement, take the mean
> each time, keep the middle 95%. No bell curve is assumed, because the rubric's
> banding from slide 3 makes per-part scores lumpy rather than smooth. The
> standard is now 400 held-out parts.

> And one rule that decides what counts as winning: a model is always compared
> against **the hand-written rule we already had**, never against chance. Beating
> chance proves nothing when a rule already works. Training refuses to save a
> model that does not clear its rule.

*Design note: this slide carries the most content in the deck. The corpus strip
and the equation are both reference material, set small. What the audience should
actually look at is the paired-dots diagram and the two-row table under it. If it
feels crowded when built, cut the equation to a backup slide before cutting
anything else.*

**Say:** We nearly undersold our single best change by half, because we first
measured it on twenty parts by comparing averages. Parts vary so much that the
variation swamped the effect. Scoring the same part before and after cancels the
part out, and then the only question left is whether the average difference stays
above zero when you resample it. If it does, we keep the change. If it crosses
zero, we drop it, and several went that way.

---

## Slide 7: When the model failed

**On screen**

> ITERATION 3
>
> ## The pocket model lost. That was the clue.

> A classifier found no signal in pocket geometry. We treated that as evidence
> about our inputs, not about pockets.
>
> Two variables shared a name. Most pocket floors were discarded before anything
> saw them.

| | Before | After |
|---|---|---|
| Pocket floors found correctly | 68% | **99%** |
| Score, of 75 | 40.75 | **49.47** |

> Recognition is now checked continuously against the dataset paper's published
> statistics. Blind hole share: ours **0.502**, published **0.502**.

**On screen, lower band, smaller: the same lesson a second time**

> Then chamfer faces reported heights **taller than the block they sit on**, and
> pocket clearing paths swept **11 times** the volume they remove. Same kind of
> cause: we were reading the STEP file's construction points as if they were
> points on the part. Counting only points reached through a vertex fixes both.
>
> **49.5 &rarr; 51.4 of 75**, which is where slide 9 picks up.

**Say:** One line of code, nearly nine points, and it looked like a modelling
problem for hours. Then a second parsing bug gave us another two. When a model
cannot find a signal, suspect the data before the theory.

---

## Slide 8: The geometry engine

**On screen**

> GEOMETRY
>
> ## Two deliverables, one exact engine

> The rubric scores a tool path against the workpiece difference. That is an
> identity, so one engine serves both:
>
> $$V_k=\mathrm{IPW}_{k-1}\setminus \mathrm{IPW}_k
>   \;\;\equiv\;\;\text{volume swept by operation }k$$
>
> Every cutter is a **convex** solid of revolution, so a sweep along a segment is
> exact, not sampled:
>
> $$K\oplus[a,b]=\mathrm{conv}\big((K+a)\cup(K+b)\big)$$

| | Tool placements | Result |
|---|---|---|
| Sampling along the path | ~4,944 | approximate |
| **One hull per move** | **272** | **exact** |

> Validated against ground truth: **IoU 0.99997**.

**Say:** Because every cutter is convex, the swept region is exactly the convex
hull of the tool at both ends of a move. Fewer operations and an exact answer.

---

## Slide 9: Where it landed

**On screen**

> RESULTS &middot; 400 parts never seen in training

| Rubric category | Available | Ours | Share |
|---|---:|---:|---:|
| Easy, operation sequence | 20 | **17.5** | **88%** |
| Medium, in-process workpiece | 35 | 23.0 | 66% |
| Hard, tool selection | 20 | 10.9 | 55% |
| *Working score tracked in this deck* | *75* | ***51.4*** | *69%* |
| Hard, machine code paths | 25 | **0.8** | **3%** |
| **Total** | **100** | **52.2** | **52%** |

> The three tiers we worked on went **21.97 &rarr; 51.4 of 75**. The fourth tier
> is the flat line second from the bottom, and it is slide 10.
>
> All 120 test artifacts pass the official validator. 96 tests. Same input, same
> output, every run.

**Say:** Easy is near its practical limit. Medium has a ceiling we can name. Tool
selection is respectable. And then there is that last row, which is the whole
reason we have a tenth slide.

---

## Slide 10: The gap

**On screen**

> WHAT IS LEFT
>
> ## The scorer works. The generator does not.

| Our swept-volume engine, scoring | Result |
|---|---|
| Ground truth machine code | **23.5 / 25** |
| Machine code we generate | **0.8 / 25** |

> The geometry is validated. What is missing is generation: pocket area clearing
> from true outlines, and chamfer paths offset so the cutter's conical flank sits
> on the chamfer surface.
>
> Medium is capped by information the input does not contain. This is capped only
> by work.

**Say:** Twenty four of our missing points sit here, we know what each one needs,
and none of it is research.

---

## Notation used, in case a judge asks

| Symbol | Meaning |
|---|---|
| $P,G$ | predicted and ground-truth sequence or solid |
| $d_L$ | Levenshtein edit distance |
| $\mathrm{vol}(\cdot)$ | volume of a solid |
| $\mathrm{IPW}_k$ | in-process workpiece after operation $k$ |
| $V_k$ | material removed by operation $k$ |
| $K$ | the cutting tool as a solid |
| $\oplus$ | Minkowski sum |
| $\nu$ | learning rate |
| $\bar\delta^*$ | bootstrap resampled mean paired difference |
| $\beta_\bullet$ | a rubric band, mapping a metric onto points as a step function |
| $e_k$ | relative tool diameter error on operation $k$ |

---

## The arc

| Slides | Doing |
|---|---|
| 1 | Problem, and that ground truth is deterministic |
| 2 | **What the system is**, in three boxes |
| 3 | The grader, with the metrics defined |
| 4 to 5 | Baseline, error attribution, then where learning won |
| 6 | **Training and validation protocol** |
| 7 | Third diagnostic: the bug, found because a model failed |
| 8 | **The geometry engine**, with the identity and the hull result |
| 9 to 10 | Result, and the honest remaining gap |

Equations sit where they carry meaning: metrics on slide 3, the model on slide 5,
the validation protocol on slide 6, the geometry on slide 8.

### Vocabulary, kept consistent throughout

Two words do all the work and the deck must not blur them. A **feature** is
geometry we recognise in the part. An **operation** is something the machine
does. One feature usually needs several operations, and slide 2 states the
mapping before any later slide relies on it.

| Word | Means | Count | Appears on |
|---|---|---:|---|
| feature | hole, pocket, chamfer | 3 | slides 2, 5, 7 |
| operation | what the machine does, once | 7 | slides 2, 4 |
| operation chain | the ordered operations one feature needs | 15 seen | slides 2, 5 |
| part | the whole workpiece, which is not a feature | 1 | slides 5, 6 |

Three rules follow from that table and the deck must not break them.

**Every operation is named the way the dataset names it.** There is no operation
called "chamfer milling". A chamfer is machined by `AREA_MILL` under
`mill_contour`, holding a chamfer mill. Chamfer is the tool, contour milling is
the operation. An earlier draft invented "chamfer milling" and it appeared on two
slides.

**Counts must reconcile.** Slide 2 promises seven operation types, so slide 4
must not quietly show four. It now shows six, with a line saying the seventh,
deep-hole drilling, occurs in neither our output nor the truth for that sample.

**A part is not a feature.** Slide 5 makes four decisions, but only three are per
feature. Ordering the tool blocks is a decision about the whole part, and it sits
in its own table so it cannot be misread as a fourth feature type.

Earlier drafts slipped between the two, listing operations on one slide and
features on the next without saying they were different things. Slide 4 is now
explicitly about operation types, slide 5 explicitly about feature types, and
both use the names introduced on slide 2.

### Two scales, named rather than blurred

The deck previously quoted every figure as "out of 100". That was wrong, and it
is worth being precise because a judge will add the numbers up.

| Number | Scale | What it covers |
|---|---|---|
| 21.97, 28.07, 40.75, 49.47, 51.4 | **of 75** | sequence, workpiece, tools |
| **52.2** | **of 100** | all four tiers, including machine code |

The 75-point working score is not a convenience. The machine code tier sat near
0.8 out of 25 for the entire project, so including it would have added a constant
to every measurement and masked the changes we were trying to detect. Slide 3
states this before the first number appears, and slide 9 reconciles both scales
in one table.

**Rendering note:** the equations need a maths renderer. If the deck is HTML, that
means KaTeX or MathJax, which are external scripts and may be blocked depending on
where it is hosted. The safe fallback is to render each equation once as an inline
SVG or an image. Tell me which and I will build accordingly.

**Still off the deck:** the estimated test score near 48 out of 100, because
explaining why it sits below the held-out figure needs a sentence there is no room
for. It is in the written document.
