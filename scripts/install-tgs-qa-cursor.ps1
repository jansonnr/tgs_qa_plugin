#Requires -Version 5.1
<#
.SYNOPSIS
  Устанавливает tgs-qa-cursor в Cursor (local plugin) и готовит MCP zephyr-scale-mcp.

.DESCRIPTION
  1) Клонирует репозиторий (или использует уже скачанный).
  2) Junction: %USERPROFILE%\.cursor\plugins\local\tgs-qa-cursor -> ...\plugins\tgs-qa-cursor
  3) Зависимости MCP: uv sync (если есть uv) иначе venv + pip install -e .
  4) Опционально создаёт шаблон %APPDATA%\zephyr-scale-mcp\config.json (без секретов в вывод).

.PARAMETER CloneDir
  Куда клонировать репозиторий, если -UseThisRepo не задан.

.PARAMETER RepoUrl
  URL git-репозитория marketplace.

.PARAMETER UseThisRepo
  Не клонировать: взять корень репо от каталога scripts\ (откуда запущен install из git clone).

.PARAMETER SkipMcpDeps
  Только junction, без Python/uv.

.PARAMETER ForceJunction
  Удалить существующий local\tgs-qa-cursor (junction или папку) и создать заново.

.EXAMPLE
  irm https://raw.githubusercontent.com/jansonnr/tgs_qa_plugin/main/scripts/install-tgs-qa-cursor.ps1 | iex

.EXAMPLE
  cd C:\tools\tgs_qa_plugin
  .\scripts\install-tgs-qa-cursor.ps1 -UseThisRepo
#>
[CmdletBinding()]
param(
    [string] $CloneDir = (Join-Path $env:USERPROFILE "tools\tgs_qa_plugin"),
    [string] $RepoUrl = "https://github.com/jansonnr/tgs_qa_plugin.git",
    [switch] $UseThisRepo,
    [switch] $SkipMcpDeps,
    [switch] $ForceJunction,
    [switch] $WriteConfigTemplate
)

$ErrorActionPreference = "Stop"

function Write-Step([string] $Message) {
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Test-Command([string] $Name) {
    $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Remove-PluginLink([string] $Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return }
    $item = Get-Item -LiteralPath $Path -Force
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
        cmd /c "rmdir `"$Path`""
    } else {
        throw "Уже существует обычная папка (не junction): $Path. Переименуйте или запустите с -ForceJunction после бэкапа."
    }
}

function New-PluginJunction([string] $Link, [string] $Target) {
    $parent = Split-Path -Parent $Link
    if (-not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }
    if (Test-Path -LiteralPath $Link) {
        if ($ForceJunction) {
            Remove-PluginLink -Path $Link
        } else {
            throw "Уже есть: $Link. Используйте -ForceJunction или удалите вручную."
        }
    }
    $targetFull = (Resolve-Path -LiteralPath $Target).Path
    cmd /c "mklink /J `"$Link`" `"$targetFull`""
    if ($LASTEXITCODE -ne 0) { throw "mklink /J не удался ($Link -> $targetFull)" }
}

function Install-McpDeps([string] $McpDir) {
    if (-not (Test-Path (Join-Path $McpDir "pyproject.toml"))) {
        throw "Нет pyproject.toml: $McpDir"
    }
    Push-Location $McpDir
    try {
        if (Test-Command "uv") {
            Write-Host "uv sync в $McpDir"
            & uv sync
            if ($LASTEXITCODE -ne 0) { throw "uv sync завершился с кодом $LASTEXITCODE" }
            & uv run python -c "import zephyr_scale_mcp; print('zephyr_scale_mcp OK')"
            if ($LASTEXITCODE -ne 0) { throw "uv run: модуль не импортируется" }
            return
        }
        Write-Host "uv не найден — venv + pip install -e ."
        $py = $null
        foreach ($candidate in @("py -3.12", "py -3.11", "python")) {
            $parts = $candidate -split " "
            if (Test-Command $parts[0]) {
                $py = $candidate
                break
            }
        }
        if (-not $py) { throw "Нужен Python 3.11+ или установите uv: https://docs.astral.sh/uv/" }
        Invoke-Expression "$py -m venv .venv"
        $pip = Join-Path $McpDir ".venv\Scripts\python.exe"
        & $pip -m pip install -e .
        if ($LASTEXITCODE -ne 0) { throw "pip install -e . failed" }
        & $pip -c "import zephyr_scale_mcp; print('zephyr_scale_mcp OK')"
    } finally {
        Pop-Location
    }
}

function Write-ConfigTemplateIfAsked {
    $configDir = Join-Path $env:APPDATA "zephyr-scale-mcp"
    $configPath = Join-Path $configDir "config.json"
    if ((Test-Path -LiteralPath $configPath) -and -not $WriteConfigTemplate) {
        Write-Host "config.json уже есть: $configPath"
        return
    }
    if (-not $WriteConfigTemplate) {
        Write-Host "Шаблон config.json не создан (добавьте -WriteConfigTemplate)."
        return
    }
    New-Item -ItemType Directory -Path $configDir -Force | Out-Null
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
    Write-Host "Шаблон: $configPath — заполните токены вручную."
}

# --- main ---

Write-Step "Определение корня репозитория"
if ($UseThisRepo) {
    $RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
    Write-Host "UseThisRepo: $RepoRoot"
} else {
    if (-not (Test-Path -LiteralPath $CloneDir)) {
        if (-not (Test-Command "git")) { throw "git не найден. Установите Git или используйте -UseThisRepo из существующего clone." }
        Write-Step "git clone -> $CloneDir"
        $parent = Split-Path -Parent $CloneDir
        if (-not (Test-Path -LiteralPath $parent)) {
            New-Item -ItemType Directory -Path $parent -Force | Out-Null
        }
        & git clone $RepoUrl $CloneDir
        if ($LASTEXITCODE -ne 0) { throw "git clone failed" }
    } else {
        Write-Host "Каталог уже есть: $CloneDir (обновление: git pull вручную)."
    }
    $RepoRoot = (Resolve-Path -LiteralPath $CloneDir).Path
}

$PluginSrc = Join-Path $RepoRoot "plugins\tgs-qa-cursor"
if (-not (Test-Path -LiteralPath $PluginSrc)) {
    throw "Не найден плагин: $PluginSrc (ожидается структура team marketplace)."
}

$LocalLink = Join-Path $env:USERPROFILE ".cursor\plugins\local\tgs-qa-cursor"

Write-Step "Junction local plugin"
Write-Host "$LocalLink -> $PluginSrc"
New-PluginJunction -Link $LocalLink -Target $PluginSrc

if (-not $SkipMcpDeps) {
    Write-Step "MCP zephyr-scale-mcp"
    Install-McpDeps -McpDir (Join-Path $PluginSrc "zephyr-scale-mcp")
}

Write-ConfigTemplateIfAsked

Write-Step "Готово"
Write-Host @"

Дальше:
  1. Cursor -> Reload Window
  2. Customize -> Plugins -> включить TGS QA Cursor
  3. Токены: %APPDATA%\zephyr-scale-mcp\config.json (см. README)
  4. Проверка: /qa-help в чате

Обновление плагина: git pull в $RepoRoot , затем Reload Window.
"@
