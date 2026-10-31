# Install the let's play pipeline's dependencies on Windows (Linux and macOS: install-deps.sh). Safe to re-run.
# usage: powershell -ExecutionPolicy Bypass -File install-deps.ps1
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

function Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Have($cmd) { [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }
function Native([scriptblock]$block) {
    & $block
    if ($LASTEXITCODE) { throw "failed with exit code ${LASTEXITCODE}: $block" }
}
function Refresh-Path {
    $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
}
function Have-Python312 {
    if (-not (Have py)) { return $false }
    & py -3.12 -c 'import sys' 2>$null
    return $LASTEXITCODE -eq 0
}

if (-not (Have winget)) { throw 'winget is required (Windows 10 1809+ / App Installer): https://aka.ms/getwinget' }
$winget = @('install', '-e', '--accept-source-agreements', '--accept-package-agreements')

Step 'System tools (winget)'
if (-not (Have ffmpeg)) { Native { winget @winget --id Gyan.FFmpeg } }
if (-not ((Have node) -and (Have npm.cmd))) { Native { winget @winget --id OpenJS.NodeJS.LTS } }
if (-not (Have-Python312)) { Native { winget @winget --id Python.Python.3.12 } }
Refresh-Path
if (-not (Have ffmpeg)) { throw 'ffmpeg not found after install: open a new PowerShell and run this script again.' }
if (-not (Have-Python312)) { throw 'Python 3.12 not found after install: open a new PowerShell and run this script again.' }
if ([int](node -p 'process.versions.node.split(".")[0]') -lt 20) { throw 'Node 20+ is required.' }

Step 'Python packages (.venv)'
if (-not (Test-Path .venv)) { Native { py -3.12 -m venv .venv } }
Native { .\.venv\Scripts\python.exe -m pip install -r requirements.txt }

Step 'Node packages'
Native { npm.cmd install }

Step 'Config and style music'
if (-not (Test-Path config.json)) {
    Copy-Item config.example.json config.json
    Write-Host 'Created config.json: set your channel name, VOD folder and language.'
}
$music = Join-Path $PSScriptRoot 'public\music'
New-Item -ItemType Directory -Force $music | Out-Null
$tracks = [ordered]@{
    'funk.mp3'          = 'Funk%20Game%20Loop'
    'elevator.mp3'      = 'Local%20Forecast%20-%20Elevator'
    'darkest-child.mp3' = 'Darkest%20Child'
    'ossuary.mp3'       = 'Ossuary%206%20-%20Air'
    'carefree.mp3'      = 'Carefree'
    'lobby-time.mp3'    = 'Lobby%20Time'
}
foreach ($file in $tracks.Keys) {
    $path = Join-Path $music $file
    if ((Test-Path $path) -and (Get-Item $path).Length -gt 0) { continue }
    Invoke-WebRequest -Uri "https://incompetech.com/music/royalty-free/mp3-royaltyfree/$($tracks[$file]).mp3" -OutFile $path
    Write-Host $file
}

Step 'MCP config (YouTube server, Windows venv path)'
$mcp = @'
{
  "mcpServers": {
    "youtube": {
      "command": ".venv\\Scripts\\python.exe",
      "args": ["scripts/youtube_mcp.py"]
    }
  }
}
'@
[IO.File]::WriteAllText((Join-Path $PSScriptRoot '.mcp.json'), $mcp + "`n", (New-Object Text.UTF8Encoding $false))

Step 'Done. Next: edit config.json, then npm test (see README.md for YouTube sign-in, optional).'
