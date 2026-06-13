# R18 Visual Review Design

## Goal

Add a real series-level R18 review pipeline that can inspect sampled media, persist its findings, expose them in review surfaces, and block aggressive auto-archive when visual risk is high.

This increment must support two trigger modes:

- manual re-run from CLI or review API
- optional automatic sampling inside `run-safe-workflow`

The architecture must support two moderation tiers:

- local coarse screening implemented now
- cloud recheck hook points reserved for a later increment

## Why This Exists

The current system only carries `r18_label`, `r18_confidence`, and `r18_reason` through the AI naming flow. That is useful for text-driven suspicion, but it is not real visual review. The result is that:

- obvious adult risk can be missed if the folder name is clean
- the archive decision engine has no visual signal to merge
- the review UI cannot distinguish text suspicion from image-derived suspicion

The next useful slice is not a full vision platform. It is a bounded, auditable pipeline that samples a series, runs a local coarse detector, records what happened, and feeds a series-level risk summary back into review and auto-archive decisions.

## Scope

This increment includes:

- series media sampling for images
- local coarse visual moderation implementation
- a provider abstraction for future cloud rechecks
- persistence of moderation runs and sample results
- series-level review summary generation
- workflow integration behind an explicit flag/limit
- manual CLI/API re-run entrypoints
- minimal review UI visibility for the latest moderation state
- decision-engine merge so visual R18 risk forces manual review

This increment does not include:

- real cloud moderation provider integration
- video frame extraction
- `review_ui.py` file splitting
- a production-grade NSFW model bundle committed into the repo

## Constraints And Assumptions

### 1. Local first, but environment-safe

The current environment does not have `nudenet`, `onnxruntime`, `torch`, or `transformers` installed. The implementation therefore cannot hard-require those imports at module import time.

The local moderation layer must be environment-safe:

- if an optional stronger local provider is installed later, the system can use it
- if it is not installed, the system still runs via a built-in coarse heuristic detector

### 2. Conservative archive behavior remains mandatory

Visual moderation is allowed to escalate risk. It is not allowed to auto-clear risk. If a series is visually suspicious:

- dual-engine auto-archive must route it to `manual_review`
- no visual result may cause more aggressive archive execution than before

### 3. Auditability matters

This feature cannot be a transient score in memory only. The system needs durable run records so review and rollback decisions remain explainable.

## Architecture

The new path is:

`SeriesCandidate -> sample assets -> local moderation provider -> series summary -> persistent run records -> review payload -> archive decision merge`

### Components

#### A. Sampling layer

New service: `series_moderation_service.py`

Responsibilities:

- select candidate assets in stable order
- choose image samples only for now
- record unsupported media when a series is video-only or mixed with no sampled images

First-pass sampling rules:

- candidate assets are ordered by `SeriesCandidateAsset.sort_order`, then asset id
- only images are sampled in this increment
- sample count defaults to `7`
- if asset count is `<= sample limit`, sample all images
- otherwise sample front, middle, and tail positions with de-duplication

The output is a list of sampled asset records with enough information to inspect and persist.

#### B. Moderation provider layer

New service: `visual_moderation_service.py`

Core protocol:

- `VisualModerationClient`
- `moderate_image(path: Path) -> VisualModerationResult`

Implemented now:

- `HeuristicVisualModerationClient`

Reserved for later:

- `CloudVisualModerationClient`

Optional local stronger provider hook:

- `NudeNetVisualModerationClient`, loaded only if its dependency is available

Provider selection:

- `auto`: prefer optional stronger local provider if installed, otherwise heuristic
- `heuristic`: always use built-in heuristic
- `nudenet`: require optional provider, fail clearly if unavailable

#### C. Heuristic local detector

The built-in detector is intentionally described as coarse screening, not definitive classification.

It uses image statistics available from Pillow:

- convert to RGB / YCbCr
- estimate exposed-skin-like pixel ratio with bounded thresholds
- compute frame coverage and concentration
- derive a score `0.0 - 1.0`

This detector exists so the workflow is runnable now without shipping a heavy model. It is a fallback coarse screen and should be labeled as such in stored metadata.

#### D. Persistence layer

New models:

- `SeriesModerationRun`
- `SeriesModerationSample`

`SeriesModerationRun` stores:

- candidate id
- provider name
- mode (`manual` or `workflow`)
- status
- total samples
- flagged samples
- unsupported samples
- max score
- summary json
- created/updated timestamps

`SeriesModerationSample` stores:

- run id
- asset id
- sample path
- media kind
- sample status
- label
- score
- reason
- provider metadata json

This is enough to inspect what was sampled, what the local detector said, and why the final series decision was made.

#### E. Series-level summary layer

New service function:

- `review_series_r18(...)`

It aggregates sample results into a series summary:

- `r18_label`
- `r18_confidence`
- `r18_reason`
- `risk_flags`
- `sample_count`
- `positive_samples`
- `provider`
- `mode`

Decision rules for this increment:

- if any sample score `>= high_threshold`, mark `r18_label=true` and add `visual_r18_suspected`
- else if any sample score `>= review_threshold`, keep `r18_label=false` but add `visual_review_required`
- if no image samples were available, add `visual_scan_incomplete`
- if a source path already contains `R18`, keep that textual signal alongside visual results instead of replacing it

### Thresholds

New settings:

- `PIMS_R18_PROVIDER`
- `PIMS_R18_SAMPLE_LIMIT`
- `PIMS_R18_HIGH_THRESHOLD`
- `PIMS_R18_REVIEW_THRESHOLD`
- `PIMS_R18_SCAN_LIMIT`

Recommended defaults:

- provider: `auto`
- sample limit: `7`
- high threshold: `0.82`
- review threshold: `0.55`
- workflow scan limit: `20`

## Integration Points

### 1. Review candidate payloads

`list_series_review_candidates()` will be extended to include a `moderation` block from the latest run, even when no AI suggestion exists yet.

That avoids overloading `SeriesSuggestion` as the only place to surface R18 state.

### 2. Suggestion synchronization

When a moderation run completes, the latest `SeriesSuggestion` for the candidate should be updated if it exists:

- merge `R18` into `content_tags`
- update `r18_label`
- update `r18_confidence`
- update `r18_reason`

If no suggestion exists yet, the moderation state still remains visible through the new `moderation` block in review payloads.

### 3. Archive decision merge

`auto_archive_candidate()` must consult the latest completed moderation run before final decision selection.

Behavior:

- if moderation says `r18_label=true`, add `visual_r18_suspected`
- if moderation says review is required, add `visual_review_required`
- either condition keeps the candidate out of `auto_apply`

This preserves the conservative archive policy.

### 4. Workflow integration

`run-safe-workflow` gains optional visual review execution:

- bounded by `--r18-scan-limit`
- off when the limit is `0`
- runs after series candidates are built and before batch auto-archive

Workflow summary gets a new `r18_scan` section with counts:

- considered
- processed
- flagged
- review_required
- incomplete

### 5. Manual trigger entrypoints

Two manual entrypoints are required:

- CLI command to scan one candidate
- review API route to scan one candidate

This supports manual recheck when the user disagrees with a previous result or changes thresholds/provider settings.

## Review UI Behavior

This increment keeps `review_ui.py` as a single file but adds minimal visibility:

- show latest visual moderation provider
- show sample count and flagged sample count
- show whether the signal is text-based, visual, or both
- add a `重跑 R18 检测` action for each series card

This is intentionally minimal because the larger UI split is the next increment.

## Failure Handling

### Provider unavailable

If the requested provider is unavailable:

- manual route returns a clear `400`
- workflow records the run as failed and increments `failed`
- no candidate should be silently marked safe

### Unsupported media

Video-only series are not ignored. They are marked incomplete with an explicit reason, so the operator can still manually review them.

### Partial sample failures

If some sampled assets fail to open:

- successful samples still contribute to the summary
- the run is marked `completed_with_errors`
- the summary includes `visual_scan_incomplete`

## Testing Strategy

This increment must be proven with tests before code:

- schema tests for moderation tables
- service tests for image sampling selection
- service tests for heuristic moderation summary aggregation
- decision-service tests proving visual R18 blocks auto-archive
- workflow tests proving `r18_scan` runs before auto-archive
- review service tests exposing moderation payload
- review route tests for manual re-run
- CLI tests for manual scan and workflow output

## Follow-up Increment

After this slice is stable, the next increment will target review UI maintainability:

- split `review_ui.py`
- add filter controls for visual risk state
- add richer per-sample visual inspection UI
- then integrate real cloud moderation into the already-defined provider interface
