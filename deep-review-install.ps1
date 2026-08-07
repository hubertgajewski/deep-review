[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $Client,
    [Parameter(Mandatory = $true)]
    [ValidateSet("User", "Project")]
    [string] $Scope,
    [Parameter(Mandatory = $true)]
    [string] $Version,
    [switch] $Update,
    [string] $AssetDirectory
)

$ErrorActionPreference = "Stop"
$PackageBaseUrl = "https://gitlab.com/api/v4/projects/84183178/packages/generic/deep-review"

function Receive-BoundedAsset {
    param(
        [Parameter(Mandatory = $true)] [uri] $Uri,
        [Parameter(Mandatory = $true)] [string] $DestinationPath,
        [Parameter(Mandatory = $true)] [long] $MaximumBytes
    )

    $Client = [System.Net.Http.HttpClient]::new()
    $Response = $null
    $InputStream = $null
    $OutputStream = $null
    try {
        $Response = $Client.GetAsync(
            $Uri, [System.Net.Http.HttpCompletionOption]::ResponseHeadersRead
        ).GetAwaiter().GetResult()
        $Response.EnsureSuccessStatusCode() | Out-Null
        if ($Response.Content.Headers.ContentLength -gt $MaximumBytes) {
            throw "Download exceeds the $MaximumBytes-byte safety limit: $Uri"
        }
        $InputStream = $Response.Content.ReadAsStreamAsync().GetAwaiter().GetResult()
        $OutputStream = [System.IO.File]::Create($DestinationPath)
        $Buffer = [byte[]]::new(65536)
        [long] $Total = 0
        while (($Read = $InputStream.Read($Buffer, 0, $Buffer.Length)) -gt 0) {
            $Total += $Read
            if ($Total -gt $MaximumBytes) {
                throw "Download exceeds the $MaximumBytes-byte safety limit: $Uri"
            }
            $OutputStream.Write($Buffer, 0, $Read)
        }
    }
    finally {
        if ($OutputStream) { $OutputStream.Dispose() }
        if ($InputStream) { $InputStream.Dispose() }
        if ($Response) { $Response.Dispose() }
        $Client.Dispose()
    }
}

if ($Version -cnotmatch '^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$') {
    throw "-Version must be a semantic version such as v1.1.0"
}

# Generated from release-contract.json; tests require an exact match.
$ClientRootEntries = "amp=.agents/skills codex=.agents/skills cursor=.agents/skills devin=.agents/skills gemini=.agents/skills github-copilot=.agents/skills antigravity=.agents/skills goose=.agents/skills opencode=.agents/skills openhands=.agents/skills warp=.agents/skills windsurf=.agents/skills claude-code=.claude/skills cline=.cline/skills grok=.grok/skills junie=.junie/skills kiro=.kiro/skills mistral=.vibe/skills qwen=.qwen/skills"
$UnsupportedClientEntries = "t3 claude-chat claude-cowork"
$ClientRoots = @{}
foreach ($Entry in $ClientRootEntries.Split(" ", [System.StringSplitOptions]::RemoveEmptyEntries)) {
    $Parts = $Entry.Split("=", 2)
    $ClientRoots[$Parts[0]] = $Parts[1]
}
$UnsupportedClients = $UnsupportedClientEntries.Split(
    " ", [System.StringSplitOptions]::RemoveEmptyEntries
)
$Client = $Client.ToLowerInvariant()

if ($ClientRoots.ContainsKey($Client)) {
    $SkillRoot = $ClientRoots[$Client]
} elseif ($UnsupportedClients -contains $Client) {
    throw "Client '$Client' has no deterministic local destination. See https://gitlab.com/hubertgajewski-ai/deep-review/-/blob/main/docs/installation.md#other-installation-environments"
} else {
    throw "Unsupported client '$Client'. See the installation guide for supported client IDs."
}

if ($Scope -eq "User") {
    if ([string]::IsNullOrWhiteSpace($HOME)) {
        throw "HOME is not set; cannot resolve the user installation directory"
    }
    $Root = $HOME
} else {
    $Root = (Get-Location).Path
}
$Destination = Join-Path (Join-Path $Root $SkillRoot) "deep-review"
$Existing = Get-Item -LiteralPath $Destination -Force -ErrorAction SilentlyContinue
if ($null -ne $Existing -and -not $Update) {
    throw "$Destination already exists; inspect the new release, then rerun with -Update to replace it"
}
if ($null -ne $Existing -and
    0 -ne ($Existing.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
    throw "$Destination is a symbolic link or reparse point; replace it manually before using -Update"
}

$Archive = "deep-review-$Version.zip"
$Checksum = "$Archive.sha256"
$TemporaryRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("deep-review-install-" + [guid]::NewGuid())
$Stage = $null
$Backup = $null
$Activated = $false
$ActivationOwned = $false
$Lock = $null
$LockOwned = $false
$MarkerName = ".deep-review-installing"
$StageLeaf = $null

try {
    New-Item -ItemType Directory -Path $TemporaryRoot | Out-Null
    $ArchivePath = Join-Path $TemporaryRoot $Archive
    $ChecksumPath = Join-Path $TemporaryRoot $Checksum

    if ($AssetDirectory) {
        $OfflineArchive = Join-Path $AssetDirectory $Archive
        $OfflineChecksum = Join-Path $AssetDirectory $Checksum
        if (-not (Test-Path -LiteralPath $OfflineArchive -PathType Leaf)) {
            throw "Offline archive not found: $OfflineArchive"
        }
        if (-not (Test-Path -LiteralPath $OfflineChecksum -PathType Leaf)) {
            throw "Offline checksum not found: $OfflineChecksum"
        }
        Copy-Item -LiteralPath $OfflineArchive -Destination $ArchivePath
        Copy-Item -LiteralPath $OfflineChecksum -Destination $ChecksumPath
    } else {
        $PackageVersion = $Version.Substring(1)
        $AssetUrl = "$PackageBaseUrl/$PackageVersion"
        try {
            Receive-BoundedAsset -Uri "$AssetUrl/$Archive" -DestinationPath $ArchivePath -MaximumBytes 67108864
            Receive-BoundedAsset -Uri "$AssetUrl/$Checksum" -DestinationPath $ChecksumPath -MaximumBytes 4096
        } catch {
            throw "Failed to download release assets for $Version`: $($_.Exception.Message)"
        }
    }

    $Expected = ((Get-Content -LiteralPath $ChecksumPath -TotalCount 1) -split '\s+')[0]
    if ($Expected -cnotmatch '^[0-9a-f]{64}$') {
        throw "The checksum file for $Version is malformed"
    }
    $Actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $ArchivePath).Hash.ToLowerInvariant()
    if ($Actual -cne $Expected) {
        throw "Checksum verification failed for $Archive; no files were installed"
    }

    $Zip = [System.IO.Compression.ZipFile]::OpenRead($ArchivePath)
    try {
        if ($Zip.Entries.Count -gt 10000) {
            throw "Release package exceeds the 10000-entry safety limit"
        }
        [long] $ExpandedBytes = 0
        foreach ($Entry in $Zip.Entries) {
            $EntryPath = $Entry.FullName.Replace("\", "/")
            $Parts = $EntryPath.Split("/", [System.StringSplitOptions]::RemoveEmptyEntries)
            if ($EntryPath.StartsWith("/") -or $Parts.Count -eq 0 -or $Parts[0] -cne "deep-review" -or
                $Parts -contains ".." -or $Parts -contains ".") {
                throw "Release package contains an unsafe path: $EntryPath"
            }
            $ExpandedBytes += $Entry.Length
            if ($ExpandedBytes -gt 134217728) {
                throw "Release package exceeds the 134217728-byte extraction safety limit"
            }
        }
    }
    finally {
        $Zip.Dispose()
    }
    $Extracted = Join-Path $TemporaryRoot "extracted"
    Expand-Archive -LiteralPath $ArchivePath -DestinationPath $Extracted
    $Package = Join-Path $Extracted "deep-review"
    if (-not (Test-Path -LiteralPath (Join-Path $Package "SKILL.md") -PathType Leaf)) {
        throw "Release package is missing deep-review/SKILL.md"
    }
    $ManifestPath = Join-Path $Package ".claude-plugin/plugin.json"
    if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf)) {
        throw "Release package is missing version metadata"
    }
    foreach ($RequiredDirectory in @("references", "scripts", "agents")) {
        if (-not (Test-Path -LiteralPath (Join-Path $Package $RequiredDirectory) -PathType Container)) {
            throw "Release package is missing deep-review/$RequiredDirectory/"
        }
    }
    $Links = Get-ChildItem -LiteralPath $Package -Recurse -Force | Where-Object {
        0 -ne ($_.Attributes -band [System.IO.FileAttributes]::ReparsePoint)
    }
    if ($Links) {
        throw "Release package contains symbolic links or reparse points"
    }
    try {
        $ManifestVersion = (Get-Content -Raw -LiteralPath $ManifestPath | ConvertFrom-Json).version
    } catch {
        throw "Release package version metadata is malformed"
    }
    if ($ManifestVersion -cne $Version.Substring(1)) {
        throw "Release package version does not match requested version $Version"
    }

    $Parent = Split-Path -Parent $Destination
    New-Item -ItemType Directory -Force -Path $Parent | Out-Null
    $Stage = Join-Path $Parent (".deep-review.stage." + [guid]::NewGuid())
    $Lock = Join-Path $Parent ".deep-review.install.lock"
    try {
        New-Item -ItemType Directory -Path $Lock | Out-Null
        $LockOwned = $true
        Set-Content -LiteralPath (Join-Path $Lock "owner") -Value $PID -NoNewline
    } catch {
        throw "Another installation is active or left $Lock; verify no installer is running before removing that lock"
    }
    New-Item -ItemType Directory -Path $Stage | Out-Null
    Get-ChildItem -LiteralPath $Package -Force | Copy-Item -Recurse -Force -Destination $Stage
    $MarkerPath = Join-Path $Stage $MarkerName
    if (Test-Path -LiteralPath $MarkerPath) {
        throw "Release package contains the reserved activation marker"
    }
    New-Item -ItemType File -Path $MarkerPath | Out-Null
    $StageLeaf = Split-Path -Leaf $Stage

    $CurrentDestination = Get-Item -LiteralPath $Destination -Force -ErrorAction SilentlyContinue
    if ($null -ne $CurrentDestination -and -not $Update) {
        throw "$Destination appeared while the package was being verified; no files were installed"
    }
    if ($null -ne $CurrentDestination -and
        0 -ne ($CurrentDestination.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
        throw "$Destination became a symbolic link or reparse point while the package was being verified; no files were installed"
    }
    if ($null -ne $CurrentDestination) {
        $Backup = Join-Path $Parent (".deep-review.backup." + [guid]::NewGuid())
        New-Item -ItemType Directory -Path $Backup | Out-Null
        Move-Item -LiteralPath $Destination -Destination (Join-Path $Backup "deep-review")
    }
    Move-Item -LiteralPath $Stage -Destination $Destination
    $ActivatedMarker = Join-Path $Destination $MarkerName
    if (-not (Test-Path -LiteralPath $ActivatedMarker -PathType Leaf)) {
        throw "Destination changed during activation; the staged package was not activated"
    }
    $ActivationOwned = $true
    $Stage = $null
    if (-not (Test-Path -LiteralPath (Join-Path $Destination "SKILL.md") -PathType Leaf)) {
        throw "Activated installation failed final validation"
    }
    Remove-Item -Force -LiteralPath $ActivatedMarker
    $ActivationOwned = $false
    $Activated = $true
    if ($Backup) {
        try {
            Remove-Item -Recurse -Force -LiteralPath $Backup
            $Backup = $null
        } catch {
            Write-Warning "Installed successfully, but the previous installation could not be removed from $(Join-Path $Backup 'deep-review')"
        }
    }

    if ($Client -eq "codex") {
        $FirstCommand = '$deep-review --base main'
    } elseif ($Client -eq "claude-code") {
        $FirstCommand = '/deep-review --base main'
    } else {
        $FirstCommand = 'Ask your client to run deep-review --base main'
    }

    Write-Output "Installed Deep Review $Version"
    Write-Output "Destination: $Destination"
    Write-Output "Verification: SHA-256 $Actual"
    Write-Output "First review: $FirstCommand"
}
catch {
    if (-not $Activated -and $ActivationOwned -and
        (Test-Path -LiteralPath (Join-Path $Destination $MarkerName) -PathType Leaf)) {
        Remove-Item -Recurse -Force -LiteralPath $Destination -ErrorAction SilentlyContinue
    }
    if (-not $Activated -and $StageLeaf) {
        $NestedStage = Join-Path $Destination $StageLeaf
        if (Test-Path -LiteralPath (Join-Path $NestedStage $MarkerName) -PathType Leaf) {
            Remove-Item -Recurse -Force -LiteralPath $NestedStage -ErrorAction SilentlyContinue
        }
    }
    if (-not $Activated -and $Backup) {
        $BackedUpDestination = Join-Path $Backup "deep-review"
        if ((Test-Path -LiteralPath $BackedUpDestination) -and -not (Test-Path -LiteralPath $Destination)) {
            Move-Item -LiteralPath $BackedUpDestination -Destination $Destination -ErrorAction SilentlyContinue
        }
    }
    throw
}
finally {
    if ($Stage) {
        Remove-Item -Recurse -Force -LiteralPath $Stage -ErrorAction SilentlyContinue
    }
    if ($Backup -and -not (Test-Path -LiteralPath (Join-Path $Backup "deep-review"))) {
        Remove-Item -Recurse -Force -LiteralPath $Backup -ErrorAction SilentlyContinue
    }
    if ($Backup -and (Test-Path -LiteralPath (Join-Path $Backup "deep-review"))) {
        Write-Warning "Previous installation preserved at $(Join-Path $Backup 'deep-review')"
    }
    if ($LockOwned -and $Lock) {
        Remove-Item -Force -LiteralPath (Join-Path $Lock "owner") -ErrorAction SilentlyContinue
        Remove-Item -Force -LiteralPath $Lock -ErrorAction SilentlyContinue
    }
    Remove-Item -Recurse -Force -LiteralPath $TemporaryRoot -ErrorAction SilentlyContinue
}
