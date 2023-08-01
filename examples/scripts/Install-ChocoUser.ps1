# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

[cmdletbinding()]
Param(
    [Parameter(Mandatory=$true)]
    [string]$PackageId,

    [Parameter(Mandatory=$false)]
    [string]$PackageArguments
)

function Show-Notification {
    [cmdletbinding()]
    Param (
        [string]
        $ToastTitle,

        [string]
        [parameter(ValueFromPipeline)]
        $ToastText
    )

    [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
    $Template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)

    $RawXml = [xml] $Template.GetXml()
    ($RawXml.toast.visual.binding.text|where {$_.id -eq "1"}).AppendChild($RawXml.CreateTextNode($ToastTitle)) > $null
    ($RawXml.toast.visual.binding.text|where {$_.id -eq "2"}).AppendChild($RawXml.CreateTextNode($ToastText)) > $null

    $SerializedXml = New-Object Windows.Data.Xml.Dom.XmlDocument
    $SerializedXml.LoadXml($RawXml.OuterXml)

    $Toast = [Windows.UI.Notifications.ToastNotification]::new($SerializedXml)
    $Toast.Tag = "AZBake"
    $Toast.Group = "AZBake"
    $Toast.ExpirationTime = [DateTimeOffset]::Now.AddMinutes(1)

    $Notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("AZBake")
    $Notifier.Show($Toast);
}

# Don't use C:\Windows\Temp as requires admin elevation
# Add logging
# Check if folder exists
$LogDir = "C:\Temp"
if (-not (Test-Path -LiteralPath $LogDir)) {
    New-Item -Path $LogDir -ItemType Directory -ErrorAction Stop | Out-Null #-Force
}

$Log = Join-Path -Path $LogDir -ChildPath "chocouserinstall.log"
if (-not (Test-Path -LiteralPath $Log)) {
    New-Item -Path $Log -ItemType File -ErrorAction Stop | Out-Null #-Force
}

Add-Content -Path $log -Value "Starting check to see if user has administrator privileges. $(Get-Date)"

# Unable to use below as the Administrator group isn't shown.
# ([Security.Principal.WindowsIdentity]::GetCurrent().Groups | Select-String 'S-1-5-32-544')

# Check if user is in administrator group
if ($null -ne (whoami /groups /fo csv | ConvertFrom-Csv | Where-Object { $_.SID -eq "S-1-5-32-544" })) {

    Add-Content -Path $log -Value "User has Administrator privileges: $(Get-Date)"

    # Self-elevate the script if required
    if (-Not ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] 'Administrator')) {
        if ([int](Get-CimInstance -Class Win32_OperatingSystem | Select-Object -ExpandProperty BuildNumber) -ge 6000) {

            # Bound Arguments aren't filling in the command line.
            #$CommandLine = "-File `"" + $MyInvocation.MyCommand.Path + "`" " + $MyInvocation.BoundArguments
            $CommandLine = "-File `"" + $MyInvocation.MyCommand.Path + "`" "

            foreach ($param in $MyInvocation.BoundParameters.GetEnumerator()){
                $CommandLine += " -" + $param.key + " """ + $param.value + """"
            }

            Start-Process -FilePath PowerShell.exe -Verb Runas -ArgumentList $CommandLine -WindowStyle Hidden
            Exit
        }
    }
}

Add-Content -Path $log -Value "Deploying: $($PackageId): $($PackageArguments): $(Get-Date)"

# Check if package is installed
$toastTitle = "DevBox User Install"
Show-Notification -ToastTitle $toastTitle -ToastText "Checking for $PackageId"
Add-Content -Path $log -Value "Checking for $($PackageId): $(Get-Date)"
$current = & choco.exe list --exact $PackageId --local-only --limit-output

if (-not $current) {
    Show-Notification -ToastTitle $toastTitle -ToastText "Installing $PackageId"
    Add-Content -Path $log -Value "Begin installing $($PackageId): $(Get-Date)"

    & choco.exe install $PackageId $($PackageArguments -split(" "))

    if ($LASTEXITCODE -ne 0) {
        Show-Notification -ToastTitle $toastTitle -ToastText "Failed Installing $PackageId"
        Add-Content -Path $log -Value "Failed to install $($PackageId): $(Get-Date)"
        Add-Content -Path $log -Value "Chocolatey log files are in C:\Windows\ProgramData\chocoportable\logs : $(Get-Date)"
        return 1
    }
    Show-Notification -ToastTitle $toastTitle -ToastText "Finished installing $PackageId"
    Add-Content -Path $log -Value "Finished installing $($PackageId): $(Get-Date)"
}
else {
    Show-Notification -ToastTitle $toastTitle -ToastText "$PackageId already installed."
    Add-Content -Path $log -Value "$($PackageId) already installed: $(Get-Date)"
}