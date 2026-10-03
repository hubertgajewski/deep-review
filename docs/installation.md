# Installation

Deep Review is an [Agent Skill](https://agentskills.io) packaged in `skills/deep-review/`. The verified release installers put the complete package in the correct directory for your client. Publication in the Claude community marketplace is planned; until that listing is available, use the release installer below.

## Requirements

- **Linux and macOS:** `curl`, `tar`, and either `sha256sum` or `shasum`.
- **Windows:** PowerShell 7.
- **Git is required to run Deep Review** and resolve repository review scopes.
- **Python 3 is optional.** It enables the bundled deterministic cache and result-processing helpers. With Python 3.10 or newer and Git 2.31 or newer, it also enables quota-enforced remote metadata fetching. Deep Review can still review without persistent reuse or transport quotas when those helpers are unavailable.
- **Remote review needs the provider CLI.** Authenticate `gh` for `--github-pr` or `glab` for `--gitlab-mr` before invoking the skill.
- **The AI client must support Agent Skills** and the filesystem guarantees described under [Runtime host requirements](#runtime-host-requirements).

## Install from a release

Paste the three commands for your operating system. The installer asks which AI client you use, whether to install for your user or the current project, and confirms the exact destination before downloading the package or changing files. It does not default to any client.

### Linux

```bash
( set -eu; install_dir="$(mktemp -d)"; trap 'rm -rf "$install_dir"' EXIT HUP INT TERM; curl --fail --fail-early --location --proto '=https' --tlsv1.2 --output "$install_dir/deep-review-install.sh" https://gitlab.com/hubertgajewski-ai/deep-review/-/releases/v1.1.1/downloads/deep-review-install.sh --output "$install_dir/deep-review-install.sh.sha256" https://gitlab.com/hubertgajewski-ai/deep-review/-/releases/v1.1.1/downloads/deep-review-install.sh.sha256 &&
(cd "$install_dir" && sha256sum -c deep-review-install.sh.sha256) &&
sh "$install_dir/deep-review-install.sh" )
```

### macOS

```bash
( set -eu; install_dir="$(mktemp -d)"; trap 'rm -rf "$install_dir"' EXIT HUP INT TERM; curl --fail --fail-early --location --proto '=https' --tlsv1.2 --output "$install_dir/deep-review-install.sh" https://gitlab.com/hubertgajewski-ai/deep-review/-/releases/v1.1.1/downloads/deep-review-install.sh --output "$install_dir/deep-review-install.sh.sha256" https://gitlab.com/hubertgajewski-ai/deep-review/-/releases/v1.1.1/downloads/deep-review-install.sh.sha256 &&
(cd "$install_dir" && shasum -a 256 -c deep-review-install.sh.sha256) &&
sh "$install_dir/deep-review-install.sh" )
```

The second command must print `deep-review-install.sh: OK`. Because the commands are joined with `&&`, a failed download or checksum prevents the installer from running.

### Windows PowerShell

```powershell
& { $ErrorActionPreference = "Stop"; $installDir = Join-Path ([System.IO.Path]::GetTempPath()) ("deep-review-install-" + [guid]::NewGuid()); New-Item -ItemType Directory -Path $installDir | Out-Null; try { Invoke-WebRequest https://gitlab.com/hubertgajewski-ai/deep-review/-/releases/v1.1.1/downloads/deep-review-install.ps1 -OutFile (Join-Path $installDir "deep-review-install.ps1"); Invoke-WebRequest https://gitlab.com/hubertgajewski-ai/deep-review/-/releases/v1.1.1/downloads/deep-review-install.ps1.sha256 -OutFile (Join-Path $installDir "deep-review-install.ps1.sha256")
$expected = ((Get-Content (Join-Path $installDir "deep-review-install.ps1.sha256") -TotalCount 1) -split '\s+')[0]; if ((Get-FileHash (Join-Path $installDir "deep-review-install.ps1") -Algorithm SHA256).Hash.ToLowerInvariant() -cne $expected) { throw "Installer checksum verification failed" }
& (Join-Path $installDir "deep-review-install.ps1") } finally { Remove-Item -Recurse -Force -LiteralPath $installDir -ErrorAction SilentlyContinue } }
```

PowerShell stops if either download or the checksum check fails. On every platform, the installer reports the installed version, destination, checksum, and first review command.

## Automated installation

Non-interactive environments must provide a client and scope; the installer never guesses. The release version is built into the installer, while `--version`/`-Version` remains available for pinned automation and testing.

| Argument | Values | Meaning |
| --- | --- | --- |
| Client | `codex`, `claude-code`, `cline`, `grok`, `junie`, `kiro`, `mistral`, `qwen`, or a shared-directory client listed below | Selects the client's skill directory. |
| Scope | `user`/`User` or `project`/`Project` | Installs for your account or the current repository. |
| Version | An exact release such as `v1.1.1` | Optional override selecting immutable versioned assets. |

For example, a Claude Code project installation uses:

```bash
sh ./deep-review-install.sh --client claude-code --scope project
```

```powershell
.\deep-review-install.ps1 -Client claude-code -Scope Project
```

### Manual download

If command-line downloads are unavailable, open the [`v1.1.1` Release](https://gitlab.com/hubertgajewski-ai/deep-review/-/releases/v1.1.1) and save all four files for your operating system in one directory:

- Linux and macOS: `deep-review-install.sh`, `deep-review-install.sh.sha256`, `deep-review-v1.1.1.tar.gz`, and `deep-review-v1.1.1.tar.gz.sha256`.
- Windows: `deep-review-install.ps1`, `deep-review-install.ps1.sha256`, `deep-review-v1.1.1.zip`, and `deep-review-v1.1.1.zip.sha256`.

Return to the user home or project directory where installation should be resolved, then verify and run the downloaded files. On Linux use:

```bash
(cd /path/to/downloads && sha256sum -c deep-review-install.sh.sha256) &&
sh /path/to/downloads/deep-review-install.sh --asset-dir /path/to/downloads
```

On macOS, replace `sha256sum -c` with `shasum -a 256 -c`. On Windows PowerShell use:

```powershell
$assets = "C:\path\to\downloads"; $installer = Join-Path $assets "deep-review-install.ps1"; $expected = ((Get-Content (Join-Path $assets "deep-review-install.ps1.sha256") -TotalCount 1) -split '\s+')[0]
if ((Get-FileHash $installer -Algorithm SHA256).Hash.ToLowerInvariant() -cne $expected) { throw "Installer checksum verification failed" }
& $installer -AssetDirectory $assets
```

The installer verifies the package checksum again before changing the destination. Do not run either installer unless its own checksum verification succeeds.

## Choose where to install

Choose one location before copying the package:

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

### Find your client directory

The shared project location `.agents/skills` works with Amp, Codex, Cursor, Devin, Gemini CLI, GitHub Copilot, Google Antigravity, Goose, OpenCode, OpenHands, Warp, and Windsurf. Several of these clients also support a vendor-specific location; consult the [client reference](#client-reference) when shared discovery is unavailable or organizational policy requires a native directory.

Common native locations are:

| Client | Project | User |
| --- | --- | --- |
| Claude Code | `.claude/skills` | `~/.claude/skills` |
| Cline | `.cline/skills` | `~/.cline/skills` |
| Grok Build CLI | `.grok/skills` | `~/.grok/skills` |
| JetBrains Junie | `.junie/skills` | `~/.junie/skills` |
| Kiro | `.kiro/skills` | `~/.kiro/skills` |
| Mistral Vibe Code | `.vibe/skills` | `~/.vibe/skills` |
| Qwen Code | `.qwen/skills` | `~/.qwen/skills` |

T3 Code uses the skill location of its active provider. Claude chat and Cowork use ZIP upload rather than a local discovery directory.

## Install a pinned copy from source

Use this advanced alternative when release assets are unavailable or policy requires installation from a reviewed commit. Select the exact lowercase, 40-character upstream commit SHA that you reviewed. The examples intentionally refuse to overwrite an existing destination.

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

Remote reviews choose a metadata-fetch transport before fetching and report it:

- `transport quotas: enforced` means the bundled `scripts/bounded_fetch.py` helper fetched commit and tree metadata. It enforced at most 64 MiB of compressed input, 256 MiB of expanded commit/tree objects, and 320 MiB of isolated-store disk use. It requires Python 3.10 or newer, Git 2.31 or newer, an `https://` or `file://` remote, and a server offering Git protocol v2 with partial-clone filtering. HTTPS fetches use Git's configured credentials.
- `transport quotas: unavailable; using standard Git` means the helper, a compatible Python, or one of those capabilities was unavailable, for example with an SSH remote. Ordinary Git fetched the metadata without those three ceilings. The review continues and is not incomplete for that reason alone.

On both paths, repository isolation, immutable identity checks, blob-free filtering, path preflight, evidence size limits, and model-input limits still apply. Authentication and access failures still fail the review. A failed bounded fetch also fails the review and is never retried with ordinary Git. The [scope-resolution contract](../skills/deep-review/references/scope-resolution.md#transport-quota-preflight) defines the exact behavior.

## Updating

Use the complete block for your operating system so the freshly downloaded and verified installer receives the update option before its private temporary copy is removed.

### Linux update

```bash
( set -eu; install_dir="$(mktemp -d)"; trap 'rm -rf "$install_dir"' EXIT HUP INT TERM; curl --fail --fail-early --location --proto '=https' --tlsv1.2 --output "$install_dir/deep-review-install.sh" https://gitlab.com/hubertgajewski-ai/deep-review/-/releases/v1.1.1/downloads/deep-review-install.sh --output "$install_dir/deep-review-install.sh.sha256" https://gitlab.com/hubertgajewski-ai/deep-review/-/releases/v1.1.1/downloads/deep-review-install.sh.sha256 &&
(cd "$install_dir" && sha256sum -c deep-review-install.sh.sha256) &&
sh "$install_dir/deep-review-install.sh" --update )
```

### macOS update

```bash
( set -eu; install_dir="$(mktemp -d)"; trap 'rm -rf "$install_dir"' EXIT HUP INT TERM; curl --fail --fail-early --location --proto '=https' --tlsv1.2 --output "$install_dir/deep-review-install.sh" https://gitlab.com/hubertgajewski-ai/deep-review/-/releases/v1.1.1/downloads/deep-review-install.sh --output "$install_dir/deep-review-install.sh.sha256" https://gitlab.com/hubertgajewski-ai/deep-review/-/releases/v1.1.1/downloads/deep-review-install.sh.sha256 &&
(cd "$install_dir" && shasum -a 256 -c deep-review-install.sh.sha256) &&
sh "$install_dir/deep-review-install.sh" --update )
```

### Windows PowerShell update

```powershell
& { $ErrorActionPreference = "Stop"; $installDir = Join-Path ([System.IO.Path]::GetTempPath()) ("deep-review-install-" + [guid]::NewGuid()); New-Item -ItemType Directory -Path $installDir | Out-Null; try { Invoke-WebRequest https://gitlab.com/hubertgajewski-ai/deep-review/-/releases/v1.1.1/downloads/deep-review-install.ps1 -OutFile (Join-Path $installDir "deep-review-install.ps1"); Invoke-WebRequest https://gitlab.com/hubertgajewski-ai/deep-review/-/releases/v1.1.1/downloads/deep-review-install.ps1.sha256 -OutFile (Join-Path $installDir "deep-review-install.ps1.sha256")
$expected = ((Get-Content (Join-Path $installDir "deep-review-install.ps1.sha256") -TotalCount 1) -split '\s+')[0]; if ((Get-FileHash (Join-Path $installDir "deep-review-install.ps1") -Algorithm SHA256).Hash.ToLowerInvariant() -cne $expected) { throw "Installer checksum verification failed" }
& (Join-Path $installDir "deep-review-install.ps1") -Update } finally { Remove-Item -Recurse -Force -LiteralPath $installDir -ErrorAction SilentlyContinue } }
```

The installer verifies and stages the complete new package before changing the destination. If activation fails, it restores the previous installation. It never merges old and new package files.

For a source-installed or manually vendored copy:

1. Select and review an exact upstream commit SHA, or verify a signed tag and record its commit.
2. Compare `skills/deep-review/` with the installed copy.
3. Review changes to `SKILL.md`, `references/`, and executable scripts.
4. Replace the complete installed directory as one change.
5. Repeat the [verification steps](#verify-installation).

Never automatically pull an unreviewed default branch into a trusted skill directory.

## Offline installation

Follow [Manual download](#manual-download). It lists all four files to transfer, verifies the installer, and runs it with the downloaded package. The installer verifies the package checksum and version before changing the destination. For an update, add `--update` on Linux or macOS, or `-Update` on Windows.
