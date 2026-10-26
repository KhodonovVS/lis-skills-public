$ErrorActionPreference = 'Continue'
# Test that libpq.dll + its dependencies load in a 32-bit process.
# Run ONLY via 32-bit PowerShell:
#   & "$env:SystemRoot\SysWOW64\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File test_libpq.ps1
param([string]$BinDir = 'C:\Program Files (x86)\Embarcadero\Studio\20.0\bin')
Write-Output "=== files in bin:"
foreach ($f in 'libpq.dll','ssleay32.dll','libeay32.dll','libintl-8.dll','libiconv-2.dll','msvcr120.dll','msvcp120.dll') {
  $p = Join-Path $BinDir $f
  if (Test-Path $p) { Write-Output ("  OK  " + $f + "  " + (Get-Item $p).Length) }
  else { Write-Output ("  MISSING " + $f) }
}
$env:PATH = $BinDir + ';' + $env:PATH
$src = @'
using System;
using System.Runtime.InteropServices;
public class NN {
  [DllImport("kernel32", SetLastError=true)]
  public static extern IntPtr LoadLibrary(string p);
}
'@
Add-Type -TypeDefinition $src
$h = [NN]::LoadLibrary("libpq.dll")
if ($h -ne [IntPtr]::Zero) { Write-Output "TEST: libpq.dll LOADED OK" }
else { $e = New-Object ComponentModel.Win32Exception ([Runtime.InteropServices.Marshal]::GetLastWin32Error()); Write-Output ("TEST: FAIL - " + $e.Message) }
