param([switch]$Console)

$ErrorActionPreference = 'Stop'
# 默认使用 pythonw 启动原生窗口；调试时可选择在当前终端显示 Python 异常。
$localControlEntry = Join-Path $PSScriptRoot 'app.py'
if ($Console) {
    & python $localControlEntry
    exit $LASTEXITCODE
}
$localControlPython = (Get-Command pythonw.exe -ErrorAction Stop).Source
Start-Process -FilePath $localControlPython -ArgumentList ('"' + $localControlEntry + '"') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden
