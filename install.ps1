param(
    [string]$penv,
    [switch]$SetEnvVariables  # Optional switch to set environment variables
)

function ktransw_install {
    Write-Output "Installing ktransw ..."

    # Install Python dependencies
    pip3 install -r .\deps\ktransw\requirements.txt

    # Add ktransw to PATH
    if ($SetEnvVariables) {
      $global:NEWPATH = $global:NEWPATH + ";$PSScriptRoot\deps\ktransw\bin;$PSScriptRoot\deps\ktransw\deps\gpp"
      Write-Output "Added to PATH: $PSScriptRoot\deps\ktransw\bin"
      Write-Output "Added to PATH: $PSScriptRoot\deps\ktransw\deps\gpp"
    } else {
        Write-Output "Skipping adding to ktransw"
    }
}

function yaml_install {
    Write-Output "Installing yamljson2xml ..."
    Push-Location "$PSScriptRoot\deps\yamljson2xml"
    python -m pip install .
    Pop-Location

    # Add yamljson2xml to PATH
    if ($SetEnvVariables) {
      $global:NEWPATH = $global:NEWPATH + ";$PSScriptRoot\deps\yamljson2xml\src"
      Write-Output "Added to PATH: $PSScriptRoot\deps\yamljson2xml\src"
    } else {
        Write-Output "Skipping adding yamljson2xml to path"
    }
}

function rossum_install {
    Write-Output "Installing rossum ..."

    # Install Python dependencies
    pip3 install -r requirements.txt

    # Add rossum to PATH
    if ($SetEnvVariables) {
      $global:NEWPATH = $global:NEWPATH + ";$PSScriptRoot\bin"
      Write-Output "Added to PATH: $PSScriptRoot\bin"
    } else {
        Write-Output "Skipping adding rossum to path"
    }

    # Set environment variables if the switch is provided
    if ($SetEnvVariables) {
        Write-Output "Setting environment variables..."
        [Environment]::SetEnvironmentVariable("ROSSUM_CORE_VERSION", "V910-1", "User")
        [Environment]::SetEnvironmentVariable("ROSSUM_PKG_PATH", "", "User")
        [Environment]::SetEnvironmentVariable("ROSSUM_SERVER_IP", "127.0.0.1", "User")
    } else {
        Write-Output "Skipping setting rossum environment variables."
    }
}

# Activate Python environment if provided
if ($penv) {
    $pactivate = Join-Path $penv "Scripts\Activate.ps1"
    Write-Output "Activating Python environment: $pactivate"
    & $pactivate
}

# Get current PATH environment variable
$OLDPATH = [System.Environment]::GetEnvironmentVariable('PATH', 'User')
$global:NEWPATH = $OLDPATH

# Run installations
ktransw_install
yaml_install
rossum_install

# Update PATH environment variable
if ($SetEnvVariables) {
  [Environment]::SetEnvironmentVariable("PATH", "$global:NEWPATH", "User")
  Write-Output "Updated PATH environment variable."
} else {
  Write-Output "Skipping setting environment variables."
}

# Deactivate Python environment if activated
if ($penv) {
    $pdeactivate = Join-Path $penv "Scripts\deactivate.ps1"
    if (Test-Path $pdeactivate) {
        Write-Output "Deactivating Python environment: $pdeactivate"
        & $pdeactivate
    } else {
        Write-Output "Deactivate script not found."
    }
}
