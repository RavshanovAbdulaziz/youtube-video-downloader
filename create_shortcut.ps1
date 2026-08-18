# Ish stoliga "YouTube Downloader" yorlig'ini yaratadi (create_shortcut.bat
# ichidan chaqiriladi). Yorliq start.bat'ni ishga tushiradi — ya'ni tray
# rejimi, konsol oynasisiz.

$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$target = Join-Path $root 'start.bat'

if (-not (Test-Path $target)) {
    Write-Output "XATO: start.bat topilmadi: $target"
    exit 1
}

$shell = New-Object -ComObject WScript.Shell
$desktop = $shell.SpecialFolders('Desktop')
$linkPath = Join-Path $desktop 'YouTube Downloader.lnk'

$link = $shell.CreateShortcut($linkPath)
$link.TargetPath = $target
$link.WorkingDirectory = $root
$link.Description = "YouTube Downloader - tray rejimida ishga tushirish"
# 7 = minimallashtirilgan: start.bat darhol yopiladi, shunda qora oyna
# ko'zga tashlanmaydi (dastur tray'da ishlashda davom etadi).
$link.WindowStyle = 7

$icon = Join-Path $root 'launcher\icon.ico'
if (Test-Path $icon) {
    $link.IconLocation = $icon
}

$link.Save()

Write-Output "Yaratildi: $linkPath"
