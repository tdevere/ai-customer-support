<#
.SYNOPSIS
    Runs the full CI pipeline locally (lint + tests) to catch failures before pushing.

.DESCRIPTION
    Mirrors the GitHub Actions ci-cd.yml pipeline exactly:
      1. Ensures a Python 3.11 virtual environment exists and is activated
      2. Installs / syncs dependencies via uv
      3. Runs black --check (formatting)
      4. Runs flake8 (linting)
      5. Runs pytest with coverage
    Mock environment variables are loaded from .env.test so no real credentials are needed.

.PARAMETER Step
    Run only a specific step: 'install', 'format', 'lint', or 'test'.
    Defaults to running all steps.

.PARAMETER Fix
    When set, auto-fixes formatting with 'black .' before the check.

.EXAMPLE
    .\scripts\test_local.ps1
    .\scripts\test_local.ps1 -Fix
    .\scripts\test_local.ps1 -Step test

#>
[CmdletBinding()]
param(
    [ValidateSet('', 'install', 'format', 'lint', 'typecheck', 'test')]
    [string]$Step = '',

    [switch]$Fix
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# ─── Helpers ──────────────────────────────────────────────────────────────────

function Write-Header($text) {
    $line = '─' * 60
    Write-Host ""
    Write-Host $line -ForegroundColor Cyan
    Write-Host "  $text" -ForegroundColor Cyan
    Write-Host $line -ForegroundColor Cyan
}

function Write-Ok($text)   { Write-Host "  ✓ $text" -ForegroundColor Green }
function Write-Fail($text) { Write-Host "  ✗ $text" -ForegroundColor Red }
function Write-Info($text) { Write-Host "  · $text" -ForegroundColor DarkGray }

$RepoRoot = Split-Path $PSScriptRoot -Parent
Set-Location $RepoRoot

# ─── 1. Virtual environment ───────────────────────────────────────────────────

function Step-Install {
    Write-Header "Step 1 · Virtual environment & dependencies"

    # Prefer Python 3.11 to match CI; fall back to whatever is on PATH
    $python = $null
    foreach ($candidate in @('py -3.11', 'python3.11', 'python3', 'python')) {
        try {
            $ver = & ($candidate.Split()[0]) ($candidate.Split()[1..99]) --version 2>&1
            if ($ver -match '3\.11') { $python = $candidate; break }
        } catch { }
    }
    if (-not $python) {
        Write-Host ""
        Write-Host "  WARNING: Python 3.11 not found — CI uses 3.11. Using system Python instead." -ForegroundColor Yellow
        Write-Host "  Install it from: https://www.python.org/downloads/release/python-3110/" -ForegroundColor Yellow
        $python = 'python'
    } else {
        Write-Ok "Python 3.11 found: $python"
    }

    $venv = Join-Path $RepoRoot '.venv'
    if (-not (Test-Path $venv)) {
        Write-Info "Creating .venv …"
        & $python.Split()[0] $python.Split()[1..99] -m venv $venv
    }

    # Activate
    $activate = Join-Path $venv 'Scripts\Activate.ps1'
    if (Test-Path $activate) { & $activate }

    Write-Info "Installing / syncing dependencies via uv …"
    python -m pip install --upgrade pip uv --quiet
    uv pip install --system -r requirements.txt --quiet
    Write-Ok "Dependencies installed"
}

# ─── 2. Load .env.test ────────────────────────────────────────────────────────

function Load-EnvTest {
    $envFile = Join-Path $RepoRoot '.env.test'
    if (-not (Test-Path $envFile)) {
        Write-Host "  WARNING: .env.test not found — continuing without mock env vars." -ForegroundColor Yellow
        return
    }
    Get-Content $envFile | ForEach-Object {
        if ($_ -match '^\s*#' -or $_ -match '^\s*$') { return }
        $parts = $_ -split '=', 2
        if ($parts.Length -eq 2) {
            [System.Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim(), 'Process')
        }
    }
    Write-Ok "Loaded mock env vars from .env.test"
}

# ─── 3. Format ────────────────────────────────────────────────────────────────

function Step-Format {
    Write-Header "Step 2 · Code formatting (black)"
    if ($Fix) {
        Write-Info "Auto-fixing with: black ."
        python -m black .
        Write-Ok "Files reformatted"
    } else {
        Write-Info "Running: black --check ."
        python -m black --check .
        if ($LASTEXITCODE -ne 0) {
            Write-Fail "Black found unformatted files. Run with -Fix to auto-correct."
            exit 1
        }
        Write-Ok "All files are black-formatted"
    }
}

# ─── 4. Lint ──────────────────────────────────────────────────────────────────

function Step-Lint {
    Write-Header "Step 3 · Linting (flake8)"

    Write-Info "Pass 1 — fatal errors only (E9, F63, F7, F82) …"
    python -m flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "flake8 fatal errors found — fix before pushing"
        exit 1
    }
    Write-Ok "No fatal lint errors"

    Write-Info "Pass 2 — full advisory check (exit-zero) …"
    python -m flake8 . --count --exit-zero --max-complexity=10 --max-line-length=127 --statistics
    Write-Ok "Lint advisory pass complete"
}

# ─── 4.5. Type check ─────────────────────────────────────────────────────────

function Step-Typecheck {
    Write-Header "Step 3.5 · Type checking (mypy)"
    Write-Info "Running: mypy shared/ orchestrator/ agents/ integrations/ --ignore-missing-imports --no-error-summary"
    python -m mypy shared/ orchestrator/ agents/ integrations/ --ignore-missing-imports --no-error-summary
    # mypy exit code is non-zero when there are type errors, but we treat it as
    # advisory (continue-on-error) to match CI behaviour.
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  ! mypy reported type issues (advisory only — will not block push)" -ForegroundColor Yellow
    } else {
        Write-Ok "mypy: no type errors found"
    }
}

# ─── 5. Test ──────────────────────────────────────────────────────────────────

function Step-Test {
    Write-Header "Step 4 · Tests (pytest + coverage)"
    Load-EnvTest
    Write-Info "Running: pytest tests/ --cov=. --cov-report=xml --cov-report=term --cov-fail-under=90"
    python -m pytest tests/ --cov=. --cov-report=xml --cov-report=term --cov-fail-under=90
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "Tests failed — see output above"
        exit 1
    }
    Write-Ok "All tests passed"
}

# ─── Main ─────────────────────────────────────────────────────────────────────

$startTime = Get-Date

switch ($Step) {
    'install'    { Step-Install }
    'format'     { Step-Format }
    'lint'       { Step-Lint }
    'typecheck'  { Step-Typecheck }
    'test'       { Step-Test }
    default      {
        Step-Install
        Step-Format
        Step-Lint
        Step-Typecheck
        Step-Test
    }
}

$elapsed = [math]::Round(((Get-Date) - $startTime).TotalSeconds, 1)
Write-Header "Done in ${elapsed}s"
Write-Ok "CI pipeline passed locally — safe to push"
Write-Host ""
