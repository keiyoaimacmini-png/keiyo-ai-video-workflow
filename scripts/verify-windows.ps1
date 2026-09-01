[CmdletBinding()]
param(
    [Alias('ResultPath')]
    [string]$ReportPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$schemaVersion = 'keiyo.windows-verification.v1'
$startedAt = [DateTime]::UtcNow
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$isWindowsPlatform = [Runtime.InteropServices.RuntimeInformation]::IsOSPlatform(
    [Runtime.InteropServices.OSPlatform]::Windows
)
if (-not $isWindowsPlatform) { throw 'HOLD_WINDOWS_REQUIRED' }
if ($PSVersionTable.PSVersion.Major -lt 7) { throw 'HOLD_POWERSHELL_7_REQUIRED' }
$pathComparison = [StringComparison]::OrdinalIgnoreCase

function Test-PathInside {
    param([string]$Child, [string]$Parent)
    $childFull = [IO.Path]::GetFullPath($Child)
    $parentFull = [IO.Path]::GetFullPath($Parent).TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar)
    return $childFull.StartsWith($parentFull + [IO.Path]::DirectorySeparatorChar, $script:pathComparison)
}

function Get-OutputLines {
    param([AllowEmptyString()][string]$Text)
    if ([string]::IsNullOrEmpty($Text)) { return @() }
    return @($Text -split "`r?`n" | Where-Object { $_ -ne '' })
}

function Resolve-PythonCommand {
    param([hashtable]$Environment)
    $candidates = @(
        [pscustomobject]@{ Name = 'py'; Prefix = @('-3.12') },
        [pscustomobject]@{ Name = 'python'; Prefix = @() },
        [pscustomobject]@{ Name = 'python3'; Prefix = @() }
    )
    foreach ($candidate in $candidates) {
        $command = Get-Command $candidate.Name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($null -ne $command) {
            try {
                $probe = Invoke-Captured -FilePath $command.Source -Arguments (@($candidate.Prefix) + @('--version')) -Environment $Environment -RemoveEnvironment @('PYTHONINTMAXSTRDIGITS')
            }
            catch {
                continue
            }
            $version = ($probe.Stdout + $probe.Stderr).Trim()
            if ($probe.ExitCode -eq 0 -and $version -match '^Python 3\.12(?:\.|$)') {
                return [pscustomobject]@{
                    Path = $command.Source
                    Prefix = @($candidate.Prefix)
                    Version = $version
                }
            }
        }
    }
    throw 'HOLD_PYTHON_3_12_REQUIRED'
}

function Invoke-Captured {
    param(
        [Parameter(Mandatory)][string]$FilePath,
        [string[]]$Arguments = @(),
        [hashtable]$Environment = @{},
        [string[]]$RemoveEnvironment = @()
    )
    $startInfo = [Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $FilePath
    $startInfo.UseShellExecute = $false
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.CreateNoWindow = $true
    $startInfo.WorkingDirectory = $script:repoRoot
    foreach ($argument in $Arguments) { [void]$startInfo.ArgumentList.Add($argument) }
    foreach ($name in $RemoveEnvironment) { [void]$startInfo.Environment.Remove($name) }
    foreach ($name in $Environment.Keys) { $startInfo.Environment[$name] = [string]$Environment[$name] }
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $startInfo
    if (-not $process.Start()) { throw "HOLD_PROCESS_START_FAILED $FilePath" }
    $stdoutTask = $process.StandardOutput.ReadToEndAsync()
    $stderrTask = $process.StandardError.ReadToEndAsync()
    $process.WaitForExit()
    $stdout = $stdoutTask.GetAwaiter().GetResult()
    $stderr = $stderrTask.GetAwaiter().GetResult()
    $exitCode = $process.ExitCode
    $process.Dispose()
    return [pscustomobject]@{ ExitCode = $exitCode; Stdout = $stdout; Stderr = $stderr }
}

function Invoke-Git {
    param([string[]]$Arguments)
    return Invoke-Captured -FilePath $script:gitPath -Arguments (@('-C', $script:repoRoot) + $Arguments)
}

function Get-RepositoryCaches {
    $gitPrefix = [IO.Path]::GetFullPath((Join-Path $script:repoRoot '.git')).TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
    $hits = [Collections.Generic.List[string]]::new()
    foreach ($item in Get-ChildItem -LiteralPath $script:repoRoot -Force -Recurse -ErrorAction Stop) {
        $full = [IO.Path]::GetFullPath($item.FullName)
        if ($full.StartsWith($gitPrefix, $script:pathComparison)) { continue }
        if (($item.PSIsContainer -and $item.Name -eq '__pycache__') -or
            (-not $item.PSIsContainer -and $item.Extension -in @('.pyc', '.pyo'))) {
            [void]$hits.Add([IO.Path]::GetRelativePath($script:repoRoot, $full).Replace('\', '/'))
        }
    }
    return @($hits | Sort-Object -Unique)
}

function New-CheckResult {
    param([string]$Name, [string[]]$Command, $Invocation)
    if ($null -eq $Invocation) {
        return [ordered]@{ name = $Name; status = 'NOT_RUN'; exit_code = $null; command = $Command; stdout = @(); stderr = @() }
    }
    return [ordered]@{
        name = $Name
        status = if ($Invocation.ExitCode -eq 0) { 'PASS' } else { 'FAIL' }
        exit_code = $Invocation.ExitCode
        command = $Command
        stdout = @(Get-OutputLines $Invocation.Stdout)
        stderr = @(Get-OutputLines $Invocation.Stderr)
    }
}

$defaultDirectory = Join-Path ([IO.Path]::GetTempPath()) 'keiyo-ai-video-workflow'
if ([string]::IsNullOrWhiteSpace($ReportPath)) {
    $ReportPath = Join-Path $defaultDirectory ("verify-windows-{0}-{1}.json" -f $startedAt.ToString('yyyyMMddTHHmmssZ'), $PID)
}
$ReportPath = [IO.Path]::GetFullPath($ReportPath)
if (([IO.Path]::GetExtension($ReportPath)) -ne '.json') { throw 'HOLD_RESULT_PATH_MUST_BE_JSON' }
if (Test-PathInside -Child $ReportPath -Parent $repoRoot) { throw 'HOLD_RESULT_PATH_INSIDE_REPOSITORY' }
$resultDirectory = Split-Path -Parent $ReportPath
[IO.Directory]::CreateDirectory($resultDirectory) | Out-Null

$pycachePrefix = Join-Path $defaultDirectory ("pycache-{0}-{1}" -f $PID, [Guid]::NewGuid().ToString('N'))
if (Test-PathInside -Child $pycachePrefix -Parent $repoRoot) { throw 'HOLD_PYCACHE_PREFIX_INSIDE_REPOSITORY' }

$gitCommand = Get-Command git -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
if ($null -eq $gitCommand) { throw 'HOLD_COMMAND_MISSING git' }
$gitPath = $gitCommand.Source

$basePythonEnvironment = @{
    PYTHONUTF8 = '1'
    PYTHONIOENCODING = 'utf-8'
    PYTHONPYCACHEPREFIX = $pycachePrefix
    PYTHONDONTWRITEBYTECODE = '1'
}
$python = Resolve-PythonCommand -Environment $basePythonEnvironment

$headResult = Invoke-Git @('rev-parse', 'HEAD')
$branchResult = Invoke-Git @('branch', '--show-current')
$startDirtyResult = Invoke-Git @('status', '--porcelain=v1', '--untracked-files=all')
if ($headResult.ExitCode -ne 0 -or $branchResult.ExitCode -ne 0 -or $startDirtyResult.ExitCode -ne 0) {
    throw 'HOLD_GIT_PREFLIGHT_FAILED'
}
$head = $headResult.Stdout.Trim()
$branch = $branchResult.Stdout.Trim()
$startDirty = @(Get-OutputLines $startDirtyResult.Stdout)
$startCaches = @(Get-RepositoryCaches)
$preflightPassed = ($startDirty.Count -eq 0 -and $startCaches.Count -eq 0)

$pythonVersion = $python.Version

$definitions = @(
    [ordered]@{ Name = 'package'; Arguments = @('scripts/verify_package.py'); Environment = $basePythonEnvironment },
    [ordered]@{ Name = 'golden_baseline_v2'; Arguments = @('scripts/verify_golden_baseline_v2.py'); Environment = $basePythonEnvironment },
    [ordered]@{ Name = 'payload_self_test'; Arguments = @('plugins/keiyo-product-video/skills/create-tiktok-product-video/scripts/validate_product_video_payload.py', '--self-test'); Environment = ($basePythonEnvironment.Clone()) },
    [ordered]@{ Name = 'unittest'; Arguments = @('-m', 'unittest', 'discover', '-s', 'tests', '-v'); Environment = $basePythonEnvironment }
)
$definitions[2].Environment['PYTHONINTMAXSTRDIGITS'] = '0'

$checks = [Collections.Generic.List[object]]::new()
foreach ($definition in $definitions) {
    $displayCommand = @('python') + @($definition.Arguments)
    if (-not $preflightPassed) {
        [void]$checks.Add((New-CheckResult -Name $definition.Name -Command $displayCommand -Invocation $null))
        continue
    }
    $invocation = Invoke-Captured -FilePath $python.Path -Arguments (@($python.Prefix) + @($definition.Arguments)) -Environment $definition.Environment -RemoveEnvironment @('PYTHONINTMAXSTRDIGITS')
    [void]$checks.Add((New-CheckResult -Name $definition.Name -Command $displayCommand -Invocation $invocation))
}

$endDirtyResult = Invoke-Git @('status', '--porcelain=v1', '--untracked-files=all')
if ($endDirtyResult.ExitCode -ne 0) { throw 'HOLD_GIT_POSTCHECK_FAILED' }
$endDirty = @(Get-OutputLines $endDirtyResult.Stdout)
$endCaches = @(Get-RepositoryCaches)
$checksPassed = ($checks.Count -eq 4 -and @($checks | Where-Object { $_.status -ne 'PASS' }).Count -eq 0)
$repositoryGatePassed = ($startDirty.Count -eq 0 -and $endDirty.Count -eq 0 -and $startCaches.Count -eq 0 -and $endCaches.Count -eq 0)
$status = if ($checksPassed -and $repositoryGatePassed) { 'PASS' } else { 'HOLD' }

$report = [ordered]@{
    schema_version = $schemaVersion
    status = $status
    started_at_utc = $startedAt.ToString('o')
    finished_at_utc = [DateTime]::UtcNow.ToString('o')
    repository = [ordered]@{
        path = $repoRoot
        head = $head
        branch = $branch
        start_dirty = $startDirty
        end_dirty = $endDirty
        start_cache = $startCaches
        end_cache = $endCaches
    }
    environment = [ordered]@{
        os = [Runtime.InteropServices.RuntimeInformation]::OSDescription
        architecture = [Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString()
        powershell = $PSVersionTable.PSVersion.ToString()
        python = $pythonVersion
        python_executable = $python.Path
        python_utf8 = $true
        python_pycache_prefix = $pycachePrefix
        python_dont_write_bytecode = $true
        python_int_max_str_digits_scope = 'payload_self_test_only'
        windows_required = $true
        powershell_7_required = $true
    }
    gates = [ordered]@{
        start_clean = ($startDirty.Count -eq 0)
        end_clean = ($endDirty.Count -eq 0)
        start_repo_cache_free = ($startCaches.Count -eq 0)
        end_repo_cache_free = ($endCaches.Count -eq 0)
    }
    checks = @($checks)
}

$json = $report | ConvertTo-Json -Depth 8
[IO.File]::WriteAllText($ReportPath, $json + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
$readBack = Get-Content -LiteralPath $ReportPath -Raw -Encoding UTF8 | ConvertFrom-Json -Depth 8
if ($readBack.schema_version -ne $schemaVersion -or $readBack.status -ne $status -or @($readBack.checks).Count -ne 4) {
    throw 'HOLD_RESULT_READBACK_MISMATCH'
}

Write-Output ("{0}_WINDOWS_VERIFICATION result={1}" -f $status, $ReportPath)
if ($status -eq 'PASS') { exit 0 }
exit 1
