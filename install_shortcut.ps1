# 바탕화면에 pc-agent 실행 창 바로가기를 만든다 (처음 한 번).
# 사용법 (프로젝트 폴더에서):  powershell -ExecutionPolicy Bypass -File install_shortcut.ps1
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$pyw = Join-Path $root ".venv\Scripts\pythonw.exe"
if (-not (Test-Path $pyw)) {
    Write-Host "가상환경이 없습니다. 먼저 프로젝트 폴더에서 'uv sync'를 실행하세요."
    exit 1
}
$desktop = [Environment]::GetFolderPath("Desktop")
$path = Join-Path $desktop "pc-agent.lnk"
$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut($path)
$link.TargetPath = $pyw                      # pythonw: 콘솔 창 없이 실행
$link.Arguments = "`"$(Join-Path $root 'app.py')`""
$link.WorkingDirectory = $root
$link.Description = "pc-agent 실행 창"
$link.Save()
Write-Host "바로가기를 만들었습니다: $path"
