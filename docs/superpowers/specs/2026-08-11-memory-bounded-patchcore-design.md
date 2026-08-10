# Memory-Bounded PatchCore Research Design

**Status:** Approved for autonomous execution

## Context and objective

The public-only 640 x 640 `wallplugs` PatchCore seed-42 run at a 0.10
coreset ratio improved AU-PRO by 0.0695 and pixel AUROC by 0.0166, but its
training peak reached 22,219 MiB and its artifact was 1,251,953,715 bytes.
Two later 640 replication attempts were interrupted during 187,519-center
K-center selection, and the 576 probe sustained severe degradation during
151,890-center selection. Repeating those contracts is neither safe nor
informative.

The objective is to determine whether the proven 640 localization benefit can
be retained with a substantially smaller PatchCore memory bank and bounded
K-center workload. This is public-only efficiency research. It cannot change
the frozen champion, official `PRIVATE-NO-GO` verdict, or submission state.

## Alternatives considered

1. **Fixed 640 coreset-ratio ladder — selected.** Probe ratio 0.01, allow one
   predeclared 0.02 rescue only when 0.01 completes safely but misses quality,
   and replicate the first passing ratio. This directly tests whether the
   existing 640 gain survives a 5-10x smaller memory bank.
2. **576 at ratio 0.01.** This is geometrically safer but has no completed
   public-quality reference and would confound the resolution and coreset
   questions. It is excluded from this study.
3. **Custom streaming or partitioned K-center.** This could cap working memory
   more aggressively, but it changes the upstream algorithm and creates a much
   larger correctness surface. It is deferred unless the fixed-ratio ladder
   fails its resource contract.

## Fixed candidate ladder

The category is exactly `wallplugs`. Backbone, feature layers, neighbor count,
normalization, interpolation, batch size, precision, training data, public
evaluation geometry, metric implementation, and seed semantics remain frozen.
Candidate configs differ from the existing 640 config only in
`coreset_sampling_ratio`.

### Stage A: 0.01 seed-42 probe

- Run 640 x 640 PatchCore at seed 42 with coreset ratio exactly 0.01.
- Compare quality with the immutable matching 512 x 512 ratio-0.10 seed-42
  baseline and with the immutable 640 x 640 ratio-0.10 seed-42 efficiency
  reference.
- The probe advances when all of the following hold:
  - AU-PRO delta versus 512 is at least +0.03;
  - pixel AUROC delta versus 512 is non-negative;
  - image AUROC delta versus 512 is no worse than -0.05;
  - AU-PRO, pixel AUROC, and image AUROC deltas versus the 640 reference are no
    worse than -0.02, -0.005, and -0.01 respectively;
  - public GPU p95 latency is at most 150 ms;
  - artifact size is at most 200 MiB;
  - per-image failure rate is zero; and
  - the resource contract completes without a guard stop.

### Stage B: conditional 0.02 rescue

- Run this stage only when Stage A completes within the resource contract but
  misses at least one quality or efficiency threshold.
- Run 640 x 640 PatchCore at seed 42 with coreset ratio exactly 0.02.
- Apply the same quality thresholds, with artifact size capped at 350 MiB and
  public GPU p95 latency capped at 175 ms.
- Do not run Stage B when Stage A encounters a resource or integrity failure,
  because the larger coreset cannot improve that resource outcome.

The selected ratio is the first ratio in the fixed ladder that passes its
seed-42 gate. If neither passes, record `NO_QUALITY_PRESERVATION`. Do not invent
another ratio after observing the results.

### Stage C: conditional replication

- Only for the selected ratio, run seeds 17 and 2026 sequentially.
- Compare each candidate with its matching immutable 512 x 512 ratio-0.10
  baseline.
- The final result is `EFFICIENT_REPRODUCIBLE` only when all three runs
  complete, mean AU-PRO delta is at least +0.02, at least two AU-PRO deltas are
  positive, mean image AUROC delta is no worse than -0.04, no individual image
  AUROC delta is worse than -0.07, mean pixel AUROC delta is non-negative,
  every p95 latency is at most 175 ms, every artifact satisfies the selected
  ratio's cap, and every per-image failure rate is zero.
- A completed seed-42 gate followed by an adverse replication is
  `EFFICIENT_SEED42_ONLY`; any run-level resource failure is
  `RESOURCE_LIMIT_EXCEEDED`.

## Resource and process safety

Formal execution uses a unique external root
`D:\mvtec-ad2-memory-bounded-patchcore-20260811` and the existing exclusive
project GPU lease. Before acquiring the lease, require a clean committed tree,
verified dataset/config/reference hashes, at least 160 GiB free on `D:`, at
least 16 GiB available system memory, and no foreign CUDA compute workload.

The isolated subprocess executor samples health every 10 seconds and may stop
only its own child process. It records a resource stop after three consecutive
samples with available system memory below 4 GiB, GPU memory above 22,500 MiB,
or GPU temperature at or above 83 degrees Celsius. It also stops its own child
after 45 minutes for ratio 0.01 or 60 minutes for ratio 0.02. Graceful
termination receives 10 seconds before a forced child-only kill. A guard stop
releases the project lease, preserves sanitized evidence, and stops later
candidates; it never terminates or modifies another workload.

## Architecture and evidence

A focused research module will:

1. validate the two candidate configs against the frozen 640 reference;
2. build deterministic seed and ratio identities before execution;
3. reuse the existing `RunStore`, GPU lease, worker, and public evaluator;
4. add an optional, tested health guard to `SubprocessExecutor` without
   changing existing callers;
5. execute the fixed conditional ladder sequentially and resumably;
6. preserve checkpoints, logs, maps, predictions, and detailed records only in
   the external root; and
7. atomically write one canonical, sanitized aggregate report containing
   identities, metrics, deltas, duration, peak VRAM, artifact size, guard
   outcomes, selected ratio, and fixed verdict.

## Error handling and stopping rules

- A checksum, dataset, config, non-finite, shape, or reference mismatch fails
  closed and prevents GPU execution.
- A candidate failure remains visible and is never replaced or hidden.
- Retry only the existing supervisor's single batch-size OOM fallback when it
  is valid; never retry a deterministic guard stop or repeat the unsafe
  ratio-0.10 candidates.
- Resume only an identical run identity with valid artifacts.
- Stop for another GPU owner, corrupted prerequisites, repeated infrastructure
  failure, credentials, private evidence, or an external publication action.

## Testing and verification

Use test-driven development for config-difference guards, fixed candidate
ordering, conditional rescue, selected-ratio replication, verdict
recomputation, resource-guard debounce/timeout/child-only termination,
resumability, idempotent reporting, and sanitized-field rejection. Before
committing aggregate evidence, run focused research gates and the full exact-
HEAD release candidate clean export.

## Authorization boundaries

- Read only public training/calibration data and `test_public` evidence.
- Never read or derive decisions from private images, predictions, or metrics.
- Do not promote or modify a frozen champion in this study.
- Do not create a second MVTec submission.
- Do not push, tag, create a GitHub Release, deploy, or publish a model.
- Commit only code, tests, concise documentation, and reviewed sanitized
  aggregate evidence; all raw or large artifacts remain external.

Expected GPU time is 20-60 minutes when ratio 0.01 advances directly, 40-120
minutes when the 0.02 rescue runs, and up to three hours including conditional
replication and evaluation. Full release verification is primarily CPU, disk,
Docker, and browser work.
