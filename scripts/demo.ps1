<#
.SYNOPSIS
    Guided live demo of the AI Customer Support API (local mock server).

.DESCRIPTION
    Drives a scripted four-scene conversation through the REST API and prints
    colour-coded output suitable for a live demo or a screen recording.

    Prerequisites
    -------------
    Terminal 1 (keep running):
        .venv\Scripts\python.exe scripts/demo_local.py

    Terminal 2 (run this script):
        .\scripts\demo.ps1

    Or start the server automatically:
        .\scripts\demo.ps1 -StartServer

.PARAMETER StartServer
    Automatically launch demo_local.py in the background before the demo.

.PARAMETER Port
    Port the server is listening on (default: 8000).

.EXAMPLE
    # Two-terminal workflow (recommended for demos)
    # Terminal 1:
    .venv\Scripts\python.exe scripts\demo_local.py

    # Terminal 2:
    .\scripts\demo.ps1

.EXAMPLE
    # One-liner (server starts and stops automatically)
    .\scripts\demo.ps1 -StartServer
#>

param(
    [switch]$StartServer,
    [int]$Port = 8000
)

Set-StrictMode -Off
$ErrorActionPreference = "Stop"

$BaseUrl    = "http://localhost:$Port"
$PythonExe  = ".venv\Scripts\python.exe"
$ServerProc = $null

# ─── Helpers ─────────────────────────────────────────────────────────────────

function Write-Banner {
    param([string]$Text, [string]$Color = "Cyan")
    Write-Host ""
    Write-Host ("═" * 64) -ForegroundColor $Color
    Write-Host "  $Text" -ForegroundColor White
    Write-Host ("═" * 64) -ForegroundColor $Color
}

function Write-Scene {
    param([string]$Number, [string]$Title)
    Write-Host ""
    Write-Host ("─" * 64) -ForegroundColor DarkGray
    Write-Host "  SCENE $Number  " -ForegroundColor Cyan -NoNewline
    Write-Host $Title -ForegroundColor White
    Write-Host ("─" * 64) -ForegroundColor DarkGray
}

function Write-Request {
    param([string]$Method, [string]$Path, [string]$Body = "")
    Write-Host ""
    Write-Host "  REQUEST:" -ForegroundColor DarkYellow
    Write-Host "    $Method $Path" -ForegroundColor Yellow
    if ($Body) { Write-Host "    $Body" -ForegroundColor DarkYellow }
}

function Write-Field {
    param([string]$Label, [string]$Value, [string]$Color = "DarkGray")
    Write-Host ("  {0,-20} {1}" -f "${Label}:", $Value) -ForegroundColor $Color
}

function Invoke-Api {
    param(
        [string]$Method = "GET",
        [string]$Path,
        [hashtable]$Body = $null
    )
    $uri     = "$BaseUrl$Path"
    $headers = @{ "Content-Type" = "application/json"; "Accept" = "application/json" }

    if ($Body) {
        $json     = $Body | ConvertTo-Json -Compress -Depth 5
        $response = Invoke-RestMethod -Method $Method -Uri $uri -Headers $headers -Body $json
    } else {
        $response = Invoke-RestMethod -Method $Method -Uri $uri -Headers $headers
    }
    return $response
}

function Wait-ForServer {
    Write-Host "  Waiting for server to be ready" -ForegroundColor DarkGray -NoNewline
    for ($i = 0; $i -lt 20; $i++) {
        Start-Sleep -Milliseconds 800
        try {
            $null = Invoke-RestMethod -Uri "$BaseUrl/health" -ErrorAction Stop
            Write-Host "  ready." -ForegroundColor Green
            return $true
        } catch {
            Write-Host "." -NoNewline -ForegroundColor DarkGray
        }
    }
    Write-Host ""
    return $false
}

# ─── Optionally start the mock server ────────────────────────────────────────

if ($StartServer) {
    Write-Host ""
    Write-Host "  Starting mock server..." -ForegroundColor DarkGray

    $ServerProc = Start-Process `
        -FilePath $PythonExe `
        -ArgumentList "scripts/demo_local.py" `
        -PassThru `
        -WindowStyle Hidden

    if (-not (Wait-ForServer)) {
        Write-Host ""
        Write-Host "  ERROR: Server did not become ready in time." -ForegroundColor Red
        Write-Host "  Start it manually in a separate terminal:" -ForegroundColor Yellow
        Write-Host "    $PythonExe scripts/demo_local.py" -ForegroundColor Yellow
        exit 1
    }
}

# ─── Banner ───────────────────────────────────────────────────────────────────

Write-Banner "AI Customer Support  —  Adaptive Agent Network  (v1.0)"
Write-Host "  All Azure services are MOCKED.  No cloud credentials needed." -ForegroundColor DarkGray
Write-Host "  Swagger UI  →  $BaseUrl/docs" -ForegroundColor DarkGray

# ─── STEP 1 — Health check ────────────────────────────────────────────────────

Write-Scene "0" "Health check — is the API alive?"
Write-Request "GET" "/health"

$health = Invoke-Api -Path "/health"

Write-Host ""
Write-Host "  RESPONSE:" -ForegroundColor Green
Write-Field "Status"  $health.status  "Green"
Write-Field "Version" $health.version "Green"

Start-Sleep -Milliseconds 400

# ─── SCENE 1 — Billing query ─────────────────────────────────────────────────

Write-Scene "1" "Customer reports an unexpected charge on their invoice"

$req1 = @{
    message = "Hi, I just noticed I was charged twice on my account this month. Can you help me sort this out?"
    user_id = "user-demo-001"
}
Write-Request "POST" "/conversations" ($req1 | ConvertTo-Json -Compress)

$conv1   = Invoke-Api -Method POST -Path "/conversations" -Body $req1
$convId1 = $conv1.conversation_id

Write-Host ""
Write-Host "  RESPONSE:" -ForegroundColor Cyan
Write-Field "Conversation ID"  $convId1                                "DarkGray"
Write-Field "Topic detected"   $conv1.topic                            "DarkGray"
Write-Field "Confidence"       ("{0:P0}" -f $conv1.confidence)         "DarkGray"
Write-Field "Resolution state" $conv1.resolution_state                 "DarkGray"
Write-Host ""
Write-Host $conv1.response -ForegroundColor White

Start-Sleep -Milliseconds 600

# ─── SCENE 2 — Follow-up: customer confirms resolution ───────────────────────

Write-Scene "2" "Same conversation — customer confirms the issue is resolved"

$req2 = @{ message = "That makes sense, thanks! All sorted now." }
Write-Request "POST" "/conversations/$convId1/messages" ($req2 | ConvertTo-Json -Compress)

$reply1 = Invoke-Api -Method POST -Path "/conversations/$convId1/messages" -Body $req2

Write-Host ""
Write-Host "  RESPONSE:" -ForegroundColor Cyan
Write-Field "Resolution state" $reply1.resolution_state "Green"
Write-Host ""
Write-Host "  ✔  'resolved_confirmed' — the agent detected a thank-you and closed the loop." -ForegroundColor Green
Write-Host ""
Write-Host $reply1.response -ForegroundColor White

Start-Sleep -Milliseconds 600

# ─── SCENE 3 — New conversation: app bug ─────────────────────────────────────

Write-Scene "3" "Different customer — mobile app crashes on login (iOS)"

$req3 = @{
    message = "The app keeps crashing every time I try to log in. I'm on an iPhone running iOS 18."
    user_id = "user-demo-002"
}
Write-Request "POST" "/conversations" ($req3 | ConvertTo-Json -Compress)

$conv2 = Invoke-Api -Method POST -Path "/conversations" -Body $req3

Write-Host ""
Write-Host "  RESPONSE:" -ForegroundColor Cyan
Write-Field "Conversation ID"  $conv2.conversation_id                  "DarkGray"
Write-Field "Topic detected"   $conv2.topic                            "DarkGray"
Write-Field "Confidence"       ("{0:P0}" -f $conv2.confidence)         "DarkGray"
Write-Host ""
Write-Host $conv2.response -ForegroundColor White

Start-Sleep -Milliseconds 600

# ─── SCENE 4 — GET: retrieve persisted conversation state ────────────────────

Write-Scene "4" "Retrieve conversation history via GET (state persisted across turns)"
Write-Request "GET" "/conversations/$convId1"

$state = Invoke-Api -Path "/conversations/$convId1"

Write-Host ""
Write-Host "  RESPONSE:" -ForegroundColor Cyan
Write-Field "Status"           $state.status           "DarkGray"
Write-Field "Resolution"       $state.resolution_state "Green"
Write-Field "Confidence"       ("{0:P0}" -f $state.confidence) "DarkGray"

Start-Sleep -Milliseconds 400

# ─── Summary ─────────────────────────────────────────────────────────────────

Write-Banner "Demo complete  ✔" "Green"

Write-Host "  What just happened in 4 scenes:" -ForegroundColor White
Write-Host ""
Write-Host "  Scene 0  Health check — API is live and responsive"               -ForegroundColor DarkGray
Write-Host "  Scene 1  Billing query → billing agent → structured response"     -ForegroundColor DarkGray
Write-Host "  Scene 2  Follow-up 'thanks' → resolution_state = resolved_confirmed" -ForegroundColor DarkGray
Write-Host "  Scene 3  New user, tech issue → tech agent → step-by-step fix"   -ForegroundColor DarkGray
Write-Host "  Scene 4  GET /conversations confirms state persisted across turns" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  Key capabilities demonstrated:" -ForegroundColor White
Write-Host "  • Multi-turn conversation context (Cosmos DB, mocked here)"       -ForegroundColor DarkGray
Write-Host "  • Automatic topic routing  (billing / tech / returns / general)"  -ForegroundColor DarkGray
Write-Host "  • Resolution tracking  (in_progress → resolved_confirmed)"        -ForegroundColor DarkGray
Write-Host "  • X-Request-ID tracing on every response"                         -ForegroundColor DarkGray
Write-Host "  • OpenTelemetry telemetry  (no-op when App Insights not set)"     -ForegroundColor DarkGray
Write-Host "  • Zero Azure credentials required for local development"          -ForegroundColor DarkGray
Write-Host ""
Write-Host "  Swagger UI  →  $BaseUrl/docs" -ForegroundColor Cyan
Write-Host ("═" * 64) -ForegroundColor Green
Write-Host ""

# ─── Cleanup ──────────────────────────────────────────────────────────────────

if ($ServerProc -and -not $ServerProc.HasExited) {
    $ServerProc | Stop-Process -Force
    Write-Host "  Mock server stopped." -ForegroundColor DarkGray
    Write-Host ""
}
