#!/bin/sh

set -eu

PROGRAM=${0##*/}
PACKAGE_BASE_URL=https://gitlab.com/api/v4/projects/84183178/packages/generic/deep-review

usage() {
    cat <<EOF
Usage: $PROGRAM --client CLIENT --scope user|project --version vMAJOR.MINOR.PATCH [--update] [--asset-dir DIR]

Downloads a versioned Deep Review package, verifies its SHA-256 checksum, and
installs it in the selected client's standard skill directory. --asset-dir is
for verified offline assets and tests; it must contain the archive and checksum.
EOF
}

fail() {
    printf '%s: %s\n' "$PROGRAM" "$*" >&2
    exit 1
}

client=
scope=
version=
update=false
asset_dir=

while [ "$#" -gt 0 ]; do
    case $1 in
        --client|--scope|--version|--asset-dir)
            [ "$#" -ge 2 ] || fail "$1 requires a value"
            case $1 in
                --client) client=$2 ;;
                --scope) scope=$2 ;;
                --version) version=$2 ;;
                --asset-dir) asset_dir=$2 ;;
            esac
            shift 2
            ;;
        --update)
            update=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *) fail "unknown argument: $1" ;;
    esac
done

[ -n "$client" ] || fail "--client is required"
[ -n "$scope" ] || fail "--scope is required"
[ -n "$version" ] || fail "--version is required"

printf '%s\n' "$version" | grep -Eq '^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$' ||
    fail "--version must be a semantic version such as v1.1.0"

case $client in
    amp|codex|cursor|devin|gemini|github-copilot|antigravity|goose|opencode|openhands|warp|windsurf)
        skill_root=.agents/skills
        ;;
    claude-code) skill_root=.claude/skills ;;
    cline) skill_root=.cline/skills ;;
    grok) skill_root=.grok/skills ;;
    junie) skill_root=.junie/skills ;;
    kiro) skill_root=.kiro/skills ;;
    mistral) skill_root=.vibe/skills ;;
    qwen) skill_root=.qwen/skills ;;
    t3|claude-chat|claude-cowork)
        fail "client '$client' has no deterministic local destination; see https://gitlab.com/hubertgajewski-ai/deep-review/-/blob/main/docs/installation.md#other-installation-environments"
        ;;
    *) fail "unsupported client '$client'; run $PROGRAM --help and see the installation guide for supported client IDs" ;;
esac

case $scope in
    project) destination="$PWD/$skill_root/deep-review" ;;
    user)
        [ -n "${HOME:-}" ] || fail "HOME is not set; cannot resolve the user installation directory"
        destination="$HOME/$skill_root/deep-review"
        ;;
    *) fail "--scope must be 'user' or 'project'" ;;
esac

if { [ -e "$destination" ] || [ -L "$destination" ]; } && [ "$update" != true ]; then
    fail "$destination already exists; inspect the new release, then rerun with --update to replace it"
fi
if [ -L "$destination" ]; then
    fail "$destination is a symbolic link; replace it manually before using --update"
fi

archive="deep-review-$version.tar.gz"
checksum="$archive.sha256"
tmp_root=
stage=
backup=
lock=
lock_owned=false
activation_owned=false
stage_leaf=
marker=.deep-review-installing

cleanup() {
    status=$?
    if [ "$status" -ne 0 ] && [ "$activation_owned" = true ] && [ -f "$destination/$marker" ]; then
        rm -rf -- "$destination"
    fi
    if [ "$status" -ne 0 ] && [ -n "$stage_leaf" ] && [ -f "$destination/$stage_leaf/$marker" ]; then
        rm -rf -- "$destination/$stage_leaf"
    fi
    if [ "$status" -ne 0 ] && [ -n "$backup" ] && { [ -e "$backup/deep-review" ] || [ -L "$backup/deep-review" ]; } && ! { [ -e "$destination" ] || [ -L "$destination" ]; }; then
        if ! mv "$backup/deep-review" "$destination" 2>/dev/null; then
            printf '%s: rollback failed; the previous installation remains at %s/deep-review\n' "$PROGRAM" "$backup" >&2
        fi
    fi
    [ -z "$stage" ] || rm -rf -- "$stage"
    if [ -n "$backup" ] && { [ -e "$backup/deep-review" ] || [ -L "$backup/deep-review" ]; }; then
        printf '%s: previous installation preserved at %s/deep-review\n' "$PROGRAM" "$backup" >&2
    elif [ -n "$backup" ]; then
        rm -rf -- "$backup"
    fi
    if [ "$lock_owned" = true ] && [ -n "$lock" ]; then
        rm -f -- "$lock/owner"
        rmdir "$lock" 2>/dev/null || true
    fi
    [ -z "$tmp_root" ] || rm -rf -- "$tmp_root"
    trap - EXIT HUP INT TERM
    exit "$status"
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

umask 077
tmp_root=$(mktemp -d "${TMPDIR:-/tmp}/deep-review-install.XXXXXX") || fail "could not create a private temporary directory"

if [ -n "$asset_dir" ]; then
    [ -f "$asset_dir/$archive" ] || fail "offline archive not found: $asset_dir/$archive"
    [ -f "$asset_dir/$checksum" ] || fail "offline checksum not found: $asset_dir/$checksum"
    cp "$asset_dir/$archive" "$tmp_root/$archive"
    cp "$asset_dir/$checksum" "$tmp_root/$checksum"
else
    command -v curl >/dev/null 2>&1 || fail "curl is required to download release assets"
    package_version=${version#v}
    asset_url="$PACKAGE_BASE_URL/$package_version"
    curl --fail --location --silent --show-error --proto '=https' --tlsv1.2 --max-filesize 67108864 \
        --output "$tmp_root/$archive" "$asset_url/$archive" || fail "failed to download $archive for $version"
    curl --fail --location --silent --show-error --proto '=https' --tlsv1.2 --max-filesize 4096 \
        --output "$tmp_root/$checksum" "$asset_url/$checksum" || fail "failed to download the checksum for $version"
fi

expected=$(awk 'NR == 1 { print $1 }' "$tmp_root/$checksum")
case $expected in
    ''|*[!0-9a-f]*) fail "the checksum file for $version is malformed" ;;
esac
[ "${#expected}" -eq 64 ] || fail "the checksum file for $version is malformed"
if command -v sha256sum >/dev/null 2>&1; then
    actual=$(sha256sum "$tmp_root/$archive" | awk '{ print $1 }')
elif command -v shasum >/dev/null 2>&1; then
    actual=$(shasum -a 256 "$tmp_root/$archive" | awk '{ print $1 }')
else
    fail "sha256sum or shasum is required to verify release assets"
fi
[ "$actual" = "$expected" ] || fail "checksum verification failed for $archive; no files were installed"

mkdir "$tmp_root/extracted"
tar -tzf "$tmp_root/$archive" > "$tmp_root/members" || fail "could not inspect $archive"
member_count=$(wc -l < "$tmp_root/members" | tr -d '[:space:]')
[ "$member_count" -le 10000 ] || fail "release package exceeds the 10000-entry safety limit"
tar -tvzf "$tmp_root/$archive" > "$tmp_root/member-types" || fail "could not inspect archive entry types"
while IFS= read -r member_details; do
    case $member_details in
        -*) ;;
        d*) ;;
        *) fail "release package contains a link or special file" ;;
    esac
done < "$tmp_root/member-types"
expanded_bytes=$(tar -xOzf "$tmp_root/$archive" | head -c 134217729 | wc -c | tr -d '[:space:]')
[ "$expanded_bytes" -le 134217728 ] || fail "release package exceeds the 134217728-byte extraction safety limit"
while IFS= read -r member; do
    member=${member%/}
    case $member in
        deep-review|deep-review/*) ;;
        *) fail "release package contains a path outside deep-review/" ;;
    esac
    case /$member/ in
        */../*|*/./*|*//*) fail "release package contains an unsafe path" ;;
    esac
done < "$tmp_root/members"
tar -xzf "$tmp_root/$archive" -C "$tmp_root/extracted" || fail "could not extract $archive"
package="$tmp_root/extracted/deep-review"
[ -f "$package/SKILL.md" ] || fail "release package is missing deep-review/SKILL.md"
[ -f "$package/.claude-plugin/plugin.json" ] || fail "release package is missing version metadata"
for required_dir in references scripts agents; do
    [ -d "$package/$required_dir" ] || fail "release package is missing deep-review/$required_dir/"
done
if find "$package" -type l -print | grep -q .; then
    fail "release package contains symbolic links"
fi
manifest_version=$(sed -n 's/^[[:space:]]*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)"[[:space:]]*,\{0,1\}[[:space:]]*$/\1/p' "$package/.claude-plugin/plugin.json")
[ "$manifest_version" = "${version#v}" ] || fail "release package version does not match requested version $version"

parent=${destination%/deep-review}
mkdir -p "$parent"
lock="$parent/.deep-review.install.lock"
if ! mkdir "$lock" 2>/dev/null; then
    fail "another installation is active or left $lock; verify no installer is running before removing that lock"
fi
lock_owned=true
printf '%s\n' "$$" > "$lock/owner"
stage=$(mktemp -d "$parent/.deep-review.stage.XXXXXX") || fail "could not create a staging directory beside $destination"
cp -R "$package"/. "$stage" || fail "could not stage the release package"
[ ! -e "$stage/$marker" ] || fail "release package contains the reserved activation marker"
: > "$stage/$marker"
stage_leaf=${stage##*/}

if { [ -e "$destination" ] || [ -L "$destination" ]; } && [ "$update" != true ]; then
    fail "$destination appeared while the package was being verified; no files were installed"
fi
if [ -L "$destination" ]; then
    fail "$destination became a symbolic link while the package was being verified; no files were installed"
fi
if [ -e "$destination" ] || [ -L "$destination" ]; then
    backup=$(mktemp -d "$parent/.deep-review.backup.XXXXXX") || fail "could not create a rollback directory"
    mv "$destination" "$backup/deep-review" || fail "could not move the existing installation for replacement"
fi
mv "$stage" "$destination" || fail "could not activate the staged installation"
[ -f "$destination/$marker" ] || fail "destination changed during activation; the staged package was not activated"
activation_owned=true
stage=
[ -f "$destination/SKILL.md" ] || fail "activated installation failed final validation"
rm -f -- "$destination/$marker" || fail "could not finalize the activated installation"
[ -z "$backup" ] || rm -rf -- "$backup"
backup=
activation_owned=false

case $client in
    codex) first_command='$deep-review --base main' ;;
    claude-code) first_command='/deep-review --base main' ;;
    *) first_command='Ask your client to run deep-review --base main' ;;
esac

printf 'Installed Deep Review %s\n' "$version"
printf 'Destination: %s\n' "$destination"
printf 'Verification: SHA-256 %s\n' "$actual"
printf 'First review: %s\n' "$first_command"
