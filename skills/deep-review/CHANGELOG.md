# Changelog

All notable changes to the Deep Review plugin are documented in this file. Releases follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.1.0] - 2026-08-07

### Added

- Verified POSIX and PowerShell release installers with deterministic client and
  scope mapping, checksum enforcement, and transactional updates.
- Durable, version-addressable release packages, checksums, and installer assets
  published from protected tags to GitLab Releases.
- Direct release download, checksum, installation, update, and offline instructions,
  backed by one versioned contract for client destinations and release assets.
- A built-in C# language reviewer for compiled C#, C# scripts, and C# regions in
  Razor files, with package-owned generated-output exclusions and eight configurable
  semantic rules covering nullability, asynchronous tasks, cancellation, resource
  lifetimes, and equality contracts.
- Resource-bounded cross-chunk synthesis with credential-redacted handoffs, exact
  coverage validation, fail-closed aggregation, synthesis-aware cache identities,
  and fresh final-guard reruns.
- Structural fact-field credential rejection, orchestrator-assigned chunk-local
  fact identities, provenance-checked synthesized additions, deterministic
  checklist-action consolidation, and reusable synthesis evidence attestations.
- Fact locations bound to evidence observed by their originating chunk and
  duplicate-handoff rejection for synthesized cache identities.
- Side-aware fact locations for both target changes and base-side deletions.
- Head-side display anchors for side-less H/M/L and checklist output locations.
- Explicit fail-closed synthesis outcomes for deletion-only relationships without
  a safe head-side display anchor.

## [1.0.0] - 2026-07-22

### Added

- Initial stable release with Claude marketplace packaging metadata.
- Review scopes for local changes, Git references and ranges, repository paths, GitHub pull requests, and GitLab merge requests.
- Configurable correctness, security, architecture, simplification, documentation, CI, project-checklist, and language-semantic reviewers.
- Bounded prompt planning, credential-safe result processing, and persistent nonblocking-result reuse.
