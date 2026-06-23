param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("preflight", "oracle", "all")]
    [string]$Command,

    [Parameter(Mandatory = $true, ValueFromRemainingArguments = $true)]
    [string[]]$Tasks
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$failed = @()

foreach ($task in $Tasks) {
    Write-Host "========== $task =========="
    try {
        if ($Command -eq "preflight" -or $Command -eq "all") {
            python (Join-Path $PSScriptRoot "preflight_task.py") (Join-Path $root $task)
        }
        if ($Command -eq "oracle" -or $Command -eq "all") {
            & (Join-Path $PSScriptRoot "oracle_cumulative_go.ps1") $task
        }
    } catch {
        Write-Host "[FAIL] $task : $_"
        $failed += $task
    }
}

if ($failed.Count -gt 0) {
    Write-Error "$($failed.Count) task(s) failed: $($failed -join ', ')"
}
Write-Host "[OK] all tasks passed ($Command)"
