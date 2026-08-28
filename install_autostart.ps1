# 开机自启注册脚本（A1）
#
# 作用：把 watchdog.py --loop 注册为 Windows 计划任务，实现
#   - 开机/登录后自动启动看门狗
#   - 看门狗持续检测监控进程，崩溃/停滞后自动拉起
#
# 运行方式（任选其一）：
#   1) 在 PowerShell 里执行：
#        powershell -ExecutionPolicy Bypass -File install_autostart.ps1
#   2) 或右键本文件 → "使用 PowerShell 运行"
#
# 说明：注册到当前用户，不需要管理员权限。
# 卸载：Unregister-ScheduledTask -TaskName SuiWeiboWatchdog -Confirm:$false

$ErrorActionPreference = "Stop"

$base = Split-Path -Parent $MyInvocation.MyCommand.Path
$script = Join-Path $base "watchdog.py"
$taskName = "SuiWeiboWatchdog"

try {
    $py = (Get-Command python -ErrorAction Stop).Source
} catch {
    Write-Host "未找到 python，请先安装并确保在 PATH 中" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $script)) {
    Write-Host "找不到 watchdog.py：$script" -ForegroundColor Red
    exit 1
}

Write-Host "Python : $py"
Write-Host "脚本   : $script"

$action   = New-ScheduledTaskAction -Execute $py `
                -Argument "-X utf8 `"$script`" --loop" `
                -WorkingDirectory $base
$trigger  = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet `
                -AllowStartIfOnBatteries `
                -DontStopIfGoingOnBatteries `
                -StartWhenAvailable `
                -RestartCount 3 `
                -RestartInterval (New-TimeSpan -Minutes 1)

Register-ScheduledTask -TaskName $taskName `
    -Action $action -Trigger $trigger -Settings $settings `
    -Description "岁己SUI 微博监控看门狗（开机自启 + 崩溃自拉起）" -Force | Out-Null

Write-Host ""
Write-Host "已注册开机自启任务: $taskName" -ForegroundColor Green
Write-Host "  查看状态: Get-ScheduledTask -TaskName $taskName"
Write-Host "  立即启动: Start-ScheduledTask -TaskName $taskName"
Write-Host "  移除任务: Unregister-ScheduledTask -TaskName $taskName -Confirm:`$false"
