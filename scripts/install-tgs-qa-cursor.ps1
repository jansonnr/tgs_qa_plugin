#Requires -Version 5.1
<#
.SYNOPSIS
  Копирует плагин tgs-qa-cursor в Cursor и ставит Python-зависимости для Zephyr/Jira.

.PARAMETER UseThisRepo
  Запуск из уже скачанного clone (каталог scripts\ внутри репозитория).

.PARAMETER Force
  Удалить существующий %USERPROFILE%\.cursor\plugins\local\tgs-qa-cursor и скопировать заново.
#>
[CmdletBinding()]
param(
    [string] $CloneDir = (Join-Path $env:USERPROFILE "tools\tgs_qa_plugin"),
    [string] $RepoUrl = "https://github.com/jansonnr/tgs_qa_plugin.git",
    [switch] $UseThisRepo,
    [switch] $SkipPythonDeps,
    [switch] $Force,
    [switch] $WriteConfigTemplate,
    [Alias("ForceJunction")]
    [switch] $ForceCopy
)

if ($ForceCopy) { $Force = $true }

$ErrorActionPreference = "Stop"

function Write-Step([string] $Message) {
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Test-Command([string] $Name) {
    $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Copy-PluginToLocal([string] $Source, [string] $Dest, [switch] $Replace) {
    if (-not (Test-Path -LiteralPath $Source)) {
        throw "Нет исходника плагина: $Source"
    }
    $parent = Split-Path -Parent $Dest
    if (-not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }
    if (Test-Path -LiteralPath $Dest) {
        if (-not $Replace) {
            throw "Уже есть: $Dest. Запустите с -Force или удалите папку."
        }
        Remove-Item -LiteralPath $Dest -Recurse -Force
    }
    Write-Host "robocopy `"$Source`" -> `"$Dest`""
    & robocopy $Source $Dest /E /NFL /NDL /NJH /NJS /nc /ns /np | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy failed with exit code $LASTEXITCODE" }
}

function Install-PythonDeps([string] $McpDir) {
    if (-not (Test-Path (Join-Path $McpDir "pyproject.toml"))) {
        throw "Нет pyproject.toml: $McpDir"
    }
    Push-Location $McpDir
    try {
        if (Test-Command "uv") {
            & uv sync
            if ($LASTEXITCODE -ne 0) { throw "uv sync failed" }
            & uv run python -c "import zephyr_scale_mcp; print('OK')"
            return
        }
        $py = $null
        foreach ($candidate in @("py -3.12", "py -3.11", "python")) {
            if (Test-Command ($candidate -split " ")[0]) { $py = $candidate; break }
        }
        if (-not $py) { throw "Нужен Python 3.11+ или uv: https://docs.astral.sh/uv/" }
        if (-not (Test-Path ".venv")) { Invoke-Expression "$py -m venv .venv" }
        $pip = Join-Path $McpDir ".venv\Scripts\python.exe"
        & $pip -m pip install -e .
        if ($LASTEXITCODE -ne 0) { throw "pip install failed" }
        & $pip -c "import zephyr_scale_mcp; print('OK')"
    } finally {
        Pop-Location
    }
}

function Write-ConfigTemplateIfAsked {
    if (-not $WriteConfigTemplate) { return }
    $configPath = Join-Path $env:APPDATA "zephyr-scale-mcp\config.json"
    if (Test-Path -LiteralPath $configPath) {
        Write-Host "config.json уже есть, не перезаписываем: $configPath"
        return
    }
    New-Item -ItemType Directory -Path (Split-Path $configPath) -Force | Out-Null
    @"
{
  "base_url": "https://your-jira-host.example/soft",
  "bearer_token": "",
  "wiki_bearer_token": "",
  "project_key": "QA",
  "project_id": "10104",
  "wiki_url": ""
}
"@ | Set-Content -Path $configPath -Encoding UTF8
    Write-Host "Шаблон: $configPath"
}

Write-Step "Репозиторий"
if ($UseThisRepo) {
    $RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
} elseif (-not (Test-Path -LiteralPath $CloneDir)) {
    if (-not (Test-Command "git")) { throw "git не найден" }
    New-Item -ItemType Directory -Path (Split-Path $CloneDir -Parent) -Force -ErrorAction SilentlyContinue | Out-Null
    & git clone $RepoUrl $CloneDir
    if ($LASTEXITCODE -ne 0) { throw "git clone failed" }
    $RepoRoot = (Resolve-Path -LiteralPath $CloneDir).Path
} else {
    $RepoRoot = (Resolve-Path -LiteralPath $CloneDir).Path
    Write-Host "Используем: $RepoRoot (обновление: git pull, затем этот скрипт с -Force)"
}

$PluginSrc = Join-Path $RepoRoot "plugins\tgs-qa-cursor"
$PluginLocal = Join-Path $env:USERPROFILE ".cursor\plugins\local\tgs-qa-cursor"

Write-Step "Копия плагина для Cursor"
Copy-PluginToLocal -Source $PluginSrc -Dest $PluginLocal -Replace:$Force

if (-not $SkipPythonDeps) {
    Write-Step "Python (Zephyr/Jira внутри плагина)"
    Install-PythonDeps -McpDir (Join-Path $PluginLocal "zephyr-scale-mcp")
}

Write-ConfigTemplateIfAsked

Write-Step "Готово"
Write-Host @"

1. Cursor: Reload Window
2. Customize -> Plugins -> TGS QA Cursor (включить; third-party plugins — если выключено)
3. %APPDATA%\zephyr-scale-mcp\config.json — токены
4. /qa-help в рабочем проекте

Обновление: git pull в $RepoRoot , затем:
  .\scripts\install-tgs-qa-cursor.ps1 -UseThisRepo -Force
"@
