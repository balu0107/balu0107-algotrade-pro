# Stops every backend/frontend process belonging to this project - matched by
# whether a process's own command line references this project's backend/ or
# frontend/ subfolder, not by port number or exact invocation style. That
# means it works no matter how things were started (start_all.bat,
# start_server.bat, or a plain manual uvicorn/npm command), and it correctly
# kills BOTH uvicorn's --reload supervisor and its worker together: the
# listening socket is typically owned by the worker child, not the parent, so
# a plain "kill whatever's listening on :9999, with its tree" can miss and
# orphan the supervisor.
#
# Deliberately narrower than "any process whose command line mentions this
# project's path": that broader check also matched this very script's own
# PowerShell host and the shell it was launched from (both legitimately have
# the project path in their own command line as an argument), killing them
# mid-run. Restricting to python.exe/node.exe AND the backend/frontend
# subfolder specifically avoids that, and avoids ever touching an unrelated
# editor/terminal that merely has this project open somewhere.
$root = (Get-Item $PSScriptRoot).FullName.TrimEnd('\')
$backendPath = Join-Path $root 'backend'
$frontendPath = Join-Path $root 'frontend'

$procs = Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -and
    ($_.Name -eq 'python.exe' -or $_.Name -eq 'node.exe') -and
    ($_.CommandLine.Contains($backendPath) -or $_.CommandLine.Contains($frontendPath))
}

if (-not $procs) {
    Write-Host "Nothing running for this project (checked for processes referencing $root)."
    exit
}

foreach ($p in $procs) {
    Write-Host "Stopping PID $($p.ProcessId): $($p.CommandLine)"
    Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
}

Write-Host "Done."
