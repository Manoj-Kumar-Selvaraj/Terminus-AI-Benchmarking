param(
    [Parameter(Mandatory = $true)]
    [string]$TaskName,
    [string]$BillSingular = "bill",
    [string]$BillPlural = "bills",
    [string]$RefundSingular = "refund",
    [string]$RefundPlural = "refunds",
    [string]$BillIdCol = "bill_id",
    [string]$CustomerCol = "customer_id",
    [string]$DimCol = "channel",
    [string]$ReportFile = "refund_report.csv",
    [string]$SummaryFile = "refund_summary.json",
    [string]$PostedStatus = "POSTED",
    [string[]]$Channels = @("ACH", "CARD", "WIRE"),
    [hashtable]$Aliases = @{ CC = "CARD"; WIR = "WIRE" },
    [string]$DueDateCol = "due_date",
    [string]$RefundDateCol = "refund_date",
    [string]$TagDomain = "utility"
)

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$template = Join-Path $root "go-utility-refund-reconciler"
$task = Join-Path $root $TaskName
$utf8 = New-Object System.Text.UTF8Encoding($false)

function Write-Lf([string]$Path, [string]$Text) {
    $dir = Split-Path -Parent $Path
    if ($dir -and !(Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
    $Text = ($Text -replace "`r`n", "`n") -replace "`r", "`n"
    [System.IO.File]::WriteAllText($Path, $Text, $utf8)
}

function Replace-InTree([string]$Dir, [hashtable]$Map) {
    Get-ChildItem -Path $Dir -Recurse -File | ForEach-Object {
        $content = [System.IO.File]::ReadAllText($_.FullName)
        $sorted = $Map.GetEnumerator() | Sort-Object { $_.Key.Length } -Descending
        foreach ($entry in $sorted) {
            $content = $content.Replace($entry.Key, $entry.Value)
        }
        Write-Lf $_.FullName $content
    }
}

if (Test-Path $task) { Remove-Item -Recurse -Force $task }
Copy-Item -Path $template -Destination $task -Recurse -Force

$billCap = (Get-Culture).TextInfo.ToTitleCase($BillSingular)
$refundCap = (Get-Culture).TextInfo.ToTitleCase($RefundSingular)
$billFile = "$BillPlural.csv"
$refundFile = "$RefundPlural.csv"

$aliasSolve2 = ""
foreach ($kv in $Aliases.GetEnumerator()) {
    $aliasSolve2 += "`tcase `"$($kv.Key)`":`n`t`treturn `"$($kv.Value)`"`n"
}

$map = [ordered]@{
    "go-utility-refund-reconciler" = $TaskName
    "utility refund" = "$TagDomain $RefundSingular"
    "bill refund" = "$BillSingular $RefundSingular"
    "Bill refund" = "$billCap $RefundSingular"
    "refund_summary.json" = $SummaryFile
    "refund_report.csv" = $ReportFile
    "refunds.csv" = $refundFile
    "bills.csv" = $billFile
    "bill_id" = $BillIdCol
    "customer_id" = $CustomerCol
    "BillID" = "${billCap}ID"
    "type Bill struct" = "type $billCap struct"
    "type Refund struct" = "type $refundCap struct"
    "[]Bill" = "[]$billCap"
    "[]Refund" = "[]$refundCap"
    "loadBills" = "load$(($BillPlural.Substring(0,1).ToUpper())$($BillPlural.Substring(1)))"
    "loadRefunds" = "load$(($RefundPlural.Substring(0,1).ToUpper())$($RefundPlural.Substring(1)))"
    "bills," = "$BillPlural,"
    "refunds," = "$RefundPlural,"
    "(bills " = "($BillPlural "
    "(refunds " = "($RefundPlural "
    "bills [" = "$BillPlural ["
    "refunds [" = "$RefundPlural ["
    "bills)" = "$BillPlural)"
    "refunds)" = "$RefundPlural)"
    " for _, refund" = " for _, $RefundSingular"
    "refund." = "$RefundSingular."
    "refund," = "$RefundSingular,"
    "refund " = "$RefundSingular "
    "refund)" = "$RefundSingular)"
    "refunds " = "$RefundPlural "
    "bills " = "$BillPlural "
    "bill." = "$BillSingular."
    "bill " = "$BillSingular "
    "bill," = "$BillSingular,"
    "*Bill" = "*$billCap"
    "Bill," = "$billCap,"
    "Bill " = "$billCap "
    "Bill{" = "$billCap{"
    "Bill]" = "$billCap]"
    "usedBills" = "used$billCap"
    "findMatch(bills" = "findMatch($BillPlural"
    "writeOutputs(bills" = "writeOutputs($BillPlural"
    "POSTED" = $PostedStatus
    "due_date" = $DueDateCol
    "refund_date" = $RefundDateCol
    "DueDate" = (Get-Culture).TextInfo.ToTitleCase($DueDateCol.Replace("_", " ")).Replace(" ", "")
    "RefundDate" = (Get-Culture).TextInfo.ToTitleCase($RefundDateCol.Replace("_", " ")).Replace(" ", "")
    "channel" = $DimCol
    "Channel" = (Get-Culture).TextInfo.ToTitleCase($DimCol)
    '"ACH" || channel == "CARD" || channel == "WIRE"' = ('"' + ($Channels -join '" || channel == "') + '"')
    'channel == "ACH" || channel == "CARD" || channel == "WIRE"' = ('channel == "' + ($Channels -join '" || channel == "') + '"')
    'return channel == "ACH" || channel == "CARD" || channel == "WIRE"' = ('return channel == "' + ($Channels -join '" || channel == "') + '"')
    "ACH`, `CARD`, and `WIRE`" = ($Channels -join "`, `") + "`"
    "(`ACH`, `CARD`, or `WIRE`)" = "(`$($Channels[0])`, `$($Channels[1])`, or `$($Channels[2])`)"
    "canonical `ACH`, `CARD`, or `WIRE`" = "canonical `$($Channels[0])`, `$($Channels[1])`, or `$($Channels[2])`"
    "CC" = ($Aliases.Keys | Select-Object -First 1)
    "WIR" = ($Aliases.Keys | Select-Object -Last 1)
    "CARD" = $Channels[1]
    "WIRE" = $Channels[2]
    "ACH" = $Channels[0]
    "reconciliation, utility" = "reconciliation, $TagDomain"
    "tags = [""go"", ""csv"", ""reconciliation"", ""utility"", ""cli""]" = "tags = [""go"", ""csv"", ""reconciliation"", ""$TagDomain"", ""cli""]"
}

Replace-InTree $task $map

# Fix load function names (previous replace may be wrong)
$mainPath = Join-Path $task "environment/cmd/reconcile/main.go"
$main = [System.IO.File]::ReadAllText($mainPath)
$loadBillsFn = "load" + ($BillPlural.Substring(0,1).ToUpper() + $BillPlural.Substring(1))
$loadRefundsFn = "load" + ($RefundPlural.Substring(0,1).ToUpper() + $RefundPlural.Substring(1))
$main = $main -replace "loadBills", $loadBillsFn
$main = $main -replace "loadRefunds", $loadRefundsFn
Write-Lf $mainPath $main

# Regenerate solve2 alias block per task
$solve2 = Join-Path $task "steps/milestone_2/solution/solve2.sh"
$s2 = [System.IO.File]::ReadAllText($solve2)
$aliasCases = ($Aliases.GetEnumerator() | ForEach-Object { "`tcase `"$($_.Key)`":`n`t`treturn `"$($_.Value)`"" }) -join "`n"
$canonReturn = "return strings.ToUpper(clean(channel))"
$canonBlock = @"
func canonicalChannel(channel string) string {
	switch strings.ToUpper(clean(channel)) {
$aliasCases
	default:
		$canonReturn
	}
}
"@
$s2 = [regex]::Replace($s2, '(?s)func canonicalChannel\(channel string\) string \{.*?\n\}', $canonBlock.TrimEnd())
$allowed = 'return channel == "' + ($Channels -join '" || channel == "') + '"'
$s2 = [regex]::Replace($s2, 'return channel == "[^"]+"( \|\| channel == "[^"]+")+', $allowed)
Write-Lf $solve2 $s2

# solve3 status check
$solve3 = Join-Path $task "steps/milestone_3/solution/solve3.sh"
$s3 = [System.IO.File]::ReadAllText($solve3)
$s3 = $s3.Replace('bill.Status != "POSTED"', "bill.Status != `"$PostedStatus`"")
Write-Lf $solve3 $s3

Write-Host "Created $TaskName"
