# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

# Check if user is in administrator group
if ($null -ne (whoami /groups /fo csv | ConvertFrom-Csv | Where-Object { $_.SID -eq "S-1-5-32-544" })) {

    # Self-elevate the script if required
    if (-Not ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] 'Administrator')) {
        if ([int](Get-CimInstance -Class Win32_OperatingSystem | Select-Object -ExpandProperty BuildNumber) -ge 6000) {

            $CommandLine = "-File `"" + $MyInvocation.MyCommand.Path + "`" "

            Start-Process -FilePath PowerShell.exe -Verb Runas -ArgumentList $CommandLine -WindowStyle Hidden
            Exit
        }
    }
}
else {
    Exit
}

Set-ItemProperty 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Policies\\System' -Name ConsentPromptBehaviorAdmin -Value 5 -type DWORD