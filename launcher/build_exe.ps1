$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

Write-Output "== 1/2: PyInstaller bilan .exe quryapmiz =="
pyinstaller launcher/YouTubeDownloader.spec --noconfirm
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller muvaffaqiyatsiz tugadi (kod: $LASTEXITCODE)"
}

function Resolve-RealExe {
    param([string]$Name)
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $cmd) {
        throw "$Name tizim PATH'ida topilmadi. Avval o'rnating (masalan: winget install Gyan.FFmpeg), so'ng qayta urining."
    }
    $item = Get-Item $cmd.Source
    if ($item.LinkType) {
        $target = $item.Target
        if ($target -is [array]) { return $target[0] }
        return $target
    }
    return $cmd.Source
}

Write-Output ""
Write-Output "== 2/2: ffmpeg/ffprobe'ni runtime papkasiga joylayapmiz =="
$distDir = Join-Path $repoRoot "dist\YouTubeDownloader"
$runtimeFfmpegDir = Join-Path $distDir "runtime\ffmpeg\bin"
New-Item -ItemType Directory -Force -Path $runtimeFfmpegDir | Out-Null

$ffmpegSrc = Resolve-RealExe "ffmpeg"
$ffprobeSrc = Resolve-RealExe "ffprobe"
Write-Output "ffmpeg manbasi:  $ffmpegSrc"
Write-Output "ffprobe manbasi: $ffprobeSrc"

Copy-Item $ffmpegSrc (Join-Path $runtimeFfmpegDir "ffmpeg.exe") -Force
Copy-Item $ffprobeSrc (Join-Path $runtimeFfmpegDir "ffprobe.exe") -Force

Write-Output ""
Write-Output "== Tayyor =="
Write-Output "Dastur: $distDir\YouTubeDownloader.exe"
