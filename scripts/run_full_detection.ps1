param(
    [string]$Python = "C:\Users\Administrator\AppData\Local\Python\pythoncore-3.14-64\python.exe",
    [string]$KeepRoot = "",
    [int]$Md5Limit = 20000,
    [int]$PhashLimit = 5000,
    [int]$ThumbnailLimit = 2000,
    [int]$AiSuggestLimit = 50,
    [int]$R18ScanLimit = 50,
    [int]$AutoArchiveLimit = 20,
    [int]$SimilarLimit = 0,
    [int]$SeriesLimit = 0,
    [int]$BackupEveryRounds = 5,
    [int]$SleepSeconds = 5,
    [switch]$ExecuteConfirmedBatches
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$LogDir = Join-Path $RepoRoot "data\logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$RunStamp = Get-Date -Format "yyyyMMdd-HHmmss"
$LogPath = Join-Path $LogDir "full-detection-$RunStamp.log"
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

function Add-RunLogLine {
    param([string]$Line)
    [System.IO.File]::AppendAllText($LogPath, $Line + [Environment]::NewLine, $Utf8NoBom)
}

function Write-RunLog {
    param([string]$Message)
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $Message"
    Write-Output $line
    Add-RunLogLine $line
}

function Invoke-Pims {
    param([string[]]$Arguments)
    Write-RunLog "> python -m pims_v1.cli $($Arguments -join ' ')"
    & $Python -m pims_v1.cli @Arguments 2>&1 | ForEach-Object {
        $line = $_.ToString()
        Write-Output $line
        Add-RunLogLine $line
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $($Arguments -join ' ')"
    }
}

function Get-ProgressSummary {
    $code = @"
import json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from pims_v1.config import settings
from pims_v1.db import Base
from pims_v1.services.progress_service import review_progress_summary

engine = create_engine(settings.database_url, future=True)
Base.metadata.create_all(bind=engine)
session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)()
try:
    print(json.dumps(review_progress_summary(session), ensure_ascii=False))
finally:
    session.close()
"@
    $json = & $Python -c $code
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to read progress summary"
    }
    return $json | ConvertFrom-Json
}

function Invoke-ConfirmedBatches {
    $lines = & $Python -m pims_v1.cli list-batches
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to list batches"
    }
    $confirmedBatchIds = @()
    foreach ($line in $lines) {
        if ($line -match '^\s*(\d+)\s+\|\s+\d+\s+\|\s+confirmed\s+\|\s+duplicate_quarantine') {
            $confirmedBatchIds += [int]$Matches[1]
        }
    }
    if ($confirmedBatchIds.Count -eq 0) {
        return
    }

    Invoke-Pims @("backup-db", "--label", "before-auto-execute-$RunStamp")
    foreach ($batchId in $confirmedBatchIds) {
        Invoke-Pims @("execute-batch", "$batchId")
    }
}

Write-RunLog "Full detection started. Log: $LogPath"
if ([string]::IsNullOrWhiteSpace($KeepRoot)) {
    Write-RunLog "KeepRoot=.env Md5Limit=$Md5Limit PhashLimit=$PhashLimit ThumbnailLimit=$ThumbnailLimit AiSuggestLimit=$AiSuggestLimit R18ScanLimit=$R18ScanLimit AutoArchiveLimit=$AutoArchiveLimit SimilarLimit=$SimilarLimit SeriesLimit=$SeriesLimit ExecuteConfirmedBatches=$ExecuteConfirmedBatches"
} else {
    Write-RunLog "KeepRoot=$KeepRoot Md5Limit=$Md5Limit PhashLimit=$PhashLimit ThumbnailLimit=$ThumbnailLimit AiSuggestLimit=$AiSuggestLimit R18ScanLimit=$R18ScanLimit AutoArchiveLimit=$AutoArchiveLimit SimilarLimit=$SimilarLimit SeriesLimit=$SeriesLimit ExecuteConfirmedBatches=$ExecuteConfirmedBatches"
}

$round = 0
while ($true) {
    $round += 1
    Write-RunLog "===== Round $round started ====="

    if ($ExecuteConfirmedBatches) {
        Invoke-ConfirmedBatches
    }

    if ($round -eq 1 -or (($round - 1) % $BackupEveryRounds) -eq 0) {
        Invoke-Pims @("backup-db", "--label", "full-detection-round-$round-$RunStamp")
    }

    $workflowArgs = @(
        "run-safe-workflow",
        "--md5-limit", "$Md5Limit",
        "--phash-limit", "$PhashLimit",
        "--thumbnail-limit", "$ThumbnailLimit",
        "--ai-suggest-limit", "$AiSuggestLimit",
        "--r18-scan-limit", "$R18ScanLimit",
        "--auto-archive-limit", "$AutoArchiveLimit",
        "--similar-limit", "$SimilarLimit",
        "--series-limit", "$SeriesLimit",
        "--min-series-assets", "2"
    )
    if (-not [string]::IsNullOrWhiteSpace($KeepRoot)) {
        $workflowArgs = @("run-safe-workflow", "--keep-root", $KeepRoot) + $workflowArgs[1..($workflowArgs.Count - 1)]
    }
    Invoke-Pims $workflowArgs

    $progress = Get-ProgressSummary
    $assets = $progress.assets
    Write-RunLog "Progress: assets=$($assets.total) md5=$($assets.md5_done)/$($assets.total) phash=$($assets.phash_done)/$($assets.phash_total) pending_reviews=$($progress.reviews.pending)"

    $md5Complete = [int]$assets.total -eq 0 -or [int]$assets.md5_done -ge [int]$assets.total
    $phashComplete = [int]$assets.phash_total -eq 0 -or [int]$assets.phash_done -ge [int]$assets.phash_total
    if ($md5Complete -and $phashComplete) {
        Write-RunLog "Full detection complete."
        break
    }

    Start-Sleep -Seconds $SleepSeconds
}
