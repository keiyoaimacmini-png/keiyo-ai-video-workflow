[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Repo,
    [Parameter(Mandatory)][string]$Ref,
    [Parameter(Mandatory)][string]$ExpectedCommit,
    [string]$VerificationReportPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$expectedAccount = 'keiyoaimacmini-png'
$expectedRepo = 'keiyoaimacmini-png/keiyo-ai-video-workflow'
$expectedOrigin = 'https://github.com/keiyoaimacmini-png/keiyo-ai-video-workflow.git'
$marketplaceName = 'keiyo-ai-video-workflow'
$pluginId = 'keiyo-product-video@keiyo-ai-video-workflow'
$pluginName = 'keiyo-product-video'
$pluginVersion = '1.0.0'
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$pathComparison = if ($IsWindows) { [StringComparison]::OrdinalIgnoreCase } else { [StringComparison]::Ordinal }

function Stop-Hold {
    param([string]$Code, [string]$Detail = '')
    $message = if ([string]::IsNullOrEmpty($Detail)) { $Code } else { "$Code $Detail" }
    throw $message
}

function Get-PropertyValue {
    param($Object, [string]$Name)
    if ($null -eq $Object) { return $null }
    $property = $Object.PSObject.Properties[$Name]
    if ($null -eq $property) { return $null }
    return $property.Value
}

function Invoke-Captured {
    param([Parameter(Mandatory)][string]$FilePath, [string[]]$Arguments = @())
    $startInfo = [Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $FilePath
    $startInfo.UseShellExecute = $false
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.CreateNoWindow = $true
    $startInfo.WorkingDirectory = $script:repoRoot
    foreach ($argument in $Arguments) { [void]$startInfo.ArgumentList.Add($argument) }
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $startInfo
    if (-not $process.Start()) { Stop-Hold 'HOLD_PROCESS_START_FAILED' $FilePath }
    $stdoutTask = $process.StandardOutput.ReadToEndAsync()
    $stderrTask = $process.StandardError.ReadToEndAsync()
    $process.WaitForExit()
    $result = [pscustomobject]@{
        ExitCode = $process.ExitCode
        Stdout = $stdoutTask.GetAwaiter().GetResult()
        Stderr = $stderrTask.GetAwaiter().GetResult()
    }
    $process.Dispose()
    return $result
}

function Invoke-Required {
    param([string]$FilePath, [string[]]$Arguments, [string]$HoldCode)
    $result = Invoke-Captured -FilePath $FilePath -Arguments $Arguments
    if ($result.ExitCode -ne 0) { Stop-Hold $HoldCode }
    return $result
}

function Invoke-Git {
    param([string[]]$Arguments, [string]$HoldCode = 'HOLD_GIT_COMMAND_FAILED')
    return Invoke-Required -FilePath $script:gitPath -Arguments (@('-C', $script:repoRoot) + $Arguments) -HoldCode $HoldCode
}

function ConvertFrom-JsonRequired {
    param([string]$Text, [string]$HoldCode)
    try { return $Text | ConvertFrom-Json -Depth 20 }
    catch { Stop-Hold $HoldCode }
}

function Test-RepositoryTreeSafe {
    param([string]$Root)
    $origin = Invoke-Required $script:gitPath @('-C', $Root, 'remote', 'get-url', 'origin') 'HOLD_MARKETPLACE_ORIGIN_READBACK_FAILED'
    if ($origin.Stdout.Trim() -ne $script:expectedOrigin) { Stop-Hold 'HOLD_MARKETPLACE_ORIGIN_MISMATCH' }
    $head = Invoke-Required $script:gitPath @('-C', $Root, 'rev-parse', 'HEAD') 'HOLD_MARKETPLACE_HEAD_READBACK_FAILED'
    if ($head.Stdout.Trim() -ne $script:resolvedCommit) { Stop-Hold 'HOLD_MARKETPLACE_COMMIT_MISMATCH' }
    $dirty = Invoke-Required $script:gitPath @('-C', $Root, 'status', '--porcelain=v1', '--untracked-files=all') 'HOLD_MARKETPLACE_STATUS_FAILED'
    if (-not [string]::IsNullOrWhiteSpace($dirty.Stdout)) { Stop-Hold 'HOLD_MARKETPLACE_WORKTREE_NOT_CLEAN' }
    foreach ($item in Get-ChildItem -LiteralPath $Root -Force -Recurse -ErrorAction Stop) {
        $linkType = Get-PropertyValue $item 'LinkType'
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or -not [string]::IsNullOrEmpty([string]$linkType)) {
            Stop-Hold 'HOLD_MARKETPLACE_LINK_OR_REPARSE_POINT' $item.FullName
        }
    }
}

function Get-MarketplaceRecord {
    $result = Invoke-Required $script:codexPath @('plugin', 'marketplace', 'list', '--json') 'HOLD_MARKETPLACE_LIST_FAILED'
    $payload = ConvertFrom-JsonRequired $result.Stdout 'HOLD_MARKETPLACE_READBACK_INVALID'
    $rows = @(Get-PropertyValue $payload 'marketplaces')
    $hits = @($rows | Where-Object { (Get-PropertyValue $_ 'name') -eq $script:marketplaceName })
    if ($hits.Count -gt 1) { Stop-Hold 'HOLD_DUPLICATE_MARKETPLACE' }
    if ($hits.Count -eq 0) { return $null }
    return $hits[0]
}

function Assert-MarketplaceRecord {
    param($Record)
    $source = Get-PropertyValue $Record 'marketplaceSource'
    $root = [string](Get-PropertyValue $Record 'root')
    if ((Get-PropertyValue $source 'sourceType') -ne 'git' -or
        (Get-PropertyValue $source 'source') -ne $script:expectedOrigin -or
        [string]::IsNullOrWhiteSpace($root) -or -not (Test-Path -LiteralPath $root -PathType Container)) {
        Stop-Hold 'HOLD_EXISTING_MARKETPLACE_SOURCE_MISMATCH'
    }
    $resolvedRoot = (Resolve-Path -LiteralPath $root).Path
    Test-RepositoryTreeSafe $resolvedRoot
    return $resolvedRoot
}

function Get-PluginRecord {
    $result = Invoke-Required $script:codexPath @('plugin', 'list', '--json') 'HOLD_PLUGIN_LIST_FAILED'
    $payload = ConvertFrom-JsonRequired $result.Stdout 'HOLD_PLUGIN_READBACK_INVALID'
    $rows = @(Get-PropertyValue $payload 'installed')
    $hits = @($rows | Where-Object { (Get-PropertyValue $_ 'pluginId') -eq $script:pluginId })
    if ($hits.Count -gt 1) { Stop-Hold 'HOLD_DUPLICATE_PLUGIN' }
    if ($hits.Count -eq 0) { return $null }
    return $hits[0]
}

function Assert-PluginRecord {
    param($Record, [string]$MarketplaceRoot)
    $source = Get-PropertyValue $Record 'source'
    $market = Get-PropertyValue $Record 'marketplaceSource'
    $pluginPath = [string](Get-PropertyValue $source 'path')
    $valid = (
        (Get-PropertyValue $Record 'name') -eq $script:pluginName -and
        (Get-PropertyValue $Record 'marketplaceName') -eq $script:marketplaceName -and
        (Get-PropertyValue $Record 'version') -eq $script:pluginVersion -and
        (Get-PropertyValue $Record 'installed') -eq $true -and
        (Get-PropertyValue $Record 'enabled') -eq $true -and
        (Get-PropertyValue $source 'source') -eq 'local' -and
        -not [string]::IsNullOrWhiteSpace($pluginPath) -and
        (Get-PropertyValue $market 'sourceType') -eq 'git' -and
        (Get-PropertyValue $market 'source') -eq $script:expectedOrigin
    )
    if (-not $valid -or -not (Test-Path -LiteralPath $pluginPath -PathType Container)) {
        Stop-Hold 'HOLD_EXISTING_PLUGIN_READBACK_MISMATCH'
    }
    $resolvedPluginPath = (Resolve-Path -LiteralPath $pluginPath).Path
    $expectedPluginPath = (Resolve-Path -LiteralPath (Join-Path $MarketplaceRoot 'plugins/keiyo-product-video')).Path
    if (-not $resolvedPluginPath.Equals($expectedPluginPath, $script:pathComparison)) {
        Stop-Hold 'HOLD_PLUGIN_SOURCE_PATH_MISMATCH'
    }
    $rootPrefix = $MarketplaceRoot.TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
    if (-not $resolvedPluginPath.StartsWith($rootPrefix, $script:pathComparison)) {
        Stop-Hold 'HOLD_PLUGIN_SOURCE_OUTSIDE_MARKETPLACE'
    }
    return $resolvedPluginPath
}

function Get-ManifestEntries {
    param([string]$ManifestPath)
    $entries = @{}
    foreach ($line in [IO.File]::ReadAllLines($ManifestPath, [Text.Encoding]::UTF8)) {
        if ($line -notmatch '^([0-9a-f]{64})  (.+)$' -or $entries.ContainsKey($Matches[2])) {
            Stop-Hold 'HOLD_MANIFEST_READBACK_INVALID'
        }
        $entries[$Matches[2]] = $Matches[1]
    }
    return $entries
}

function Assert-InstalledHashes {
    param([string]$MarketplaceRoot, [string]$PluginPath)
    $releaseManifest = Join-Path $script:repoRoot 'MANIFEST.sha256'
    $snapshotManifest = Join-Path $MarketplaceRoot 'MANIFEST.sha256'
    if ((Get-FileHash -LiteralPath $releaseManifest -Algorithm SHA256).Hash -ne (Get-FileHash -LiteralPath $snapshotManifest -Algorithm SHA256).Hash) {
        Stop-Hold 'HOLD_INSTALLED_MANIFEST_MISMATCH'
    }
    $entries = Get-ManifestEntries $releaseManifest
    $files = [ordered]@{
        'plugins/keiyo-product-video/.codex-plugin/plugin.json' = '.codex-plugin/plugin.json'
        'plugins/keiyo-product-video/skills/create-tiktok-product-video/SKILL.md' = 'skills/create-tiktok-product-video/SKILL.md'
        'plugins/keiyo-product-video/skills/create-tiktok-product-video/agents/openai.yaml' = 'skills/create-tiktok-product-video/agents/openai.yaml'
        'plugins/keiyo-product-video/skills/create-tiktok-product-video/references/payload_contract.md' = 'skills/create-tiktok-product-video/references/payload_contract.md'
        'plugins/keiyo-product-video/skills/create-tiktok-product-video/scripts/validate_product_video_payload.py' = 'skills/create-tiktok-product-video/scripts/validate_product_video_payload.py'
    }
    foreach ($relative in $files.Keys) {
        if (-not $entries.ContainsKey($relative)) { Stop-Hold 'HOLD_INSTALLED_HASH_ENTRY_MISSING' $relative }
        foreach ($candidate in @((Join-Path $script:repoRoot $relative), (Join-Path $MarketplaceRoot $relative), (Join-Path $PluginPath $files[$relative]))) {
            if (-not (Test-Path -LiteralPath $candidate -PathType Leaf) -or
                (Get-FileHash -LiteralPath $candidate -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entries[$relative]) {
                Stop-Hold 'HOLD_INSTALLED_FILE_HASH_MISMATCH' $relative
            }
        }
    }
}

try {
    # Input, command, authentication, repository, ref, and worktree checks all
    # complete before the first marketplace/plugin mutation.
    if ($Repo -ne $expectedRepo) { Stop-Hold 'HOLD_REPOSITORY_MISMATCH' }
    if ([string]::IsNullOrWhiteSpace($Ref) -or $Ref -notmatch '^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$' -or
        $Ref.Contains('..') -or $Ref.Contains('//') -or $Ref.EndsWith('/') -or $Ref.EndsWith('.lock')) {
        Stop-Hold 'HOLD_RELEASE_REF_INVALID'
    }
    if ($ExpectedCommit -notmatch '^[0-9a-fA-F]{40}$') {
        Stop-Hold 'HOLD_EXPECTED_COMMIT_INVALID'
    }

    $requiredCommands = @{}
    foreach ($name in @('codex', 'gh', 'git')) {
        $command = Get-Command $name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($null -eq $command) { Stop-Hold 'HOLD_COMMAND_MISSING' $name }
        $requiredCommands[$name] = $command.Source
    }
    $codexPath = $requiredCommands['codex']
    $ghPath = $requiredCommands['gh']
    $gitPath = $requiredCommands['git']

    # Authentication remains user-owned: this is the read-only equivalent of
    # `gh auth status`; the script never accepts or stores a token.
    $authStatus = Invoke-Captured $ghPath @('auth', 'status')
    if ($authStatus.ExitCode -ne 0) { Stop-Hold 'HOLD_GITHUB_AUTH_REQUIRED' }
    $account = Invoke-Required $ghPath @('api', 'user', '--jq', '.login') 'HOLD_GITHUB_ACCOUNT_LOOKUP_FAILED'
    if ($account.Stdout.Trim() -ne $expectedAccount) { Stop-Hold 'HOLD_GITHUB_ACCOUNT_MISMATCH' }

    $repoResult = Invoke-Required $ghPath @('repo', 'view', $expectedRepo, '--json', 'nameWithOwner,isPrivate,defaultBranchRef,url') 'HOLD_REPOSITORY_METADATA_FAILED'
    $repoMetadata = ConvertFrom-JsonRequired $repoResult.Stdout 'HOLD_REPOSITORY_METADATA_INVALID'
    if ((Get-PropertyValue $repoMetadata 'nameWithOwner') -ne $expectedRepo -or
        (Get-PropertyValue $repoMetadata 'isPrivate') -ne $true -or
        (Get-PropertyValue (Get-PropertyValue $repoMetadata 'defaultBranchRef') 'name') -ne 'main' -or
        (Get-PropertyValue $repoMetadata 'url') -ne 'https://github.com/keiyoaimacmini-png/keiyo-ai-video-workflow') {
        Stop-Hold 'HOLD_PRIVATE_REPOSITORY_METADATA_MISMATCH'
    }

    $origin = Invoke-Git @('remote', 'get-url', 'origin') 'HOLD_LOCAL_ORIGIN_LOOKUP_FAILED'
    if ($origin.Stdout.Trim() -ne $expectedOrigin) { Stop-Hold 'HOLD_LOCAL_ORIGIN_MISMATCH' }
    $dirty = Invoke-Git @('status', '--porcelain=v1', '--untracked-files=all') 'HOLD_LOCAL_STATUS_FAILED'
    if (-not [string]::IsNullOrWhiteSpace($dirty.Stdout)) { Stop-Hold 'HOLD_WORKTREE_NOT_CLEAN' }
    $head = (Invoke-Git @('rev-parse', 'HEAD') 'HOLD_LOCAL_HEAD_LOOKUP_FAILED').Stdout.Trim()
    $resolvedCommit = (Invoke-Git @('rev-parse', "${Ref}^{commit}") 'HOLD_LOCAL_REF_LOOKUP_FAILED').Stdout.Trim()
    if ($head -ne $resolvedCommit) { Stop-Hold 'HOLD_HEAD_REF_MISMATCH' }
    if ($resolvedCommit -ne $ExpectedCommit.ToLowerInvariant()) {
        Stop-Hold 'HOLD_EXPECTED_COMMIT_MISMATCH'
    }

    if ($Ref -match '^[0-9a-fA-F]{40}$') {
        $remoteCommit = (Invoke-Required $ghPath @('api', "repos/$expectedRepo/commits/$Ref", '--jq', '.sha') 'HOLD_REMOTE_COMMIT_LOOKUP_FAILED').Stdout.Trim()
    }
    else {
        $remote = Invoke-Git @('ls-remote', 'origin', "refs/heads/$Ref", "refs/tags/$Ref", "refs/tags/$Ref^{}") 'HOLD_REMOTE_REF_LOOKUP_FAILED'
        $remoteRows = @{}
        foreach ($line in $remote.Stdout -split "`r?`n") {
            if ($line -match '^([0-9a-f]{40})\s+(.+)$') { $remoteRows[$Matches[2]] = $Matches[1] }
        }
        $remoteCommit = if ($remoteRows.ContainsKey("refs/tags/$Ref^{}")) { $remoteRows["refs/tags/$Ref^{}"] }
            elseif ($remoteRows.ContainsKey("refs/heads/$Ref")) { $remoteRows["refs/heads/$Ref"] }
            elseif ($remoteRows.ContainsKey("refs/tags/$Ref")) { $remoteRows["refs/tags/$Ref"] }
            else { $null }
    }
    if ($remoteCommit -ne $resolvedCommit) { Stop-Hold 'HOLD_REMOTE_REF_COMMIT_MISMATCH' }

    if ([string]::IsNullOrWhiteSpace($VerificationReportPath)) {
        $VerificationReportPath = Join-Path (Join-Path ([IO.Path]::GetTempPath()) 'keiyo-ai-video-workflow') ("bootstrap-pre-{0}-{1}.json" -f ([DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')), $PID)
    }
    $currentPowerShell = [Environment]::ProcessPath
    if ([string]::IsNullOrWhiteSpace($currentPowerShell)) { Stop-Hold 'HOLD_POWERSHELL_PATH_UNKNOWN' }
    $verifyScript = Join-Path $PSScriptRoot 'verify-windows.ps1'
    $verify = Invoke-Captured $currentPowerShell @('-NoLogo', '-NoProfile', '-File', $verifyScript, '-ReportPath', $VerificationReportPath)
    if ($verify.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $VerificationReportPath -PathType Leaf)) {
        Stop-Hold 'HOLD_WINDOWS_VERIFICATION_FAILED'
    }
    $verification = ConvertFrom-JsonRequired ([IO.File]::ReadAllText($VerificationReportPath, [Text.Encoding]::UTF8)) 'HOLD_WINDOWS_VERIFICATION_REPORT_INVALID'
    if ((Get-PropertyValue $verification 'status') -ne 'PASS' -or
        (Get-PropertyValue (Get-PropertyValue $verification 'repository') 'head') -ne $resolvedCommit) {
        Stop-Hold 'HOLD_WINDOWS_VERIFICATION_READBACK_MISMATCH'
    }

    # Inspect every existing installation before the first mutation. A partial or
    # mismatched prior installation is a HOLD, never something to overwrite.
    $marketplace = Get-MarketplaceRecord
    $plugin = Get-PluginRecord
    if ($null -ne $plugin -and $null -eq $marketplace) {
        Stop-Hold 'HOLD_EXISTING_PLUGIN_WITHOUT_MARKETPLACE'
    }
    if ($null -ne $marketplace) {
        $marketplaceRoot = Assert-MarketplaceRecord $marketplace
        if ($null -ne $plugin) {
            $pluginPath = Assert-PluginRecord $plugin $marketplaceRoot
            Assert-InstalledHashes $marketplaceRoot $pluginPath
        }
    }

    # First mutation is below this line, and only occurs after PASS verification
    # and validation of all existing Codex installation state.
    if ($null -eq $marketplace) {
        [void](Invoke-Required $codexPath @('plugin', 'marketplace', 'add', $expectedRepo, '--ref', $resolvedCommit) 'HOLD_MARKETPLACE_ADD_FAILED')
        $marketplace = Get-MarketplaceRecord
        if ($null -eq $marketplace) { Stop-Hold 'HOLD_MARKETPLACE_ADD_READBACK_FAILED' }
    }
    $marketplaceRoot = Assert-MarketplaceRecord $marketplace

    if ($null -eq $plugin) {
        [void](Invoke-Required $codexPath @('plugin', 'add', $pluginId) 'HOLD_PLUGIN_ADD_FAILED')
        $plugin = Get-PluginRecord
        if ($null -eq $plugin) { Stop-Hold 'HOLD_PLUGIN_ADD_READBACK_FAILED' }
    }
    $pluginPath = Assert-PluginRecord $plugin $marketplaceRoot
    Assert-InstalledHashes $marketplaceRoot $pluginPath

    $postReportPath = Join-Path (Split-Path -Parent ([IO.Path]::GetFullPath($VerificationReportPath))) ("bootstrap-post-{0}-{1}.json" -f ([DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')), $PID)
    $postVerify = Invoke-Captured $currentPowerShell @('-NoLogo', '-NoProfile', '-File', $verifyScript, '-ReportPath', $postReportPath)
    if ($postVerify.ExitCode -ne 0) { Stop-Hold 'HOLD_POST_INSTALL_VERIFICATION_FAILED' }
    $postVerification = ConvertFrom-JsonRequired ([IO.File]::ReadAllText($postReportPath, [Text.Encoding]::UTF8)) 'HOLD_POST_INSTALL_REPORT_INVALID'
    if ((Get-PropertyValue $postVerification 'status') -ne 'PASS' -or
        (Get-PropertyValue (Get-PropertyValue $postVerification 'repository') 'head') -ne $resolvedCommit) {
        Stop-Hold 'HOLD_POST_INSTALL_READBACK_MISMATCH'
    }

    Write-Output "PASS_PLUGIN_INSTALLED commit=$resolvedCommit version=$pluginVersion pre_report=$VerificationReportPath post_report=$postReportPath"
    Write-Output 'Start a new Codex task before using $create-tiktok-product-video.'
    Write-Output 'Sol Advisor, CapCut, Google Drive, export, publication, and paid operations are outside this bootstrap.'
    exit 0
}
catch {
    [Console]::Error.WriteLine([string]$_.Exception.Message)
    exit 3
}
