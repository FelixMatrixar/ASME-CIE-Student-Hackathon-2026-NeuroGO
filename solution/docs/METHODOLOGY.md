# Methodology: ASME CIE 2026 Hackathon, Problem 1

How the solution is built and, more importantly, **why it is built that way**.
Every claim here is backed by a measurement recorded in [FINDINGS.md](FINDINGS.md);
finding IDs are cited inline so nothing has to be taken on trust.

> Working note, gitignored like the rest of `docs/`. This is the seed of the
> public Round 2 methods write-up, not the write-up itself.

---

## 1. The problem

Convert a raw rectangular block into a finished part by removing material, and
predict the whole plan from the design geometry alone.

```mermaid
flowchart LR
    subgraph IN["Available at inference"]
        STP["BRep<br/>(.stp)"]
        PNG["5 rendered views<br/>(.png)"]
    end

    subgraph OUT["Required outputs"]
        E["<b>Easy</b> · 20 pts<br/>ordered (o1, o2) sequence"]
        M["<b>Medium</b> · 35 pts<br/>IPW mesh per operation"]
        T["<b>Hard A</b> · 20 pts<br/>tool type + diameter"]
        P["<b>Hard B</b> · 25 pts<br/>NC tool path"]
    end

    IN --> SOLVER(( )) --> OUT

    style IN fill:#e8f0fe,stroke:#4285f4
    style OUT fill:#e6f4ea,stroke:#34a853
    style SOLVER fill:#fff,stroke:#666
```

Ground truth comes from Siemens NX applying **deterministic rules**, so the task
is really *rule recovery* from 10,000 worked examples, 91,702 operations in all.

---

## 2. Architecture

```mermaid
flowchart TD
    STP["BRep (.stp)"] --> PARSE["<b>STEP reader</b><br/>planes + cylinders only<br/><i>F-030</i>"]
    PARSE --> FEAT["<b>Feature recognition</b><br/>holes · pockets · chamfers · blends<br/><i>F-031</i>"]

    FEAT --> HOLES["Holes"]
    FEAT --> POCKETS["Pockets"]
    FEAT --> CHAMFERS["Chamfers"]

    HOLES --> CLF["<b>Chain classifier</b><br/>gradient boosting<br/>0.970 accuracy<br/><i>F-047</i>"]
    POCKETS --> RULE1["Rule: 1 op per floor<br/><i>F-048</i>"]
    CHAMFERS --> RULE2["Rule: 1 AREA_MILL per face<br/>exact on 200/200 parts"]

    CLF --> PLAN["<b>Plan assembly</b><br/>group into tool blocks<br/><i>F-027</i>"]
    RULE1 --> PLAN
    RULE2 --> PLAN

    PLAN --> SEQ["easy JSON"]
    PLAN --> GEO["<b>Geometry engine</b><br/>removal solids"]
    GEO --> IPW["medium STL"]
    GEO --> NC["hard PTP"]
    PLAN --> TOOLS["hard tools JSON"]

    SEQ --> SCORE["<b>Local scorer</b><br/>reimplements the rubric"]
    IPW --> SCORE
    NC --> SCORE
    TOOLS --> SCORE

    style CLF fill:#fce8e6,stroke:#ea4335
    style SCORE fill:#fef7e0,stroke:#fbbc04
    style PARSE fill:#e8f0fe,stroke:#4285f4
```

---

## 3. The governing decision: measure before building

The first thing built was **not** a predictor but a local reimplementation of the
entire rubric: Levenshtein/F1, volumetric IoU, swept-volume comparison. Nothing
could be improved until it could be scored.

That ordering paid for itself immediately. Reimplementing the scorer is what
surfaced the facts that shaped everything after it:

| Finding | Consequence |
|---|---|
| `o1` is fully determined by `o2` (F-001) | Label space 21 → 7 before any model existed |
| `OTHER` validates but never occurs (F-002) | An attractive fallback that can only lose points |
| Medium IoU ≈ operation-count ratio, r = 0.999 (F-037) | Reprioritised the whole project |
| Rubric sub-tables don't sum to their budgets (F-006) | Logged for the organizers rather than guessed at |

---

## 4. Three structural insights

### 4.1 Medium and Hard-path are the same problem (F-005)

The rubric scores a tool path by comparing its swept volume against the boolean
difference of consecutive IPWs. That is an identity:

```mermaid
flowchart LR
    A["IPW(k-1)"] -->|"minus"| B["IPW(k)"]
    B --> C["removed volume"]
    D["tool path k"] -->|"sweep"| E["swept volume"]
    C -.->|"scored against"| E

    style C fill:#e6f4ea,stroke:#34a853
    style E fill:#e6f4ea,stroke:#34a853
```

So **60 of the 100 points share one geometry engine** rather than needing two.

### 4.2 Sequences are tool-blocked, not sorted (F-027)

Three hypotheses tested across all 10,000 parts:

| Hypothesis | Holds |
|---|---:|
| chamfers → pockets → holes | 54.45% |
| sorted by NX `Order Group` | 27.93% |
| **each tool in one contiguous block** | **70.55%** |

Cross-check: `tool_changes == blocks − 1` for **10,000 of 10,000 parts**. The plan
is tool-change minimisation under precedence constraints.

Because 97.65% of those blocks carry a single label (F-029), the easy tier's real
target is only **~4.5 (label, count) pairs**, not a sequence of up to 38 tokens.

### 4.3 Every cutting tool is convex (F-014)

For a convex body translated along a segment, the swept region is *exactly* the
convex hull of the body at both endpoints. So each move is computed exactly, not
sampled, 272 hulls instead of ~4,944 tool placements on a real operation.

---

## 5. Every decision the pipeline makes, and how each one is answered

Six distinct decisions turn recognised geometry into a plan. Each was decided
independently, by the same test: does a hand-built rule already separate the
groups; if not, does a classifier beat that rule on held-out parts. The six
land on three different kinds of answer, not one.

| # | Decision | Level | Answer | Evidence |
|---|---|---|---|---|
| 1 | Chamfer &rarr; operation | per feature | **rule**, exact | 419/419, F-026 |
| 2 | Pocket &rarr; operation(s) | per feature | **rule** (a model was tried and lost) | 0.859 model vs 0.865 rule, F-048 |
| 3 | Hole &rarr; operation chain | per feature | **model** | 0.970 vs 0.374 rule, F-047/F-051 |
| 4 | Tool diameter, given the operation | per operation | **rule**, mined ratios | e.g. 0.383, 0.779, 0.993, `predict.py` |
| 5 | Tool block order (whole part) | per part | **model** | 0.896 vs 0.349 fixed order, F-053 |
| 6 | Order within one tool block | per part | **unrecoverable** | every candidate &le; chance, F-029 |

Two feature types the recogniser finds are not decisions at all. Corner blends
are recognised (validated against the paper's statistics, F-031) but feed no
operation in the shipped predictor: nothing downstream currently reads them.
Recognition itself, upstream of all six decisions, is not a rule-versus-model
question either, it is exact geometric classification: a cylindrical face with
a closed boundary is a hole, a horizontal plane strictly inside the stock is a
pocket floor, a slanted plane is a chamfer. There is no ambiguity for a model or
a rule to resolve there.

```mermaid
flowchart TD
    STEP["STEP file"] --> REC

    subgraph REC["RECOGNISE: exact geometric classification, no decision"]
        direction LR
        HOLE["Hole<br/>cylindrical face,<br/>closed boundary"]
        PF["Pocket floor<br/>plane inside stock"]
        CHF["Chamfer<br/>slanted plane"]
        BLD["Corner blend<br/>partial cylinder"]
    end

    CHF --> T1{"1. operation?"}
    PF --> T2{"2. operations?"}
    HOLE --> T3{"3. chain?"}
    BLD -.->|"recognised, never<br/>used downstream"| NOOP(["no operation"])

    T1 --> R1["<b>RULE</b><br/>1 op / face, exact<br/>419 / 419 · F-026"]
    T2 --> R2["<b>RULE</b><br/>model tried, lost<br/>0.859 &lt; 0.865 · F-048"]
    T3 --> M1["<b>MODEL</b><br/>gradient boosting<br/>0.970 vs 0.374 · F-047"]

    R1 --> T4{"4. tool<br/>diameter?"}
    R2 --> T4
    M1 --> T4
    T4 --> R3["<b>RULE</b><br/>mined ratios<br/>0.383 / 0.779 / 0.993"]

    R3 --> T5{"5. block<br/>order, part-level?"}
    T5 --> M2["<b>MODEL</b><br/>gradient boosting<br/>0.896 vs 0.349 · F-053"]

    M2 --> T6{"6. order<br/>within a block?"}
    T6 --> U1["<b>UNRECOVERABLE</b><br/>every rule &le; chance<br/>F-029 / F-059"]

    U1 --> COMP["COMPUTE, exact:<br/>IPW mesh · swept volume · NC code"]

    style M1 fill:#fce8e6,stroke:#ea4335
    style M2 fill:#fce8e6,stroke:#ea4335
    style R1 fill:#e6f4ea,stroke:#34a853
    style R2 fill:#fef7e0,stroke:#fbbc04
    style R3 fill:#e6f4ea,stroke:#34a853
    style U1 fill:#f1f3f4,stroke:#5f6368
```

Reading the colours: green is a rule that is simply correct, nothing to gain by
learning it. Amber is a rule that survived because a model was actually built
and measured against it and lost, not because learning was never tried. Red is
a shipped model, chosen the same way, that won. Grey is neither: two different
families of candidate rule (F-029) sit at or below chance, and the classifier
built for pockets (F-048) shares the same upstream cause, so this is treated as
missing information rather than an unsolved rule.

Restated as the three answers this produced:

- **Holes.** Hand rules scored 0.374; a gradient-boosted classifier on the same
  features scored **0.970** on 6,757 holes from unseen parts (F-047, retrained
  on the full corpus per F-051; the original 2,042-part model scored 0.948
  against the same rules' 0.391, so more data measurably helped). The rules
  scored **0.000** on the single most common chain.
- **Pockets.** The same recipe scored **0.859 against the trivial rule's
  0.865**. The information is not in the recognised geometry. The training
  script's guard refused to save it.
- **Chamfers.** A one-line rule is already exact on 419/419 operations.
  Nothing to learn.

---

## 6. Discipline: what was rejected, and why

Six changes were implemented, measured, and **reverted**. They are documented at
the point of decision in the code so they are not re-derived.

| Change | Aggregate effect | Score effect | Verdict |
|---|---|---|---|
| Split wide-cornered pockets | net error −0.515 → **−0.015** | parts wrong 69 → **86** | reverted |
| `SPOT→DRILL→HOLE_MILLING` for all mid-band bores | closes a real 4.5% chain | medium 13.33 → **12.08** | reverted |
| Chamfer path along the edge | plausible tool motion | paths 1.72 → **1.25** | reverted |
| Rounded pocket corners | more faithful geometry | IoU 0.8856 → **0.8857** | kept, ~nil |
| Stricter floor merging | more defensible rule | **exactly neutral** | kept, ~nil |
| Pocket count classifier | none | worse than "always 1" | not shipped |

The recurring failure mode is worth naming: **a real but weak signal, applied to
every member of a group, fixes the population mean and breaks individual parts.**
Since medium IoU scores each part independently (F-037), matching a marginal
without separating the groups is a net loss.

Two of my own findings were also **refuted by later measurement** and are marked
superseded in place rather than deleted (F-032 on hole milling, F-036 on cut
policy), because the reasoning error is the instructive part.

---

## 7. Validation

```mermaid
flowchart LR
    subgraph L1["Unit"]
        U["96 tests<br/>closed-form geometry,<br/>not golden values"]
    end
    subgraph L2["Against published statistics"]
        S["blind share 0.502<br/>vs paper 0.502"]
    end
    subgraph L3["Against ground truth"]
        G["swept volume<br/>IoU 0.99997"]
    end
    subgraph L4["End to end"]
        E["held-out parts,<br/>official validator"]
    end
    L1 --> L2 --> L3 --> L4

    style L3 fill:#e6f4ea,stroke:#34a853
    style L4 fill:#e8f0fe,stroke:#4285f4
```

Two rules that caught real defects:

1. **Test against closed forms, not golden values.** A cylinder dragged a distance
   *L* must sweep `πr²h + 2rLh`. A test pinning current behaviour would have let a
   systematic error through.
2. **Split by part, never by hole.** Holes on one part share a block, a feature mix
   and a tool set. And in-sample scoring is quoted as such: parts 1–12 give 36.85,
   held-out parts give **31.22**, a 5.6-point optimism gap.

Stratified validation is what exposed three silent NC-parsing bugs (F-023) that
unit tests on synthetic paths never could: a `G4` dwell read as motion (6.4×
overcut), `G73` missing from the cycle set (33% of operations swept *nothing*),
and unsupported R-format arcs.

---

## 8. The released test set

Thirty parts, boundary representation and renders only. **No ground truth**, so
we cannot score ourselves on it. The organizers hold the labels.

```mermaid
flowchart LR
    subgraph T["Test_Data/ (30 parts)"]
        S1[".stp"]
        S2[".png x5"]
        S3["Note.txt<br/>(one part)"]
    end
    subgraph OUT["Submission written"]
        A["easy/<br/>30 JSON"]
        B["medium/<br/>398 STL"]
        C["hard/<br/>30 JSON"]
        D["hard_tool_path/<br/>398 PTP"]
    end
    S1 --> P["pipeline<br/>9.5 s total"] --> OUT
    S2 -.->|"never opened"| P
    OUT --> V["official validator<br/><b>120/120 valid</b>"]

    style V fill:#e6f4ea,stroke:#34a853
    style S2 stroke-dasharray: 4 4
```

**Two deliberate traps, both handled.**

`featured_part_22222` carries a note saying to infer it *without any images*, and
its folder contains none. We read only the boundary representation, so it
processed like every other part. It is also out of distribution: 16 holes against
a corpus maximum of 6, and a 32 mm block height against a corpus range of 50–150.

### The estimate needs correcting downward

Our held-out score is 51.40/75, but that average is weighted by easy parts. The
test set is harder:

| | Test set | Our held-out sample |
|---|---:|---:|
| Predicted operations per part | **13.27** | 9.21 |
| Holes per part | **3.77** | 2.29 |

Test parts carry **1.44×** the operations. And our score falls with complexity
(correlation −0.329):

| Predicted operations | Held-out parts | Mean score of 75 |
|---|---:|---:|
| ≤ 8 | 196 | **56.84** |
| 9–13 | 134 | 47.35 |
| 14–20 | 60 | 43.29 |
| > 20 | 10 | 47.86 |

Reweighting our held-out results to the test set's actual complexity mix:

```mermaid
flowchart LR
    A["51.40 / 75<br/>unweighted held-out"] -->|"reweight to<br/>test complexity"| B["47.69 / 75<br/>−3.71"]
    B -->|"add tool paths<br/>~0.8 / 25"| C["≈ 48 / 100<br/><b>test-set estimate</b>"]

    style C fill:#fef7e0,stroke:#fbbc04
```

So **48 out of 100 is the honest expectation**, not the 52 our unweighted
held-out figure suggests. Quoting the higher number would have been flattering
ourselves by about four points.

---

## 9. Where it stands

**51.40 / 75 on 400 provably-unseen parts**, all four submission formats passing
the official validator.

By the rubric's own three categories, Hard being 45 points split into tool
selection (20) and tool path geometry (25):

| Rubric category | Score | Share | What gates it now |
|---|---:|---:|---|
| Easy | **17.41 / 20** | 87% | near its practical limit |
| Medium | 23.02 / 35 | 66% | within-block ordering, not recoverable (F-059) |
| **Hard** | **11.76 / 45** | **26%** | see the split below |
| ├ tool selection | 10.96 / 20 | 55% | diameter only; *type is 100% correct* |
| └ tool path geometry | ~0.8 / 25 | 3% | generator inadequate, **engine is fine** |

Nearly all our missing points sit in one rubric category.

That last row is still the sharpest result in the project: the swept-volume
engine scores **≈23.5/25 on ground-truth paths** (F-021) and near zero on the
paths we generate (F-042). The geometry is solved; the generation is not.

### Score progression

```mermaid
flowchart LR
    A["21.97<br/>first baseline"] --> B["28.07<br/>count fixes"]
    B --> C["31.22<br/>held out, honest"]
    C --> D["40.75<br/>block ordering"]
    D --> E["49.47<br/>shadowed variable"]
    E --> F["51.40 / 75<br/><b>current</b>"]
    F --> G["≈ 48 / 100<br/>test-set estimate"]

    style F fill:#e6f4ea,stroke:#34a853
    style G fill:#fef7e0,stroke:#fbbc04
```

The step from 31.22 to 40.75 is the learned block-order model. The step to 49.47
is a single shadowed variable in the feature recogniser, which had been costing
8.72 points while looking like a modelling problem.

### Two ceilings we can name

**Medium** is bounded near 23 by an ordering the input does not contain. We cut
the right material and cut it in the wrong order: the finished part reaches IoU
0.9965 with 67.5% of parts above the top band, while the mean across indices is
0.9909 with 31.4% above it. Family order is 95% correct and tool-block order is
irrelevant, so the residual is which individual feature comes first inside a
single-tool block, and F-029 showed every candidate rule for that sits at or
below chance.

**Paths** are bounded only by work not yet done, which makes them the opposite
case and the obvious next target.
