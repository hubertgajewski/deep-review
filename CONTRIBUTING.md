# Contributing

Contributions to Deep Review are welcome. Keep changes narrow, preserve the review-only safety model, and update the documentation that owns any behavior you change.

## Development environment

The package has no third-party Python runtime dependencies. Use Python 3.10 or 3.14 to match CI, plus Git for repository fixtures and scope-related work.

Run the complete test suite from the repository root:

```bash
python3 -m unittest discover -s tests -v
```

On Windows, use `py -3 -m unittest discover -s tests -v` when the Python launcher is installed instead of a `python3` command.

## Repository layout

- `skills/deep-review/SKILL.md` — skill entry point, workflow, and roster
- `skills/deep-review/references/` — normative runtime contracts, reviewer prompts, and language rules
- `skills/deep-review/scripts/` — deterministic support scripts
- `skills/deep-review/agents/` — client metadata
- `tests/` — package, contract, fixture, and cache tests
- `docs/` — user and maintainer guides

## Changing reviewers and rules

When adding or changing an agent:

1. Preserve the frontmatter and output contract described by the [agent contract](skills/deep-review/references/agent-contract.md).
2. Give each concern one clear owner; do not create duplicate findings across reviewers.
3. Keep built-in agents repository-neutral.
4. Do not use the reserved `x-` namespace for built-in agent names, domains, or language-rule namespaces. It belongs to consumer extensions.
5. Update the roster, orchestration rules, configuration documentation, and tests together.

When adding a language rule, use a complete namespaced rule ID, add its reference fragment, declare it in the language agent in dispatch order, and update the user-facing rule catalog in `docs/configuration.md`.

## Documentation ownership

- Put user-facing concepts and quick-start information in `README.md`.
- Put detailed user installation and configuration guidance in `docs/`.
- Put contributor process here.
- Put private vulnerability reporting policy in `SECURITY.md`.
- Put CI controls and repository administration in `docs/maintainers.md`.
- Put instructions useful only to coding agents in `AGENTS.md`.

Do not duplicate normative runtime behavior in several guides. Link to the relevant file under `skills/deep-review/references/` when exact behavior matters.

## Merge requests

Before opening a merge request:

- run the complete test suite;
- review the diff for unrelated changes and generated artifacts;
- update tests for contract changes;
- update the appropriate user or maintainer documentation;
- explain behavior, safety, or compatibility effects in the merge-request description.

Use a focused branch and reference the related issue in commits and the merge request.
