$env:AWS_CONFIG_FILE = Join-Path $PSScriptRoot '.aws\config'
$env:AWS_SHARED_CREDENTIALS_FILE = Join-Path $PSScriptRoot '.aws\credentials'
$env:AWS_LOGIN_CACHE_DIRECTORY = Join-Path $PSScriptRoot '.aws\login-cache'
$env:AWS_PROFILE = 'pathlock'
$env:AWS_REGION = 'ap-southeast-2'
$env:Path = "$env:LOCALAPPDATA\Programs\Amazon\AWSCLIV2;$env:USERPROFILE\.local\bin;$env:Path"
