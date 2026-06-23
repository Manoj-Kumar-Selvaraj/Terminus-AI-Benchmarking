param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$TaskName
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$taskDir = Join-Path $root $TaskName
$image = "local/${TaskName}:check"

if (-not (Test-Path -LiteralPath $taskDir)) {
    throw "Task not found: $taskDir"
}

docker build -t $image (Join-Path $taskDir "environment")
$stepsMount = (Join-Path $taskDir "steps") -replace '\\', '/'
if ($stepsMount -match '^([A-Z]):') {
    $stepsMount = "/$($Matches[1].ToLower())$($stepsMount.Substring(2))"
}

$tomlPath = Join-Path $taskDir "task.toml"
$maxM = 3
if (Test-Path -LiteralPath $tomlPath) {
    if ((Get-Content -LiteralPath $tomlPath -Raw) -match 'number_of_milestones\s*=\s*(\d+)') {
        $maxM = [int]$Matches[1]
    }
}

foreach ($m in 1..$maxM) {
    Write-Host "=== $TaskName milestone_$m ==="
    $inner = @(
        "set -e",
        "bash /steps/milestone_${m}/solution/solve.sh",
        "rm -rf /tests",
        "mkdir -p /tests",
        "cp -r /steps/milestone_${m}/tests/. /tests/",
        "bash /tests/test.sh",
        "cat /logs/verifier/reward.txt"
    ) -join "`n"
    docker run --rm -v "${stepsMount}:/steps:ro" $image bash -lc $inner
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
