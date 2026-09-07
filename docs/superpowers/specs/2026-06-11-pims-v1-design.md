# PIMS V1 Design

Date: 2026-06-11

## Overview

PIMS V1 is a photo organization system for a single user with a large mixed library spread across a PC and a NAS. The application runs on the PC, uses local compute and cache, and treats the NAS as the final archive destination.

The primary goal is not full AI understanding of every image. The primary goal is to safely converge a 10TB-scale library into a clean NAS archive through reviewable series suggestions, exact duplicate cleanup, and recoverable batch operations.

## Product Goals

- Consolidate scattered images from PC folders and NAS folders into a single review workflow.
- Archive the kept version to a clear NAS destination structure.
- Detect exact duplicates across PC and NAS and remove redundant copies only after user confirmation.
- Keep the user in control of every destructive action.
- Support long-running processing with interruption recovery.

## Non-Goals

V1 does not attempt to provide:

- Full-library AI scoring for every image
- Fully automatic deletion without user review
- Multi-user permissions
- Mobile or desktop packaging work
- Cloud sync
- Advanced person merge and split workflows
- Real-time global similar-image search engine

## Target Deployment

### Runtime Placement

- Application server runs on the PC
- Database runs on the PC
- Thumbnail cache and intermediate analysis cache live on the PC, preferably SSD-backed
- Final organized archive lives on the NAS
- Quarantine for deletions also lives on the NAS

### Supported Libraries

- Local libraries: folders physically on the PC
- NAS libraries: SMB/NFS mapped or mounted folders reachable from the PC

The system treats both as libraries with different execution behavior.

## Core User Outcome

The user should be able to:

1. Scan PC and NAS libraries into one system
2. See exact duplicates across both sides
3. Review candidate series instead of reviewing isolated files
4. Confirm which files should be archived to the NAS organized area
5. Approve deletion batches for redundant copies
6. Recover from interruption and continue from the last completed stage

## Design Principles

- Series-first organization: treat a set of related images as the main review unit
- Review before destruction: all deletions require batch confirmation
- Preserve then delete: deletion is allowed only after archive placement and verification succeed
- Rule-first grouping: deterministic grouping rules produce initial series candidates
- AI as enhancement: AI improves naming, labeling, and edge-case review rather than driving the whole pipeline
- Recoverable execution: every long-running stage must persist progress

## High-Level Workflow

1. Discover files from local and NAS libraries
2. Extract lightweight metadata
3. Generate thumbnails
4. Compute exact and similarity fingerprints
5. Produce series candidates using rule-based grouping
6. Surface review queues
7. Confirm archive targets on the NAS
8. Copy or move into final NAS structure
9. Verify result integrity
10. Generate deletion batches for redundant copies
11. Move approved deletions into quarantine
12. Purge quarantine after retention window

## Review Model

The product should compress a huge library into a manageable set of review tasks. The main review queues are:

- Pending series confirmation
- Exact duplicates
- Similar-image candidates
- Low-confidence exceptions
- Pending deletion batches

### Pending Series Confirmation

The review unit is a candidate series, not an individual image.

Each series card should show:

- Cover image
- Suggested title
- Image count
- Source library and source path
- Time range when available
- Size or resolution consistency summary
- Theme tags
- Confidence
- Suggested archive destination

Available actions:

- Confirm archive
- Rename then confirm
- Split candidate
- Merge into adjacent candidate
- Defer

### Exact Duplicates

Exact duplicates are high-confidence cleanup opportunities and should be presented separately from series review.

Only exact duplicates are eligible for batch deletion in V1.

### Similar Candidates

Similarity results are advisory only in V1. They help the user inspect near-duplicates or repeated downloads, but they do not enter the deletion flow automatically.

### Low-Confidence Exceptions

This queue captures cases such as:

- Weak series boundaries
- Missing time metadata
- Conflicting grouping signals
- AI labeling uncertainty

## Grouping Strategy

### Primary Rule-Based Signals

For the initial V1, candidate series are created using deterministic signals:

- Original folder boundary
- Filename continuity or shared prefix pattern
- Similar resolution or size profile
- Similar-image density
- Time proximity when trustworthy metadata exists

### Signal Priority for Network Photo Collections

For the user's target library type, priorities are:

1. Original folder structure
2. Filename pattern continuity
3. Resolution consistency
4. Similarity density
5. Time metadata as a weak signal

### AI Role in Grouping

AI should not perform open-ended full-library grouping. AI is used after basic candidates exist to:

- Suggest readable series names
- Add coarse theme labels
- Flag likely merge or split boundaries

## Person Recognition Strategy

Person recognition is important for retrieval but should not dominate grouping in V1.

### V1 Person Capabilities

- Detect faces on processed images
- Generate face embeddings
- Surface likely main person in a series when available
- Support filtering by person
- Allow manual naming of person entities

### Deferred Person Capabilities

- Large-scale manual merge and split of person clusters
- Full-library person curation workflows
- Complex threshold tuning tools

### Person Role in Product Logic

Person recognition serves two use cases:

- Help the user find related series
- Help validate whether adjacent series might belong together

It does not serve as the primary archive structure or the main grouping engine.

## AI Scope

### Keep in V1

- Series naming suggestions
- Coarse theme tags
- Series-level description or explanation

### Downscope in V1

- Full-image aesthetic scoring
- Fine-grained content taxonomy
- Global AI-first grouping of all files
- Author identification automation

The AI role is assistant, not judge.

## File Movement and Archive Rules

### Final Archive Center

The final kept copy should live on the NAS in a clear organized structure.

### Execution Semantics

- NAS source to NAS archive: move or rename is allowed
- Local source to NAS archive: archive through copy, then optionally delete the local redundant source only after explicit approval
- Cross-location destructive action must never happen before integrity verification

### Archive Verification

Before a source file can become deletion-eligible, the system must verify:

- Destination file exists
- Destination size matches expectation
- Hash verification passes for the archived copy

## Deletion and Quarantine Strategy

Deletion is the highest-risk workflow and must be staged.

### Deletion Eligibility

Deletion candidates may enter a review batch only when they are:

- Exact duplicates by hash
- Redundant source copies already archived to the NAS and verified successfully

Similar-image candidates never qualify for automatic deletion in V1.

### Deletion Flow

1. Generate deletion batch
2. User reviews batch
3. User approves batch
4. System moves files into NAS quarantine
5. Files remain recoverable during retention period
6. System purges quarantine after retention expiration

### Required Safety Rules

- No direct permanent deletion upon first confirmation
- No deletion before archive verification
- No deletion without a batch record
- Every deletion item must show the kept path and deletion reason

## Recovery and Long-Running Processing

Interruption recovery is a core V1 requirement.

### Recovery Requirements

- Scanning resumes without restarting the full library
- Per-file processing resumes from the last finished stage
- Archive execution resumes safely after interruption
- Deletion batches resume safely after interruption
- AI analysis results persist as soon as they complete

### Processing Philosophy

All heavy work must be stage-based and durable. The system should never rely on in-memory completion state for critical operations.

## Data Model

### Core Entities

- `libraries`
- `assets`
- `thumbnails`
- `faces`
- `persons`
- `tags`
- `asset_tags`
- `series_candidates`
- `series`
- `series_assets`
- `review_items`
- `scan_runs`
- `processing_tasks`
- `operation_batches`
- `operations`

### Key Modeling Decisions

- `assets` represents discovered files and their durable metadata
- `series_candidates` represents system-generated grouping proposals
- `series` represents user-confirmed archive entities
- `review_items` represents actionable user decisions
- `operation_batches` represents audit and recovery scope for archive or deletion actions

This separation prevents candidate suggestions, confirmed archive state, and execution logs from being mixed together.

## Processing Pipeline

### Lightweight Global Processing

Run across the full library:

- File discovery
- File size and mtime check
- Basic metadata extraction
- Thumbnail generation
- MD5 hashing
- pHash generation
- Basic grouping features

### Selective Heavy Processing

Run only where value is highest:

- Face detection and embeddings for series under review or high-value content
- Series naming AI
- Coarse theme labeling
- Exception-case AI review

This keeps first-pass processing feasible at 10TB scale.

## Technology Direction

- Python 3.11+
- FastAPI
- SQLite
- APScheduler or equivalent background scheduling
- Pillow, OpenCV, imagehash
- exiftool
- ffmpeg and ffprobe
- InsightFace for face processing

SQLite remains acceptable for V1 because the system is single-user and desktop-hosted, but it must be used with explicit indexing and durable task state.

## Milestones

### Milestone 1: Durable Indexing Base

- Library configuration
- File discovery
- SQLite schema
- Incremental scanning
- Recovery-safe task state
- Metadata extraction
- Thumbnail generation

### Milestone 2: Duplicate Foundations

- MD5 exact duplicate detection
- pHash generation
- Exact duplicate review queue
- Similar candidate review queue

### Milestone 3: Series Candidate Workflow

- Rule-based series candidate generation
- Series confirmation queue
- Confirmed archive entity creation

### Milestone 4: Archive Execution and Safety

- Copy or move to NAS archive
- Verification checks
- Operation batches
- Resume-safe execution

### Milestone 5: Deletion and Quarantine

- Deletion batch generation
- User batch review
- Move to quarantine
- Retention-based purge
- Restore from quarantine

### Milestone 6: AI and Person Enhancements

- Series naming suggestions
- Coarse theme labels
- Person detection and retrieval support

## Open Decisions

These items still need explicit implementation choices later, but they do not block design approval:

- Quarantine retention duration
- NAS archive directory naming template
- Face-processing trigger policy for cold data versus active review data
- Whether local-to-NAS archive confirmation should default to copy-only before deletion approval

## Final Definition

PIMS V1 is a PC-hosted, NAS-centered, interruption-safe photo organization system for a single large personal library. It prioritizes exact duplicate cleanup, rule-first series grouping, human-reviewed NAS archiving, and batch-confirmed deletion through quarantine. AI is used to improve retrieval and reduce review cost, not to replace user control.
