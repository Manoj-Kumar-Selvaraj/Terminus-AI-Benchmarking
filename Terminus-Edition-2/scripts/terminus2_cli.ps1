param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("preflight", "oracle", "nop", "check", "agents", "full", "zip")]
    [string]$Command,

    [Parameter(Mandatory = $false, Position = 1)]
    [string]$TaskPath = ".\cobol-ach-reversal-reconciliation",

    [int]$AgentTrials = 1,
    [switch]$RunRealAgents,
    [switch]$FullWithAgents,
    [switch]$Zip,
    [string]$Distro = "",
    [string]$User = "",
    [int]$StageDelaySec = 20
)

$ErrorActionPreference = "Stop"

function Convert-ToWslPath {
    param([string]$Path)
    $resolved = Resolve-Path -LiteralPath $Path
    $full = $resolved.Path
    $drive = $full.Substring(0, 1).ToLowerInvariant()
    $rest = $full.Substring(2).Replace("\", "/")
    return "/mnt/$drive$rest"
}

$scriptRoot = Split-Path -Parent $PSScriptRoot
$bashScript = Join-Path $PSScriptRoot "terminus2_cli.sh"
if (-not (Test-Path -LiteralPath $bashScript)) {
    throw "Missing script: $bashScript"
}

$wslRoot = Convert-ToWslPath $scriptRoot
$wslTask = Convert-ToWslPath (Join-Path $scriptRoot $TaskPath)

if ($FullWithAgents) {
    $RunRealAgents = $true
    if (-not $PSBoundParameters.ContainsKey("AgentTrials")) {
        $AgentTrials = 5
    }
}

$envParts = @(
    "AGENT_TRIALS=$AgentTrials"
)
if ($RunRealAgents) {
    $envParts += "RUN_REAL_AGENTS=1"
}
if ($Zip) {
    $envParts += "RUN_ZIP=1"
}

function Invoke-WslStage {
    param(
        [string]$Stage,
        [string[]]$ExtraEnv = @()
    )

    $allEnvParts = @($envParts) + @($ExtraEnv)
    $quotedEnv = ($allEnvParts | ForEach-Object { $_ }) -join " "
    $cmd = "cd '$wslRoot' && $quotedEnv bash ./scripts/terminus2_cli.sh '$Stage' '$wslTask'"
    $stageUser = $User
    if ($Stage -eq "check" -and $stageUser.Trim().Length -eq 0) {
        $stageUser = "ec2-user"
    }

    $distroArg = ""
    if ($Distro.Trim().Length -gt 0) {
        $distroArg = "-d $Distro "
    }
    $userArg = ""
    if ($stageUser.Trim().Length -gt 0) {
        $userArg = "-u $stageUser "
    }
    Write-Host "Command: wsl ${distroArg}${userArg}bash -lc `"$cmd`""

    if ($Distro.Trim().Length -gt 0 -and $stageUser.Trim().Length -gt 0) {
        wsl -d $Distro -u $stageUser bash -lc $cmd
    } elseif ($Distro.Trim().Length -gt 0) {
        wsl -d $Distro bash -lc $cmd
    } elseif ($stageUser.Trim().Length -gt 0) {
        wsl -u $stageUser bash -lc $cmd
    } else {
        wsl bash -lc $cmd
    }
    $script:LastStageExitCode = $LASTEXITCODE
}

if ($Command -eq "full") {
    foreach ($stage in @("preflight", "nop", "oracle", "check")) {
        Write-Host "=== $stage ==="
        Invoke-WslStage $stage
        $rc = $script:LastStageExitCode
        if ($rc -ne 0) {
            exit $rc
        }
        if ($stage -in @("nop", "oracle")) {
            Write-Host "Waiting $StageDelaySec seconds for Harbor/Docker cleanup..."
            Start-Sleep -Seconds $StageDelaySec
        }
    }
    if ($RunRealAgents) {
        foreach ($model in @("@openai/gpt-5.2", "@anthropic/claude-opus-4-6")) {
            for ($i = 1; $i -le $AgentTrials; $i++) {
                Write-Host "=== agents $model run $i/$AgentTrials ==="
                Invoke-WslStage "agents" @("AGENT_TRIALS=1", "AGENT_ONLY_MODEL=$model")
                $rc = $script:LastStageExitCode
                if ($rc -ne 0) {
                    exit $rc
                }
                if (-not ($model -eq "@anthropic/claude-opus-4-6" -and $i -eq $AgentTrials)) {
                    Write-Host "Waiting $StageDelaySec seconds for Harbor/Docker cleanup before next agent run..."
                    Start-Sleep -Seconds $StageDelaySec
                }
            }
        }
    }
    if ($Zip) {
        Write-Host "=== zip ==="
        Invoke-WslStage "zip"
        $rc = $script:LastStageExitCode
        if ($rc -ne 0) {
            exit $rc
        }
    }
    exit 0
}

$script:LastStageExitCode = 0
Invoke-WslStage $Command
$rc = $script:LastStageExitCode
exit $rc
