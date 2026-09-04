param(
    [string]$ApiBaseUrl = "http://localhost:8000",
    [ValidateRange(1, 50)]
    [int]$Count = 8,
    [ValidateRange(1, 30)]
    [int]$IntervalSeconds = 2,
    [switch]$RunBaseline,
    [ValidateRange(0, 100)]
    [int]$ControlPercentage = 0
)

$ErrorActionPreference = "Stop"

$caseResponse = Invoke-RestMethod -Uri "$ApiBaseUrl/api/cases"
$merchantIds = @($caseResponse | ForEach-Object { $_.merchant_id })
if ($merchantIds.Count -eq 0) {
    throw "No merchant-backed case exists. Run: docker compose exec api python -m app.db.seed"
}

$merchantId = [string]$merchantIds[0]
$amounts = @(129900, 249900, 499900, 799900, 1499900)
$sourceTypes = @("ORDER", "PAYMENT_LINK", "PAYMENT")
$runId = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()

Write-Host "Sending $Count synthetic recovery signals to merchant $merchantId"
for ($index = 1; $index -le $Count; $index++) {
    $now = [DateTimeOffset]::UtcNow
    $sourceType = $sourceTypes[($index - 1) % $sourceTypes.Count]
    $sourcePrefix = $sourceType.ToLowerInvariant()
    $payload = @{
        merchant_id = $merchantId
        source_type = $sourceType
        source_id = "${sourcePrefix}_demo_live_${runId}_$index"
        amount_at_risk = $amounts[($index - 1) % $amounts.Count]
        currency = "INR"
        recovery_window_start = $now.ToString("o")
        recovery_window_end = $now.AddDays(14).ToString("o")
    } | ConvertTo-Json

    $created = Invoke-RestMethod `
        -Method Post `
        -Uri "$ApiBaseUrl/api/cases" `
        -ContentType "application/json" `
        -Body $payload

    Write-Host ("[{0}/{1}] {2}  {3}  INR {4:N0}" -f `
        $index, $Count, $created.source_type, $created.source_id, `
        ($created.amount_at_risk / 100))
    if ($index -lt $Count) {
        Start-Sleep -Seconds $IntervalSeconds
    }
}

Write-Host "Live feed complete. The dashboard refreshes every three seconds."

if ($RunBaseline) {
    $batchPayload = @{
        merchant_id = $merchantId
        name = "Live demo $runId"
        control_percentage = $ControlPercentage
    } | ConvertTo-Json
    $batch = Invoke-RestMethod `
        -Method Post `
        -Uri "$ApiBaseUrl/api/baselines/batches" `
        -ContentType "application/json" `
        -Body $batchPayload
    $report = Invoke-RestMethod `
        -Uri "$ApiBaseUrl/api/baselines/$($batch.experiment_id)/report"

    Write-Host "`nDeterministic baseline result"
    Write-Host ("Control: {0}; treatment: {1}; actions: {2}" -f `
        $batch.control_cases, $batch.treatment_cases, $batch.actions_created)
    $report.action_distribution | Format-List
}
