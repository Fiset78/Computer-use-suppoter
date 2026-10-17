# pc-agent 실행 창 바로가기를 만든다 (처음 한 번).
# 사용법 (프로젝트 폴더에서):
#   powershell -ExecutionPolicy Bypass -File install_shortcut.ps1                  # 바탕화면 바로가기
#   powershell -ExecutionPolicy Bypass -File install_shortcut.ps1 -Startup         # + Windows 로그인 때 최소화 상태로 자동 실행
#   powershell -ExecutionPolicy Bypass -File install_shortcut.ps1 -RemoveStartup   # 자동 실행 끄기
param(
    [switch]$Startup,
    [switch]$RemoveStartup
)
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$startupLink = Join-Path ([Environment]::GetFolderPath("Startup")) "pc-agent.lnk"

if ($RemoveStartup) {
    if (Test-Path $startupLink) {
        Remove-Item $startupLink
        Write-Host "자동 실행을 껐습니다."
    } else {
        Write-Host "자동 실행이 설정돼 있지 않습니다."
    }
    exit 0
}

$pyw = Join-Path $root ".venv\Scripts\pythonw.exe"
if (-not (Test-Path $pyw)) {
    Write-Host "가상환경이 없습니다. 먼저 프로젝트 폴더에서 'uv sync'를 실행하세요."
    exit 1
}
$shell = New-Object -ComObject WScript.Shell
$app = "`"$(Join-Path $root 'app.py')`""

function New-AgentLink([string]$path, [string]$arguments, [int]$windowStyle) {
    $link = $shell.CreateShortcut($path)
    $link.TargetPath = $pyw                  # pythonw: 콘솔 창 없이 실행
    $link.Arguments = $arguments
    $link.WorkingDirectory = $root
    $link.WindowStyle = $windowStyle         # 1 = 보통, 7 = 최소화
    $link.Description = "pc-agent 실행 창"
    $link.Save()
}

$desktopLink = Join-Path ([Environment]::GetFolderPath("Desktop")) "pc-agent.lnk"
New-AgentLink $desktopLink $app 1
Write-Host "바탕화면 바로가기를 만들었습니다: $desktopLink"

if ($Startup) {
    New-AgentLink $startupLink "$app --minimized" 7
    Write-Host "Windows에 로그인하면 최소화된 상태로 자동 실행됩니다: $startupLink"
    Write-Host "지금 바로 쓰려면 바탕화면 아이콘으로 한 번 켜 두세요. 끄려면 -RemoveStartup"
}
