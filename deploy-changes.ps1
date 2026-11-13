# BigFlavor Band Agent - deploy only what changed since the last deploy (Windows)
#
#   .\deploy-changes.ps1            show the plan, ask, then do it
#   .\deploy-changes.ps1 -DryRun    show the plan only
#   .\deploy-changes.ps1 -Yes       don't ask
#   .\deploy-changes.ps1 -Since <commit>   diff from this commit instead of the last deploy
#   .\deploy-changes.ps1 -Full      run deploy-production.ps1 (everything)
#
# deploy-production.ps1 rebuilds and restarts the whole stack. Most changes need
# far less, because of how docker-compose.yml + docker-compose.prod.yml run it:
#   - frontend: a built image (no source mounts) -> rebuild + recreate it
#   - backend:  src/, database/, backend_api.py are mounted -> a restart is enough;
#               only its requirements/Dockerfile/entrypoint need a rebuild
#   - liquidsoap: radio.liq is COPY'd into the image, and BuildKit caches that
#               layer -> a --no-cache rebuild (see AGENTS.md)
#   - nginx:    nginx.conf is mounted -> restart
#   - scripts/, scraper/ are mounted and read per run -> nothing to do
#
# Restarting the backend also drops its in-memory render cache, so not
# restarting it when nothing of its changed saves minutes of re-rendering on
# the produce page as well as deploy time.
#
# The last deploy is recorded in .deploy-state.json (gitignored): the commit,
# any uncommitted files that went out with it, and a hash of .env.production.
# deploy-production.ps1 records it too, so the two stay in step.

param(
    [string]$Since,
    [switch]$DryRun,
    [switch]$Yes,
    [switch]$Full
)

Set-Location $PSScriptRoot

$composeArgs = @('-f', 'docker-compose.yml', '-f', 'docker-compose.prod.yml', '--env-file', '.env.production')
$stateFile = '.deploy-state.json'

function Fail([string]$message) {
    Write-Host "ERROR: $message" -ForegroundColor Red
    exit 1
}

function Run([string]$what, [scriptblock]$command) {
    Write-Host ""
    Write-Host "> $what" -ForegroundColor Cyan
    & $command
    if ($LASTEXITCODE -ne 0) { Fail "$what failed (exit code $LASTEXITCODE)" }
}

if ($Full) {
    & .\deploy-production.ps1
    exit $LASTEXITCODE
}

if (-not (Test-Path '.env.production')) { Fail '.env.production not found - see deploy-production.ps1' }
docker info 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) { Fail 'Docker is not running' }

# --- where to diff from -----------------------------------------------------

$state = $null
if (Test-Path $stateFile) {
    $state = Get-Content $stateFile -Raw | ConvertFrom-Json
}

if ($Since) {
    $base = $Since
    $baseWhy = "-Since $Since"
} elseif ($state) {
    $base = $state.commit
    $baseWhy = "last deploy, $($state.deployedAt)"
} else {
    # No deploy recorded yet. The full deploy rebuilds the frontend every time
    # anything in it changed, so the commit current when the running frontend
    # image was built is a fair starting point. If that image was a cache hit
    # it is older, which only makes the diff bigger - the safe direction.
    $image = docker inspect -f '{{.Image}}' bigflavor-frontend 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $image) {
        Fail 'No deploy recorded and no running frontend to date one from. Run with -Full, or -Since <commit>.'
    }
    $built = docker image inspect -f '{{.Created}}' $image
    $base = git rev-list -1 "--before=$built" HEAD
    $baseWhy = "no deploy recorded yet - commit current when the running frontend image was built ($built)"
}

$baseSha = git rev-parse --verify --quiet "$base^{commit}"
if ($LASTEXITCODE -ne 0 -or -not $baseSha) { Fail "Can't find commit '$base'. Run with -Full, or -Since <commit>." }

# Diffing a commit against the working tree covers committed, staged and
# unstaged changes; untracked files are added separately. Uncommitted files
# that went out with the last deploy count as changed again, in case they have
# since been reverted.
$changed = @(git diff --name-only --no-renames $baseSha) + @(git ls-files --others --exclude-standard)
if ($state -and -not $Since -and $state.dirtyFiles) { $changed += @($state.dirtyFiles) }
$changed = @($changed | Where-Object { $_ } | Sort-Object -Unique)

$envHash = (Get-FileHash '.env.production' -Algorithm SHA256).Hash
$envChanged = $state -and $state.envHash -and ($state.envHash -ne $envHash)

# --- what each changed file needs ---------------------------------------------

function Classify([string]$path) {
    switch -Regex ($path) {
        '^frontend/__tests__/' { return 'skip' }
        '\.md$' { return 'skip' }
        '^(docs|\.agents|\.claude|\.github|tests|setup|sql)/' { return 'skip' }
        '^(LICENSE|conftest\.py|pytest\.ini|\.gitignore|\.gitattributes|\.worktreeinclude|\.env(\.production)?\.example|docker-compose\.override\.yml\.example|Dockerfile\.frontend\.dev|deploy-production\.(ps1|sh)|deploy-changes\.ps1)$' { return 'skip' }
        # Mounted into the backend and read when a script runs, not at startup.
        '^(scripts|scraper)/' { return 'skip' }
        # Icecast is configured through its compose environment; nothing reads this file.
        '^streaming/icecast\.xml$' { return 'skip' }
        '^(frontend/|Dockerfile\.frontend$)' { return 'build:frontend' }
        '^(requirements-(api|ml)\.txt|Dockerfile\.backend|docker-entrypoint-backend\.sh|\.dockerignore)$' { return 'build:backend' }
        # Migrations are applied by hand; the running code doesn't read them.
        '^database/sql/migrations/' { return 'migration' }
        '^(src/|database/|backend_api\.py$)' { return 'restart:backend' }
        '^(streaming/radio\.liq|Dockerfile\.liquidsoap)$' { return 'build:liquidsoap' }
        '^nginx/' { return 'restart:nginx' }
        '^docker-compose(\.prod)?\.yml$' { return 'compose' }
        default { return 'unknown' }
    }
}

$builds = @()
$restarts = @()
$migrations = @()
$unknown = @()
$skipped = 0
$composeChanged = $false
$reasons = @{}

foreach ($path in $changed) {
    $kind = Classify $path
    if ($kind -eq 'skip') { $skipped++; continue }
    if ($kind -eq 'unknown') { $unknown += $path; continue }
    if ($kind -eq 'migration') { $migrations += $path; continue }
    if ($kind -eq 'compose') { $composeChanged = $true; continue }
    $action, $service = $kind -split ':'
    if ($action -eq 'build' -and $builds -notcontains $service) { $builds += $service }
    if ($action -eq 'restart' -and $restarts -notcontains $service) { $restarts += $service }
    if (-not $reasons[$kind]) { $reasons[$kind] = $path }
}
# A rebuilt service is recreated, which restarts it anyway.
$restarts = @($restarts | Where-Object { $builds -notcontains $_ })
$recreateAll = $composeChanged -or $envChanged

# --- the plan -------------------------------------------------------------------

Write-Host "Deploying changes since $($baseSha.Substring(0, 7)) ($baseWhy)" -ForegroundColor Cyan
Write-Host "$($changed.Count) changed file(s), $skipped needing nothing (docs, tests, scripts)"
Write-Host ""

if ($unknown.Count -gt 0) {
    Write-Host "Not sure what these need, so not guessing:" -ForegroundColor Yellow
    $unknown | ForEach-Object { Write-Host "  $_" }
    Write-Host "Run .\deploy-changes.ps1 -Full to deploy everything, or teach Classify in this script about them." -ForegroundColor Yellow
    exit 1
}

$plan = @()
foreach ($svc in $builds) { $plan += "rebuild + recreate $svc   (e.g. $($reasons["build:$svc"]))" }
foreach ($svc in $restarts) { $plan += "restart $svc   (e.g. $($reasons["restart:$svc"]))" }
if ($composeChanged) { $plan += 'docker-compose up -d   (compose file changed - recreates only services whose config changed)' }
elseif ($envChanged) { $plan += 'docker-compose up -d   (.env.production changed - recreates only services whose config changed)' }

if ($plan.Count -eq 0) {
    Write-Host 'Nothing to deploy.' -ForegroundColor Green
} else {
    Write-Host 'Plan:' -ForegroundColor Cyan
    $plan | ForEach-Object { Write-Host "  - $_" }
}
if ($migrations.Count -gt 0) {
    Write-Host ""
    Write-Host 'New or changed migrations - apply these by hand, this script does not:' -ForegroundColor Yellow
    $migrations | ForEach-Object { Write-Host "  $_" }
}
if ($restarts -contains 'backend' -or $builds -contains 'backend') {
    Write-Host ""
    Write-Host 'Note: restarting the backend clears its render cache; open produce pages re-render on next play.' -ForegroundColor DarkGray
}

if ($DryRun) { exit 0 }

if ($plan.Count -gt 0 -and -not $Yes) {
    Write-Host ""
    $answer = Read-Host 'Continue? (y/n)'
    if ($answer -ne 'y' -and $answer -ne 'Y') {
        Write-Host 'Deployment cancelled' -ForegroundColor Yellow
        exit 0
    }
}

# --- do it ----------------------------------------------------------------------

# Build first, while the old containers keep serving, so the swap is short.
$cachedBuilds = @($builds | Where-Object { $_ -ne 'liquidsoap' })
if ($cachedBuilds.Count -gt 0) {
    Run "build $($cachedBuilds -join ', ')" { docker-compose @composeArgs build @cachedBuilds }
}
if ($builds -contains 'liquidsoap') {
    Run 'build liquidsoap (no cache - BuildKit caches the radio.liq COPY)' { docker-compose @composeArgs build --no-cache liquidsoap }
}

if ($recreateAll) {
    Run 'docker-compose up -d' { docker-compose @composeArgs up -d }
} elseif ($builds.Count -gt 0) {
    Run "recreate $($builds -join ', ')" { docker-compose @composeArgs up -d --no-deps @builds }
}
foreach ($svc in $restarts) {
    Run "restart $svc" { docker restart "bigflavor-$svc" | Out-Null }
}

# --- wait for what was touched -----------------------------------------------------

$touched = @($builds + $restarts)
if ($recreateAll) {
    $touched = @(docker-compose @composeArgs config --services | Where-Object { $_.Trim() -ne '' })
}

if ($touched.Count -gt 0) {
    Write-Host ""
    Write-Host "Waiting for $($touched -join ', ')..." -ForegroundColor Cyan
    $allUp = $false
    $statusLines = @()
    for ($i = 1; $i -le 30; $i++) {
        $allUp = $true
        $statusLines = @()
        foreach ($svc in $touched) {
            $info = docker inspect --format '{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "bigflavor-$svc" 2>$null
            if ($LASTEXITCODE -ne 0) { $allUp = $false; $statusLines += "$svc : no container"; continue }
            $status, $health = $info -split '\|'
            if ($status -ne 'running' -or ($health -ne 'healthy' -and $health -ne 'none')) { $allUp = $false }
            $statusLines += "$svc : $status/$health"
        }
        if ($allUp) { break }
        Start-Sleep -Seconds 5
    }
    if (-not $allUp) {
        Write-Host "ERROR: not everything came up running/healthy:" -ForegroundColor Red
        $statusLines | ForEach-Object { Write-Host "  $_" -ForegroundColor Yellow }
        Write-Host "Check logs with: docker logs bigflavor-<service> --tail 100" -ForegroundColor Yellow
        Write-Host "The deploy was NOT recorded, so the next run will try these again." -ForegroundColor Yellow
        exit 1
    }
    Write-Host "[OK] $($touched -join ', ') running and healthy" -ForegroundColor Green
}

# --- record it ------------------------------------------------------------------------

$dirty = @(git diff --name-only --no-renames HEAD) + @(git ls-files --others --exclude-standard)
@{
    commit     = (git rev-parse HEAD)
    dirtyFiles = @($dirty | Where-Object { $_ })
    envHash    = $envHash
    deployedAt = (Get-Date).ToString('s')
} | ConvertTo-Json | Set-Content -Encoding utf8 $stateFile

Write-Host ""
Write-Host "Recorded deploy of $((git rev-parse --short HEAD))$(if ($dirty.Count -gt 0) { " + $($dirty.Count) uncommitted file(s)" })" -ForegroundColor Green
