# Installation

Deep Review is an [Agent Skill](https://agentskills.io) packaged in `skills/deep-review/`. The verified release installers put that complete package in the standard skill directory for your client and scope. Publication in the Claude community marketplace is planned; until that listing is available, use a release installer below.

## Requirements

- **Linux and macOS installation needs** `curl`, `tar`, and either `sha256sum` or `shasum`.
- **Windows installation needs** PowerShell 7 or newer.
- **Git is required at runtime** to resolve review scopes, but not to run a release installer.
- **Python 3 is optional.** It enables the bundled deterministic cache and result-processing helpers; Deep Review can still review without persistent reuse when those helpers are unavailable.
- **Remote review needs the provider CLI.** Authenticate `gh` for `--github-pr` or `glab` for `--gitlab-mr` before invoking the skill.
- **The AI client must support Agent Skills** and the filesystem guarantees described under [Runtime host requirements](#runtime-host-requirements).

## Install a verified release

Installers are on the **[Deep Review releases page](https://gitlab.com/hubertgajewski-ai/deep-review/-/releases)** under **Assets > Links**. If that page says there are no releases, a verified installer has not been published yet; use the [pinned-commit instructions](#advanced-install-a-pinned-commit) until one is available.

For `v1.1.0`, the downloads will be:

| System | Installer | Checksum |
| --- | --- | --- |
| Linux or macOS | [`deep-review-install.sh`](https://gitlab.com/hubertgajewski-ai/deep-review/-/releases/v1.1.0/downloads/deep-review/v1.1.0/deep-review-install.sh) | [`deep-review-install.sh.sha256`](https://gitlab.com/hubertgajewski-ai/deep-review/-/releases/v1.1.0/downloads/deep-review/v1.1.0/deep-review-install.sh.sha256) |
| Windows | [`deep-review-install.ps1`](https://gitlab.com/hubertgajewski-ai/deep-review/-/releases/v1.1.0/downloads/deep-review/v1.1.0/deep-review-install.ps1) | [`deep-review-install.ps1.sha256`](https://gitlab.com/hubertgajewski-ai/deep-review/-/releases/v1.1.0/downloads/deep-review/v1.1.0/deep-review-install.ps1.sha256) |

Do not use those links until the releases page lists `v1.1.0`. You may click both downloads above, or copy and paste the matching block below to download, verify, and install them. The examples install Deep Review for Codex at user scope. For another setup, replace `codex` with an [installer client ID](#installer-destinations) or change `user` to `project`.

### Linux and macOS

```bash
version=v1.1.0
release="https://gitlab.com/hubertgajewski-ai/deep-review/-/releases/$version/downloads/deep-review/$version"
curl --fail --location --remote-name "$release/deep-review-install.sh" --remote-name "$release/deep-review-install.sh.sha256"
if command -v sha256sum >/dev/null 2>&1; then sha256sum -c deep-review-install.sh.sha256; else shasum -a 256 -c deep-review-install.sh.sha256; fi
sh ./deep-review-install.sh --client codex --scope user --version "$version"
```

The checksum command must print `deep-review-install.sh: OK` before the installer runs.

### Windows PowerShell

```powershell
$version = "v1.1.0"
$release = "https://gitlab.com/hubertgajewski-ai/deep-review/-/releases/$version/downloads/deep-review/$version"
Invoke-WebRequest "$release/deep-review-install.ps1" -OutFile deep-review-install.ps1
Invoke-WebRequest "$release/deep-review-install.ps1.sha256" -OutFile deep-review-install.ps1.sha256
$expected = ((Get-Content ./deep-review-install.ps1.sha256 -TotalCount 1) -split '\s+')[0]
if ((Get-FileHash ./deep-review-install.ps1 -Algorithm SHA256).Hash.ToLowerInvariant() -cne $expected) { throw "Installer checksum verification failed" }
./deep-review-install.ps1 -Client codex -Scope User -Version $version
```

PowerShell stops before installation if the checksum does not match.

Keeping the downloaded installer as a file makes its checksum verifiable and lets you inspect it before running it. Do not pipe a downloaded installer directly into a shell.

The installer downloads the package for exactly that version into a private temporary directory, verifies its SHA-256 checksum, validates the complete package layout, and only then activates it. It prints the installed version, destination, verification result, and first review command. A failed download, checksum, extraction, or validation leaves the destination unchanged and removes temporary files.

An existing installation is never replaced implicitly. Inspect the new release, then add `--update` on Linux or macOS, or `-Update` in PowerShell, to replace the complete directory transactionally.

## Choose where to install

Choose the installer scope based on who should discover the skill:

| Scope | Use it when | Trust requirement |
| --- | --- | --- |
| User | You want one installation across repositories or need to review untrusted remote changes. | Install a commit you have reviewed and keep it outside contributor-controlled checkouts. |
| Project | A team wants one version committed with the repository. | The checkout and everyone allowed to change the installed skill must already be trusted. |

The final layout must be:

```text
<skill-root>/deep-review/SKILL.md
<skill-root>/deep-review/references/
<skill-root>/deep-review/scripts/
<skill-root>/deep-review/agents/
```

Do not flatten the package or copy only `SKILL.md`.

### Installer destinations

The installer maps these client IDs and never asks for a raw destination:

| Installer client ID | Clients | Project root | User root |
| --- | --- | --- | --- |
| `amp`, `codex`, `cursor`, `devin`, `gemini`, `github-copilot`, `antigravity`, `goose`, `opencode`, `openhands`, `warp`, `windsurf` | Shared Agent Skills convention | `.agents/skills` | `~/.agents/skills` |
| `claude-code` | Claude Code | `.claude/skills` | `~/.claude/skills` |
| `cline` | Cline | `.cline/skills` | `~/.cline/skills` |
| `grok` | Grok Build CLI | `.grok/skills` | `~/.grok/skills` |
| `junie` | JetBrains Junie | `.junie/skills` | `~/.junie/skills` |
| `kiro` | Kiro | `.kiro/skills` | `~/.kiro/skills` |
| `mistral` | Mistral Vibe Code | `.vibe/skills` | `~/.vibe/skills` |
| `qwen` | Qwen Code | `.qwen/skills` | `~/.qwen/skills` |

T3 Code uses the skill location of its active provider, so `--client t3` stops without changing the filesystem and points to the manual guidance below. Claude chat and Cowork use ZIP upload rather than a local discovery directory; `claude-chat` and `claude-cowork` stop the same way. The installer also rejects unknown client IDs instead of guessing.

## Advanced: install a pinned commit

Use this process when you need a commit that has not been released. Select the exact lowercase, 40-character upstream commit SHA that you reviewed and choose the destination yourself. The examples intentionally refuse to overwrite an existing destination.

### Linux and macOS

Run this from the consuming repository for a project installation. Change `review_destination` to your chosen user or client-native path when needed.

```bash
(
set -e
deep_review_ref="<reviewed-40-character-commit-sha>"
review_destination=".agents/skills/deep-review"
review_source="$(mktemp -d)"
trap 'rm -rf "$review_source"' EXIT

if ! printf '%s\n' "$deep_review_ref" | grep -Eq '^[0-9a-f]{40}$'; then
  echo "deep_review_ref must be a lowercase, 40-character commit SHA" >&2
  exit 1
fi
if [ -e "$review_destination" ] || [ -L "$review_destination" ]; then
  echo "$review_destination already exists; review changes before replacing it" >&2
  exit 1
fi

git init -q "$review_source"
git -C "$review_source" remote add origin https://gitlab.com/hubertgajewski-ai/deep-review.git
git -C "$review_source" fetch --depth 1 origin "$deep_review_ref"
git -C "$review_source" checkout --detach FETCH_HEAD
resolved_commit="$(git -C "$review_source" rev-parse HEAD)"

if [ "$resolved_commit" != "$deep_review_ref" ]; then
  echo "fetched commit does not match deep_review_ref" >&2
  exit 1
fi

mkdir -p "$(dirname "$review_destination")"
cp -R "$review_source/skills/deep-review" "$review_destination"
)
```

### Windows PowerShell

Run this from the consuming repository. Change `$reviewDestination` as needed.

```powershell
$deepReviewRef = "<reviewed-40-character-commit-sha>"
$reviewDestination = ".agents\skills\deep-review"
$reviewSource = Join-Path ([System.IO.Path]::GetTempPath()) ("deep-review-" + [guid]::NewGuid())

if ($deepReviewRef -cnotmatch '^[0-9a-f]{40}$') {
    throw "deepReviewRef must be a lowercase, 40-character commit SHA"
}
if ($null -ne (Get-Item -LiteralPath $reviewDestination -Force -ErrorAction SilentlyContinue)) {
    throw "$reviewDestination already exists; review changes before replacing it"
}

try {
    git init -q $reviewSource
    if ($LASTEXITCODE -ne 0) { throw "git init failed" }
    git -C $reviewSource remote add origin https://gitlab.com/hubertgajewski-ai/deep-review.git
    if ($LASTEXITCODE -ne 0) { throw "git remote add failed" }
    git -C $reviewSource fetch --depth 1 origin $deepReviewRef
    if ($LASTEXITCODE -ne 0) { throw "git fetch failed" }
    git -C $reviewSource checkout --detach FETCH_HEAD
    if ($LASTEXITCODE -ne 0) { throw "git checkout failed" }

    $resolvedCommit = git -C $reviewSource rev-parse HEAD
    if ($LASTEXITCODE -ne 0 -or $resolvedCommit -cne $deepReviewRef) {
        throw "fetched commit does not match deepReviewRef"
    }

    $reviewParent = Split-Path -Parent $reviewDestination
    New-Item -ItemType Directory -Force -Path $reviewParent | Out-Null
    Copy-Item -Recurse -LiteralPath (Join-Path $reviewSource "skills\deep-review") -Destination $reviewDestination
}
finally {
    Remove-Item -Recurse -Force -LiteralPath $reviewSource -ErrorAction SilentlyContinue
}
```

For a shared project installation, commit the copied package and protect changes to it with repository ownership or required approvals. For a user installation, common shared-convention destinations are `$HOME/.agents/skills/deep-review` on Linux/macOS and `$env:USERPROFILE\.agents\skills\deep-review` in PowerShell.

## Verify installation

1. Start a new client session or use its skill reload command.
2. List or search available skills and confirm `deep-review` appears.
3. Check that the discovered entry point is exactly `<skill-root>/deep-review/SKILL.md`.
4. Continue with the [README quick start](../README.md#quick-start) and run a small known review.
5. Confirm the output includes the reviewer roster and ends with `ready`, `blocked`, or `incomplete`.

If discovery fails, validate the `SKILL.md` YAML frontmatter, confirm the complete directory was copied, and check your client's first-party documentation below.

## Review untrusted remote changes

Do not start an AI client from an untrusted branch, merge request, or fork containing a project-installed skill. Contributor-controlled code can replace `SKILL.md` before Deep Review starts and before its untrusted-input boundaries apply.

Instead:

1. Install a reviewed Deep Review commit in a user or administrator location.
2. Start the AI client from a separate clean checkout of the trusted base.
3. Invoke the remote change with `--github-pr` or `--gitlab-mr`.

If project skills take precedence over user skills, the separate trusted checkout remains required. Deep Review then resolves the provider-recorded immutable identities and materializes reviewed content in its isolated context. Exact scope and filesystem behavior is defined by the [scope-resolution contract](../skills/deep-review/references/scope-resolution.md).

## Client reference

These first-party sources own volatile discovery paths and commands. They were last checked on 2026-07-20.

- [Amp](https://ampcode.com/manual#agent-skills)
- [Claude Code](https://code.claude.com/docs/en/slash-commands) and [Claude app skills](https://support.claude.com/en/articles/12512180-use-skills-in-claude)
- [Cline](https://docs.cline.bot/customization/skills)
- [Codex](https://learn.chatgpt.com/docs/build-skills)
- [Cursor](https://cursor.com/docs/context/skills)
- [Devin](https://docs.devin.ai/product-guides/skills)
- [Gemini CLI](https://geminicli.com/docs/cli/using-agent-skills/)
- [GitHub Copilot](https://docs.github.com/en/copilot/concepts/agents/about-agent-skills)
- [Google Antigravity](https://antigravity.google/docs/skills?app=antigravity-ide)
- [Goose](https://goose-docs.ai/docs/guides/context-engineering/using-skills/)
- [Grok Build CLI](https://docs.x.ai/build/features/skills-plugins-marketplaces)
- [JetBrains Junie](https://junie.jetbrains.com/docs/agent-skills.html)
- [Kiro](https://kiro.dev/docs/skills/)
- [Mistral Vibe Code](https://docs.mistral.ai/vibe/code/cli/skills)
- [OpenCode](https://opencode.ai/docs/skills)
- [OpenHands](https://docs.openhands.dev/overview/skills/adding)
- [Qwen Code](https://qwenlm.github.io/qwen-code-docs/en/users/features/skills/)
- [T3 Code](https://t3.codes/)
- [Warp](https://docs.warp.dev/agent-platform/capabilities/skills)
- [Windsurf](https://docs.windsurf.com/windsurf/cascade/skills)

## Other installation environments

### Claude chat and Cowork

Create a ZIP whose root contains the `deep-review` directory, including `deep-review/SKILL.md`. In Claude, open **Customize > Skills**, choose **Create skill > Upload a skill**, upload the ZIP, and enable it. Organization sharing depends on the Claude plan and administrator settings.

### Windows and WSL

`~` means the current user's home directory in common POSIX shells and PowerShell, but not Command Prompt. WSL uses the Linux home inside the selected distribution. Install the skill in the environment where the AI client runs and keep the reviewed repository inside that same filesystem boundary.

### Enterprise locations

Administrator paths are product- and operating-system-specific. Do not derive them by replacing `$HOME` with a system directory. Follow the client vendor's administrative documentation and deployment policy.

## Runtime host requirements

Local and path reviews require a secure-open adapter that anchors mutable reads to the repository root, rejects symlink or Windows reparse-point traversal, verifies file identity, and proves containment. Remote reviews apply the same guarantees to their immutable snapshot. If the host cannot establish them, Deep Review fails scope resolution or reports required evidence as incomplete rather than silently weakening the boundary.

## Updating

Deep Review has no automatic updater. For a release installation, review the target release and rerun the same installer with its version plus `--update` or `-Update`. The installer verifies and stages the replacement before changing the current directory.

To update an advanced pinned-commit installation manually:

1. Select and review an exact upstream commit SHA, or verify a signed tag and record its commit.
2. Compare `skills/deep-review/` with the installed copy.
3. Review changes to `SKILL.md`, `references/`, and executable scripts.
4. Replace the complete installed directory as one change.
5. Repeat the [verification steps](#verify-installation).

Never automatically pull an unreviewed default branch into a trusted skill directory.
