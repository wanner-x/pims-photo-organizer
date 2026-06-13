# Dual-Engine Auto Archive Design

**Date:** 2026-06-13

**Project:** PIMS V1

**Status:** Approved design draft

## Goal

Transform PIMS from a review-first organizer into a dual-engine archive system that:

- uses both rules and AI to produce archive plans
- auto-executes normal archive moves immediately
- keeps `R18`, quarantine, delete, and destructive actions under strict review gates
- records every decision and move in a rollback-friendly ledger
- shifts the UI from approval-heavy workflow to anomaly handling and quality control

## Product Direction

The target operating mode is:

- aggressive auto-archiving for ordinary series organization
- zero tolerance for false-positive `R18`, quarantine, or delete actions
- immediate execution after planning for ordinary archive moves
- rules and AI both produce full plans, with a strategy layer choosing the final plan

This changes the system from:

- "AI suggests, human approves most things"

to:

- "system plans and executes by default, human handles exceptions"

## Why The Current Model Is Not Enough

The current project already has access to:

- full folder and file names
- parent directory hierarchy
- size and `P/V/MB/VOL` metadata embedded in names
- duplicate and similarity signals
- historical archive paths

That is enough information to build a deterministic large-scale archive strategy for a large share of candidates. Requiring broad manual approval for ordinary archive moves adds friction without improving the right risks.

The current AI usage is also misplaced. AI should not primarily act as a path author that waits for blanket approval. It should instead:

- generate a full archive plan
- explain the plan
- detect rule blind spots
- detect conflict and risk
- audit rule outputs

while high-risk execution permissions remain constrained.

## Design Principles

1. Ordinary archive moves should be automatic unless there is a clear reason to stop.
2. `R18`, quarantine, delete, overwrite, and cross-category structural changes must remain conservative.
3. Every decision must be explainable after the fact.
4. Every ordinary move must be reversible.
5. Historical archive consistency matters more than one-off naming creativity.
6. AI is a decision engine, not just a suggestion engine, but it is not allowed to authorize destructive actions.

## System Architecture

The redesigned archive flow has five core layers.

### 1. Rule Planner

The rule planner produces a complete archive plan from deterministic inputs:

- source root
- parent directory names
- known person, brand, studio, or project names
- folder metadata such as `VOL`, `EX`, `[43P4V234MB]`, `[86+1P]`
- historical archive matches
- current target directory existence and conflicts

It outputs:

- `category`
- `title`
- `archive_path`
- structured metadata
- confidence score
- explanation of matched rules
- detected risks

### 2. AI Planner

The AI planner receives the same candidate context and produces:

- `category`
- `title`
- `archive_path`
- plan summary
- semantic tags
- risk flags
- confidence score
- explanation

The AI planner has real influence over ordinary archive planning, but no authority to auto-approve destructive actions.

### 3. Decision Merger

The decision merger compares the rule plan and AI plan, calculates strategy scores, and selects a final plan.

It decides whether the candidate becomes:

- `auto_apply`
- `auto_apply_sampled`
- `manual_review`
- `blocked`

### 4. Safety Gate

The safety gate is a hard policy layer. It does not care whether the risk came from rules or AI. It blocks automation for:

- `R18` labeling
- quarantine moves
- delete actions
- overwrite or merge into conflicting existing directories
- cross-person or cross-brand top-level reclassification

### 5. Execution And Rollback Ledger

Every final decision and every file move must be written to a durable ledger before the system can claim successful automation.

This ledger enables:

- post-hoc explanation
- quality control sampling
- rollback
- failure recovery
- long-run model and rule calibration

## Decision Model

The dual-engine strategy should be explicit and score-based rather than vague.

### Scoring Dimensions

Each candidate receives:

- `rule_score`
- `ai_score`
- `risk_score`

#### Rule Score Inputs

- parent directory match quality
- known person or brand match quality
- folder metadata preservation
- historical archive pattern reuse
- path structure clarity
- target path validity

#### AI Score Inputs

- model confidence
- completeness of explanation
- agreement with known archive history
- semantic plausibility of title and category
- absence of unsupported generic naming

#### Risk Score Inputs

- `R18` suspicion
- directory conflict
- destructive action type
- cross-category move
- duplicate ambiguity
- history mismatch

### Decision Outcomes

#### Auto Apply

Immediately execute when any of these hold and no hard risk gate is triggered:

- rule and AI agree on `category` and `title`
- rule and AI agree on `category`, with only minor title formatting differences
- rule score is high, AI score is medium or high, and risk score is low
- candidate matches a stable historical archive pattern with low conflict

#### Auto Apply Sampled

Immediately execute, but enqueue for quality-control sampling:

- rule and AI agree on top-level category but differ on title semantics
- AI adds plausible tags or refinements while category remains stable
- candidate is a new person or brand with clear structural evidence

This is not a blocking state. It is a post-execution inspection state.

#### Manual Review

Require human review when:

- rule and AI disagree on top-level category
- `R18` is suspected
- quarantine or delete is proposed
- target path conflicts with existing archive contents
- cross-person, cross-brand, or cross-project migration is implied
- both planners are low-confidence

#### Blocked

Never auto-execute:

- delete actions
- quarantine of valuable originals without review
- automatic `R18` tagging from ordinary AI inference alone
- silent overwrite into inconsistent existing targets
- batch restructuring of mature top-level archive groups

## Data Model Changes

The current suggestion-oriented model is not enough for aggressive automation. The system needs decision-first records.

### Planning Record

Create a planning-level record for every finalized candidate decision.

Fields:

- `id`
- `candidate_id`
- `source_root`
- `rule_plan_json`
- `ai_plan_json`
- `final_plan_json`
- `decision_type`
- `rule_score`
- `ai_score`
- `risk_score`
- `decision_reason`
- `created_at`

Purpose:

- explain why a decision was made
- preserve both engine outputs
- support debugging and post-mortem analysis

### Execution Record

Create an execution-level record for each concrete file operation.

Fields:

- `id`
- `planning_record_id`
- `operation_type`
- `source_path`
- `target_path`
- `status`
- `started_at`
- `finished_at`
- `error_message`

Purpose:

- track whether execution happened
- track failure states
- support partial recovery and rollback

### Rollback Record

Create a rollback-level record for each reversal.

Fields:

- `id`
- `execution_record_id`
- `rollback_source_path`
- `rollback_target_path`
- `status`
- `operator`
- `reason`
- `created_at`

Purpose:

- support reversible automation
- support auditability

### Risk Event

Create an event table for anomaly and sampling signals.

Fields:

- `id`
- `planning_record_id`
- `event_type`
- `severity`
- `details_json`
- `resolved_at`

Purpose:

- feed the anomaly queue
- feed the sampling queue
- support model and rule calibration

## Execution Model

The candidate lifecycle becomes:

1. build candidate
2. run rule planner
3. run AI planner
4. merge decisions
5. write planning record
6. if result is `auto_apply` or `auto_apply_sampled`, execute immediately
7. write execution records
8. if needed, create risk events
9. if failure happens, mark failed and route into rollback or anomaly handling
10. if result is `manual_review` or `blocked`, do not execute

The key design change is that the primary object is no longer the AI suggestion. The primary object is the finalized decision record.

## Safety Policy

The project should become more aggressive only for reversible ordinary archive moves.

### Allowed For Immediate Auto Execution

- ordinary archive moves into a non-conflicting archive path
- title normalization within stable category boundaries
- consistent reuse of established person, brand, or project structure

### Not Allowed For Immediate Auto Execution

- delete
- quarantine
- `R18` labeling based on uncertain inference
- overwrite into conflicting existing directories
- structural top-level category rewrites

### Required Safeguards For Ordinary Auto Moves

- record source and target before move
- verify target conflict status before move
- use reversible move semantics
- preserve per-file traceability for batch moves
- expose rollback as a first-class operation

## UI Redesign

The review UI should stop acting as a mass approval console and become an anomaly and tracking console.

### Primary Panels

#### Auto Execution Overview

Show:

- recent auto-archive counts
- success rate
- failure count
- rollback count
- sample queue count

This becomes the default operational dashboard.

#### Anomaly Queue

Only show items that actually require attention:

- `R18` suspected
- quarantine or delete pending review
- cross-category conflicts
- existing-path conflicts
- execution failures
- rollback failures

#### Sampling Queue

Show items that auto-executed successfully but were flagged for quality control sampling.

This queue exists to catch drift, not to reintroduce full pre-approval workflow.

#### Execution And Rollback Ledger

Show:

- decision reason
- source and target paths
- rule score
- AI score
- risk score
- execution status
- rollback controls

## Operating Modes

The system should explicitly support three modes.

### Full Auto Archive Mode

Used for ordinary archive planning and immediate move execution.

Characteristics:

- dual-engine planning
- strategy merge
- immediate reversible execution
- automatic sampling where needed

### High-Risk Review Mode

Used for:

- `R18`
- quarantine
- delete
- overwrite conflict
- structural category conflict

Characteristics:

- planners still generate proposals
- system does not auto-execute
- anomaly queue requires explicit human action

### Learning And Calibration Mode

Used to improve long-run quality by reviewing:

- rollback patterns
- anomaly causes
- sample inspection results
- frequent rule mismatches
- AI drift cases

This mode closes the loop between operations and planner quality.

## Role Of AI In The New System

AI should become stronger, but in the right place.

### AI Should Do

- produce a full archive plan
- explain why the plan makes sense
- detect rule blind spots
- identify likely naming, topic, or category issues
- detect possible risk states
- act as a semantic auditor for rule output

### AI Should Not Do

- auto-approve `R18`
- auto-approve delete
- auto-approve quarantine of valuable originals
- auto-overwrite conflicting targets
- auto-rewrite stable top-level archive structures on its own

In short:

- AI should be strong in planning and review
- AI should not own high-risk execution authority

## Migration Strategy

The safest implementation path is incremental rather than a single rewrite.

### Phase A: Introduce Rule Planner And Decision Records

- add deterministic archive planning service
- add planning record model
- keep current review flow available

### Phase B: Add Decision Merger And Risk Gate

- generate rule and AI plans in parallel
- compute decision outcomes
- route only risky cases to review

### Phase C: Add Immediate Auto Execution For Ordinary Moves

- execute low-risk archive moves automatically
- write execution ledger
- keep rollback disabled only for destructive operations

### Phase D: Redesign Review UI

- replace approval-heavy panels with anomaly and ledger panels
- add sampling queue
- add rollback controls

### Phase E: Calibration Loop

- capture sample outcomes
- capture rollback reasons
- refine rule weights and AI prompts or policies

## Testing Strategy

The implementation should be validated with strong regression coverage.

### Rule Planner Tests

Cover at minimum:

- `雪琪SAMA`
- `紧急企划`
- `IMISS爱蜜社`
- metadata preservation such as `[46P208MB]`, `[43P4V234MB]`, `[86+1P]`
- top-level category preservation

### Decision Merger Tests

Cover:

- rule and AI agreement
- same category with title differences
- low-risk auto apply
- conflict routing
- hard blocking for high-risk actions

### Execution Ledger Tests

Cover:

- planning record creation
- execution record creation
- failure capture
- rollback record creation

### UI And API Tests

Cover:

- anomaly queue API
- sampling queue API
- ledger API
- rollback action API
- overview metrics

## Open Non-Goals

This design does not attempt to solve:

- multi-user workflow
- public network deployment
- full visual NSFW recognition design details
- PostgreSQL migration strategy beyond compatibility needs

Those may be addressed later, but they are not required for this architecture shift.

## Summary

The approved direction is:

- aggressive auto-archiving for ordinary series moves
- strict review-only handling for `R18`, quarantine, delete, and conflict-heavy cases
- dual-engine planning with explicit strategy merge
- immediate execution backed by durable decision and rollback ledgers
- UI transformation from approval center to anomaly and traceability center

This is the correct shape for a 10T-scale archive project that already has rich filename and path information and should use AI as a strong planner without giving it destructive authority.
