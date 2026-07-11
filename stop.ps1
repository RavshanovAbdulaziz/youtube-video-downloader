$conn = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue

if ($conn) {
    $procId = ($conn | Select-Object -First 1).OwningProcess
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$procId" -ErrorAction SilentlyContinue
    if ($proc) {
        Write-Output "Server topildi (PID: $procId, $($proc.Name)). To'xtatilmoqda..."
        $result = $proc | Invoke-CimMethod -MethodName Terminate
        if ($result.ReturnValue -eq 0) {
            Write-Output "Server to'xtatildi."
        } else {
            Write-Output "Serverni to'xtatib bo'lmadi (kod: $($result.ReturnValue))."
        }
    } else {
        Write-Output "Port 8000 band, lekin jarayon topilmadi."
    }
} else {
    Write-Output "Server ishlamayapti (8000-port band emas)."
}
