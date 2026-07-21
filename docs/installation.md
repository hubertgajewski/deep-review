# Installation

Deep Review is an [Agent Skill](https://agentskills.io) packaged in `skills/deep-review/`. Install that directory—not the repository root—under a skill-discovery directory supported by your AI client.

## Choose a scope

Project installation provides shared, reproducible behavior when the current checkout and the people allowed to change its skill files are already trusted. Commit the installed `deep-review` directory so teammates and remote agents use the reviewed version, and protect changes to that directory with repository ownership or required-approval rules where available. Treat changes to a vendored skill like changes to executable CI configuration.

Do not initiate a review from an untrusted checkout containing a project-installed skill. A branch, merge request, or fork can replace `SKILL.md` before Deep Review starts and therefore before its untrusted-input boundaries apply. For untrusted changes, install the reviewed Deep Review commit in a user or administrator location, start the AI client from a separate clean checkout of the trusted base that does not contain contributor-controlled skill changes, and use `--github-pr` or `--gitlab-mr`. Deep Review then retrieves and materializes the reviewed head in its isolated review context. If the client gives project skills precedence over user skills, the separate trusted checkout is required even when a user copy is installed. For a client without user or administrator installation, keep the reviewed project copy only in that separate trusted checkout and initiate the remote review there.

User installation is also useful for personal use across many repositories, but it is not available in every client.

After installation, the important path is:

```text
<skill-root>/deep-review/SKILL.md
```

Do not flatten the package or copy only `SKILL.md`; Deep Review also needs its `references/`, `scripts/`, and `agents/` directories.

## Install a project copy

The portable project location is `.agents/skills/`, supported by many—but not all—clients. Check the [client table](#ai-client-locations) and replace `.agents/skills` with the client-native project directory when necessary.

### Linux and macOS

Choose the exact lowercase, 40-character commit SHA you reviewed in the upstream repository. Do not substitute a branch name or an unverified tag. Then, from the consuming repository root:

```bash
deep_review_ref="<reviewed-40-character-commit-sha>"
review_destination=".agents/skills/deep-review"
review_source="$(mktemp -d)"

if ! printf '%s\n' "$deep_review_ref" | grep -Eq '^[0-9a-f]{40}$'; then
  echo "deep_review_ref must be a lowercase, 40-character commit SHA" >&2
  exit 1
fi
if [ -e "$review_destination" ] || [ -L "$review_destination" ]; then
  echo "$review_destination already exists; review changes before replacing it" >&2
  exit 1
fi

if ! git init -q "$review_source"; then
  echo "git init failed" >&2
  exit 1
fi
if ! git -C "$review_source" remote add origin https://gitlab.com/hubertgajewski-ai/deep-review.git; then
  echo "git remote add failed" >&2
  exit 1
fi
if ! git -C "$review_source" fetch --depth 1 origin "$deep_review_ref"; then
  echo "git fetch failed" >&2
  exit 1
fi
if ! git -C "$review_source" checkout --detach FETCH_HEAD; then
  echo "git checkout failed" >&2
  exit 1
fi
if ! resolved_commit="$(git -C "$review_source" rev-parse HEAD)"; then
  echo "git rev-parse failed" >&2
  exit 1
fi
if [ "$resolved_commit" != "$deep_review_ref" ]; then
  echo "fetched commit does not match deep_review_ref" >&2
  exit 1
fi
mkdir -p .agents/skills
cp -R "$review_source/skills/deep-review" "$review_destination"
```

### Windows PowerShell

From the consuming repository root:

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

git init -q $reviewSource
if ($LASTEXITCODE -ne 0) { throw "git init failed" }
git -C $reviewSource remote add origin https://gitlab.com/hubertgajewski-ai/deep-review.git
if ($LASTEXITCODE -ne 0) { throw "git remote add failed" }
git -C $reviewSource fetch --depth 1 origin $deepReviewRef
if ($LASTEXITCODE -ne 0) { throw "git fetch failed" }
git -C $reviewSource checkout --detach FETCH_HEAD
if ($LASTEXITCODE -ne 0) { throw "git checkout failed" }
$resolvedCommit = (git -C $reviewSource rev-parse HEAD)
if ($LASTEXITCODE -ne 0 -or $resolvedCommit -cne $deepReviewRef) {
    throw "fetched commit does not match deepReviewRef"
}
New-Item -ItemType Directory -Force .agents\skills | Out-Null
Copy-Item -Recurse -LiteralPath (Join-Path $reviewSource "skills\deep-review") -Destination $reviewDestination
```

These commands intentionally fail or require intervention if `deep-review` is already installed. Review upstream changes before replacing a trusted skill. Commit the copied package when it is intended to be shared by the project.

## Install a user copy

Use the same copy process with the user directory supported by your client. For example, clients using the shared `.agents` convention use:

```text
Linux/macOS:  $HOME/.agents/skills/deep-review/
PowerShell:   $env:USERPROFILE\.agents\skills\deep-review\
Command Prompt: %USERPROFILE%\.agents\skills\deep-review\
```

The `~` notation in the client table means the current user's home directory. It works in common POSIX shells and PowerShell, but not in Command Prompt. Project-relative paths such as `.agents/skills` identify the same repository location on Linux, macOS, and Windows; only the displayed separator differs.

For WSL, `$HOME` is the Linux home directory inside the selected distribution, not the Windows `%USERPROFILE%` directory. Install the skill in the environment where the client process runs.

Installation support does not permit weaker filesystem checks at review time. Local and path reviews require the active client to provide a secure-open adapter that can anchor reads to the repository root, reject symlink or Windows reparse-point traversal, verify file identity, and prove containment. When those capabilities are unavailable, Deep Review fails scope resolution before reading mutable primary content; a client may use WSL only when the reviewed repository is also inside that environment's filesystem boundary. Remote reviews apply the same invariant-based checks to their immutable snapshot context.

## Invoke Deep Review

Naming the skill in natural language is the portable form:

```text
Use the deep-review skill to review my current repository changes.
```

Some clients provide an explicit mention or command syntax:

| Client | Explicit invocation | Skill discovery or selection |
| --- | --- | --- |
| Claude Code | `/deep-review --base main` | Type `/` to find installed skills. |
| Codex CLI and IDE | `$deep-review --base main` | Type `$` to mention a skill, or open `/skills`. |
| Devin | `@skills:deep-review --base main` | Devin uses the `@skills:<name>` namespace. |
| Windsurf Cascade | `@deep-review --base main` | Type `@` to mention the skill. |

Do not assume `/`, `$`, and `@` are interchangeable. For clients not listed above, use natural language or the discovery mechanism linked in the client table. T3 Code follows the invocation behavior of its active provider.

For a numbered remote change, use the familiar reference style for the hosting provider:

```text
Use deep-review #123
Use deep-review !123
```

`#123` is the familiar GitHub-style reference, while `!123` is GitLab merge-request notation. For backward compatibility, `#123` and bare `123` infer the provider from the trusted repository remote. `!123` explicitly selects GitLab and is equivalent to `--gitlab-mr 123`. These examples are AI-client invocations, not shell commands.

Both reference styles work with client-specific invocation prefixes:

```text
/deep-review #123
/deep-review !123
$deep-review #123
$deep-review !123
@skills:deep-review #123
@skills:deep-review !123
@deep-review #123
@deep-review !123
```

Scope selectors and modifiers are appended after the client-specific invocation token. For example:

```text
/deep-review --gitlab-mr 123
$deep-review --path src/payments
@deep-review --focus "pay particular attention to retry behavior"
@skills:deep-review --range release..HEAD
```

## AI client locations

Clients are listed alphabetically. Locations and links were verified against first-party documentation on 2026-07-20. Product support changes quickly, so consult the linked source if discovery fails.

| AI client | Project location | User or global location | Notes and official source |
| --- | --- | --- | --- |
| Amp | `.agents/skills` | `~/.config/agents/skills` or `~/.agents/skills` | Amp also reads Claude-compatible locations. [Amp Owner's Manual](https://ampcode.com/manual#agent-skills) |
| Claude Code CLI and Claude Desktop | `.claude/skills` | `~/.claude/skills` | Claude Code surfaces share this filesystem model. For regular Claude chat or Cowork, upload a ZIP as described below. [Claude Code skills](https://code.claude.com/docs/en/slash-commands), [Claude app skills](https://support.claude.com/en/articles/12512180-use-skills-in-claude) |
| Cline | `.cline/skills` | `~/.cline/skills` | Skills are experimental and may need enabling in **Settings > Features**. Cline also recognizes selected compatibility paths. [Cline skills](https://docs.cline.bot/customization/skills) |
| Codex CLI, IDE, and desktop | `.agents/skills` | `~/.agents/skills` | Codex scans repository skill directories from the working directory to the repository root and supports symlinked skill folders. [OpenAI skill guide](https://learn.chatgpt.com/docs/build-skills) |
| Cursor | `.agents/skills` or `.cursor/skills` | `~/.agents/skills` or `~/.cursor/skills` | Available in Cursor editor and CLI; use a current release. [Cursor Agent Skills](https://cursor.com/docs/context/skills) |
| Devin | `.agents/skills` (recommended), `.github/skills`, or another supported compatibility path | Not currently documented | Devin skills are repository-scoped; it currently documents no global skill directory. [Devin skills](https://docs.devin.ai/product-guides/skills) |
| Gemini CLI | `.agents/skills` or `.gemini/skills` | `~/.agents/skills` or `~/.gemini/skills` | `gemini skills install` and `gemini skills link` are also supported. [Gemini CLI skills](https://geminicli.com/docs/cli/using-agent-skills/) |
| GitHub Copilot CLI, VS Code, and coding agent | `.github/skills`, `.agents/skills`, or `.claude/skills` | `~/.copilot/skills` or `~/.agents/skills` | Skills also work with Copilot code review, the Copilot app, and JetBrains agent mode. [GitHub Copilot skills](https://docs.github.com/en/copilot/concepts/agents/about-agent-skills) |
| Google Antigravity | `.agents/skills` | `~/.gemini/config/skills` | `.agent/skills` remains a legacy workspace compatibility path. [Antigravity skills](https://antigravity.google/docs/skills?app=antigravity-ide) |
| Goose | `.agents/skills` | `~/.agents/skills` | `.goose/skills` and Claude-compatible directories are retained for backward compatibility. [Goose Agent Skills](https://goose-docs.ai/docs/guides/context-engineering/using-skills/) |
| Grok Build CLI | `.grok/skills` | `~/.grok/skills` | Additional directories can be configured under `[skills] paths` in `~/.grok/config.toml`. [Grok skills](https://docs.x.ai/build/features/skills-plugins-marketplaces) |
| JetBrains Junie | `.junie/skills` | `~/.junie/skills` | On Windows the documented global path is `%USERPROFILE%\.junie\skills`. Skills work in Junie CLI and JetBrains IDEs. [Junie Agent skills](https://junie.jetbrains.com/docs/agent-skills.html) |
| Kiro | `.kiro/skills` | `~/.kiro/skills` | Applies to Kiro IDE and CLI; custom CLI agents must list skill resources explicitly. [Kiro IDE skills](https://kiro.dev/docs/skills/), [Kiro CLI skills](https://kiro.dev/docs/cli/skills/) |
| Mistral Vibe Code | `.agents/skills` or `.vibe/skills` | `~/.vibe/skills` | Custom directories can be set with `skill_paths` in Vibe's `config.toml`. [Vibe Code skills](https://docs.mistral.ai/vibe/code/cli/skills) |
| OpenCode | `.agents/skills`, `.opencode/skills`, or `.claude/skills` | `~/.agents/skills`, `~/.config/opencode/skills`, or `~/.claude/skills` | OpenCode recommends WSL for the best Windows experience; install under the WSL home when OpenCode runs there. [OpenCode skills](https://opencode.ai/docs/skills), [Windows/WSL guidance](https://opencode.ai/docs/windows-wsl/) |
| OpenHands | `.agents/skills` | `~/.openhands/skills` | `/add-skill` installs into the current workspace; global installation is manual. [Adding OpenHands skills](https://docs.openhands.dev/overview/skills/adding) |
| Qwen Code | `.qwen/skills` | `~/.qwen/skills` | Recent Qwen Code versions expose skills through `/skills` and `/<skill-name>`. [Qwen Code skills](https://qwenlm.github.io/qwen-code-docs/en/users/features/skills/) |
| T3 Code | Use the selected provider's project location | Use the selected provider's user location | T3 Code launches supported provider harnesses rather than defining a separate skill store. Follow the Claude Code, Codex, Cursor, Grok, or OpenCode row that matches the active provider. [T3 Code](https://t3.codes/), [T3 Code repository](https://github.com/pingdotgg/t3code) |
| Warp | `.agents/skills` (recommended), `.warp/skills`, or another supported compatibility path | `~/.agents/skills` (recommended), `~/.warp/skills`, or another supported compatibility path | Warp scans a broad set of client-compatible directories. [Warp skills](https://docs.warp.dev/agent-platform/capabilities/skills) |
| Windsurf Cascade | `.agents/skills` or `.windsurf/skills` | `~/.agents/skills` or `~/.codeium/windsurf/skills` | Claude-compatible locations are optional when Claude configuration import is enabled. Enterprise system paths are OS-specific. [Windsurf skills](https://docs.windsurf.com/windsurf/cascade/skills) |

### Enterprise and system locations

Do not derive enterprise paths by replacing `$HOME` with a system directory. They are product- and OS-specific. For example, Codex documents `/etc/codex/skills` for administrator-installed skills, while Windsurf uses `/Library/Application Support/Windsurf/skills/` on macOS, `/etc/windsurf/skills/` on Linux/WSL, and `C:\ProgramData\Windsurf\skills\` on Windows. Follow the client's administrative documentation and deployment policy.

## Claude chat and Cowork ZIP upload

Claude chat and Cowork do not discover a local project folder in the same way as Claude Code. Package the `deep-review` directory as a ZIP so the archive contains `deep-review/SKILL.md`, then open **Customize > Skills**, choose **Create skill > Upload a skill**, upload the ZIP, and enable it.

Linux/macOS, from this repository:

```bash
cd skills
zip -r deep-review.zip deep-review
```

Windows PowerShell, from this repository:

```powershell
Compress-Archive -Path .\skills\deep-review -DestinationPath .\deep-review.zip
```

Organization sharing and provisioning depend on the Claude plan and administrator settings. Uploaded personal skills are private unless explicitly shared through a supported organization workflow.

## Updating

Deep Review has no automatic updater. For a vendored project installation:

1. Select an exact reviewed commit SHA, or verify a signed tag and record the exact commit it resolves to.
2. Compare `skills/deep-review/` with the installed copy.
3. Review changes to `SKILL.md`, `references/`, and executable scripts.
4. Replace the installed package and commit the update as one reviewed change.
5. Re-run the client's discovery check and a small review invocation.

Pinning an exact commit in repository documentation or dependency tooling makes installations reproducible. Avoid automatically pulling an unreviewed default branch into trusted skill directories.

## Verify installation

Start a new client session or use its reload command, then:

1. List available skills and confirm `deep-review` appears.
2. Ask the client to use Deep Review on a repository with a small known diff.
3. Confirm the output includes the reviewer roster and ends in a documented aggregate terminal state.

Examples of discovery commands include `/skills` in Claude Code, Gemini CLI, Qwen Code, and Warp; `goose skills list` in Goose; and the client settings UI where documented. If discovery fails, check that the final path is exactly `<skill-root>/deep-review/SKILL.md`, validate the YAML frontmatter, and consult the linked first-party client guide.
