function ktransw_install {
    Write-Output "Installing ktransw ..."

    #install python dependencies
    pip3 install -r .\deps\ktransw\requirements.txt

    #add ktransw to path
    $global:NEWPATH = $global:NEWPATH + ";$PSScriptRoot\deps\ktransw\bin;$PSScriptRoot\deps\ktransw\deps\gpp"
    Write-Output "Added to Path: $PSScriptRoot\deps\ktransw\bin"
    Write-Output "Added to Path: $PSScriptRoot\deps\ktransw\deps\gpp"

}

function yaml_install {
    Write-Output "Installing yamljson2xml ..."
    cd "$PSScriptRoot\deps\yamljson2xml"
    python setup.py install
    cd "$PSScriptRoot"

    #add ktransw to path
    $global:NEWPATH = $global:NEWPATH + ";$PSScriptRoot\deps\yamljson2xml\src"
    Write-Output "Added to Path: $PSScriptRoot\deps\yamljson2xml\src"

}

function rossum_install {
    Write-Output "Installing rossum ..."

    #install python dependencies
    pip3 install -r requirements.txt

    #add ktransw to path
    $global:NEWPATH = $global:NEWPATH + ";$PSScriptRoot\bin"
    Write-Output "Added to Path: $PSScriptRoot\bin"

    #add environment variables
    [Environment]::SetEnvironmentVariable("ROSSUM_CORE_VERSION", "V910-1", "User");
    [Environment]::SetEnvironmentVariable("ROSSUM_PKG_PATH", "", "User");
    [Environment]::SetEnvironmentVariable("ROSSUM_SERVER_IP", "127.0.0.1", "User");
}


#python environment
$penv=$args[0]

if ($penv) {
    $pactivate = $penv + "\Scripts\Activate.ps1"
    Write-Output $pactivate
    Invoke-Expression -Command $pactivate
}

#get environment path
$OLDPATH = [System.Environment]::GetEnvironmentVariable('PATH','User')
$global:NEWPATH = $OLDPATH

#run ktransw install
ktransw_install

#run yamljson2xml install
yaml_install

#run rossum install
rossum_install

#set Path
[Environment]::SetEnvironmentVariable("PATH", "$global:NEWPATH", "User")

if ($penv) {
    $pdeactivate = $penv + "\Scripts\deactivate"
    deactivate
}

