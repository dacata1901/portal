param(
    [string]$Region = "ap-southeast-2",
    [string]$StackName = "campus-event-portal",
    [string]$AllowedCidr = "",
    [ValidateSet("demo", "cognito")]
    [string]$AuthMode = "demo",
    [string]$DatabaseUrl = "",
    [string]$CognitoRegion = "",
    [string]$CognitoUserPoolId = "",
    [string]$CognitoClientId = "",
    [string]$CognitoDomain = "",
    [string]$CognitoRedirectUri = "",
    [string]$CognitoLogoutUri = "",
    [switch]$ProvisionCognito,
    [switch]$ProvisionRds,
    [string]$DbMasterPassword = "",
    [switch]$DisableCloudflareTunnel,
    [string]$OrganizerPassword = "",
    [string]$AdminPassword = ""
)

$ErrorActionPreference = "Stop"

foreach ($pw in @(@{ Name = "OrganizerPassword"; Value = $OrganizerPassword }, @{ Name = "AdminPassword"; Value = $AdminPassword })) {
    if (-not [string]::IsNullOrEmpty($pw.Value)) {
        if ($pw.Value.Length -lt 12 -or $pw.Value.Length -gt 128) { throw "$($pw.Name) must be 12-128 characters." }
        if ($pw.Value -match "['`"\r\n]") { throw "$($pw.Name) must not contain quotes or line breaks." }
    }
}

$defaultAws = Join-Path $env:ProgramFiles "Amazon\AWSCLIV2\aws.exe"
if ((-not (Get-Command aws.exe -ErrorAction SilentlyContinue)) -and (Test-Path $defaultAws)) {
    $env:Path = "$(Split-Path $defaultAws -Parent);$env:Path"
}
if (-not (Get-Command aws.exe -ErrorAction SilentlyContinue)) {
    & py -3 -m awscli --version *> $null
    if ($LASTEXITCODE -eq 0) {
        function script:aws { & py -3 -m awscli @args }
    }
}
if (-not (Get-Command aws -ErrorAction SilentlyContinue)) {
    throw "AWS CLI is required. Install AWS CLI and run 'aws configure' first."
}
if ($AuthMode -eq "cognito" -and (-not $ProvisionCognito) -and (
    [string]::IsNullOrWhiteSpace($CognitoRegion) -or
    [string]::IsNullOrWhiteSpace($CognitoUserPoolId) -or
    [string]::IsNullOrWhiteSpace($CognitoClientId) -or
    [string]::IsNullOrWhiteSpace($CognitoDomain)
)) {
    throw "Cognito mode requires -CognitoRegion, -CognitoUserPoolId, -CognitoClientId, and -CognitoDomain (or pass -ProvisionCognito)."
}
if ($ProvisionRds -and ([string]::IsNullOrWhiteSpace($DbMasterPassword) -or $DbMasterPassword.Length -lt 8)) {
    throw "RDS provisioning requires -DbMasterPassword with at least 8 characters."
}
if ([string]::IsNullOrWhiteSpace($AllowedCidr)) {
    try {
        $detectedIp = (Invoke-RestMethod -Uri "https://checkip.amazonaws.com" -TimeoutSec 5).ToString().Trim()
        if ($detectedIp -match '^(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)$') {
            $AllowedCidr = "$detectedIp/32"
            Write-Host "Detected public IPv4 CIDR: $AllowedCidr"
        }
    }
    catch {
        Write-Warning "Could not auto-detect public IPv4 address."
    }
}
if ([string]::IsNullOrWhiteSpace($AllowedCidr)) {
    $AllowedCidr = Read-Host "Allowed public IPv4 CIDR (recommended: your-address/32)"
}
if ($AllowedCidr -notmatch '^(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)/(?:[0-9]|[12]\d|3[0-2])$') {
    throw "Provide a valid IPv4 CIDR such as 203.0.113.10/32."
}
if ($AllowedCidr -eq "0.0.0.0/0") {
    throw "This demo uses spoofable identities and must not be exposed to the entire internet."
}

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$template = Join-Path $PSScriptRoot "campus-ec2.yaml"
$tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("campus-aws-" + [Guid]::NewGuid().ToString("N"))
$staging = Join-Path $tempRoot "package"
$archive = Join-Path $tempRoot "campus-portal.zip"
New-Item -ItemType Directory -Path $staging -Force | Out-Null

try {
    Copy-Item (Join-Path $projectRoot "server.py") $staging
    Copy-Item (Join-Path $projectRoot "fixtures.json") $staging
    if (Test-Path (Join-Path $projectRoot "requirements.txt")) {
        Copy-Item (Join-Path $projectRoot "requirements.txt") $staging
    }
    Copy-Item (Join-Path $projectRoot "backend") $staging -Recurse
    Copy-Item (Join-Path $projectRoot "dist") $staging -Recurse
    New-Item -ItemType Directory -Path (Join-Path $staging "scripts") -Force | Out-Null
    Copy-Item (Join-Path $projectRoot "scripts\set_account_password.py") (Join-Path $staging "scripts")
    Get-ChildItem -Path $staging -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
    & py -3 -c "import pathlib, sys, zipfile; src = pathlib.Path(sys.argv[1]); dst = pathlib.Path(sys.argv[2]); zf = zipfile.ZipFile(dst, 'w', zipfile.ZIP_DEFLATED); [zf.write(p, p.relative_to(src).as_posix()) for p in src.rglob('*') if p.is_file()]; zf.close()" $staging $archive
    if ($LASTEXITCODE -ne 0) { throw "Could not create the application ZIP archive." }

    $accountId = & aws sts get-caller-identity --query Account --output text --region $Region
    if ($LASTEXITCODE -ne 0) { throw "Could not read the AWS identity. Check your CLI credentials and permissions." }
    $suffix = [Guid]::NewGuid().ToString("N").Substring(0, 8)
    $bucket = "campus-portal-$accountId-$suffix"
    $key = "releases/campus-portal-$([DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ'))-$suffix.zip"

    if ($Region -eq "us-east-1") {
        & aws s3api create-bucket --bucket $bucket --region $Region | Out-Null
    } else {
        & aws s3api create-bucket --bucket $bucket --region $Region --create-bucket-configuration "LocationConstraint=$Region" | Out-Null
    }
    if ($LASTEXITCODE -ne 0) { throw "Could not create the private deployment bucket." }

    & aws s3api put-public-access-block --bucket $bucket --region $Region --public-access-block-configuration 'BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Could not secure the deployment bucket." }
    & aws s3api put-bucket-encryption --bucket $bucket --region $Region --server-side-encryption-configuration 'Rules=[{ApplyServerSideEncryptionByDefault={SSEAlgorithm=AES256}}]' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Could not enable deployment bucket encryption." }
    & aws s3 cp $archive "s3://$bucket/$key" --region $Region
    if ($LASTEXITCODE -ne 0) { throw "Could not upload the application archive." }

    $paramOverrides = @(
        "ArtifactBucket=$bucket",
        "ArtifactKey=$key",
        "AllowedCidr=$AllowedCidr",
        "AuthMode=$AuthMode"
    )
    $optionalParams = @{
        DatabaseUrl = $DatabaseUrl
        CognitoRegion = $CognitoRegion
        CognitoUserPoolId = $CognitoUserPoolId
        CognitoClientId = $CognitoClientId
        CognitoDomain = $CognitoDomain
        CognitoRedirectUri = $CognitoRedirectUri
        CognitoLogoutUri = $CognitoLogoutUri
    }
    foreach ($entry in $optionalParams.GetEnumerator()) {
        if (-not [string]::IsNullOrWhiteSpace($entry.Value)) {
            $paramOverrides += "$($entry.Key)=$($entry.Value)"
        }
    }
    if ($ProvisionCognito) {
        $paramOverrides += "ProvisionCognito=true"
    }
    if ($ProvisionRds) {
        $paramOverrides += "ProvisionRds=true"
        $paramOverrides += "DbMasterPassword=$DbMasterPassword"
    }
    if ($DisableCloudflareTunnel) { $paramOverrides += "EnableCloudflareTunnel=false" }
    if (-not [string]::IsNullOrEmpty($OrganizerPassword)) { $paramOverrides += "OrganizerPassword=$OrganizerPassword" }
    if (-not [string]::IsNullOrEmpty($AdminPassword)) { $paramOverrides += "AdminPassword=$AdminPassword" }

    Write-Host "Private deployment bucket: $bucket"
    Write-Host "Deploying stack '$StackName' in $Region (auth: $AuthMode); HTTP access restricted to $AllowedCidr."
    & aws cloudformation deploy --template-file $template --stack-name $StackName --region $Region --capabilities CAPABILITY_IAM --parameter-overrides $paramOverrides
    if ($LASTEXITCODE -ne 0) {
        throw "CloudFormation deployment failed. Review the stack events in AWS Console; the private S3 bucket may need manual cleanup."
    }

    $outputsRaw = & aws cloudformation describe-stacks --stack-name $StackName --region $Region --query "Stacks[0].Outputs" --output json
    if ($LASTEXITCODE -ne 0) { throw "Stack deployed, but its outputs could not be read." }
    $outputs = $outputsRaw | ConvertFrom-Json
    $outputMap = @{}
    foreach ($item in $outputs) {
        $outputMap[$item.OutputKey] = $item.OutputValue
    }
    Write-Host ""
    Write-Host "Application: $($outputMap['ApplicationUrl'])"
    Write-Host "Health check: $($outputMap['HealthCheckUrl'])"
    if ($outputMap.ContainsKey('DashboardName')) { Write-Host "CloudWatch Dashboard: $($outputMap['DashboardName'])" }
    if ($outputMap.ContainsKey('CognitoUserPoolId')) { Write-Host "Cognito User Pool ID: $($outputMap['CognitoUserPoolId'])" }
    if ($outputMap.ContainsKey('CognitoClientId')) { Write-Host "Cognito Client ID: $($outputMap['CognitoClientId'])" }
    if ($outputMap.ContainsKey('CognitoDomain')) { Write-Host "Cognito Domain: $($outputMap['CognitoDomain'])" }
    if ($outputMap.ContainsKey('RdsEndpoint')) { Write-Host "RDS Endpoint: $($outputMap['RdsEndpoint'])" }
    if ($outputMap.ContainsKey('TunnelUrlParameter')) {
        Write-Host "Waiting for the Cloudflare Quick Tunnel URL (first boot can take a few minutes)..."
        $tunnelUrl = ""
        for ($i = 0; $i -lt 60 -and -not $tunnelUrl; $i++) {
            $value = $null
            try { $value = & aws ssm get-parameter --name $outputMap['TunnelUrlParameter'] --region $Region --query "Parameter.Value" --output text 2>$null } catch { $value = $null }
            if ($value -and "$value" -match '^https://') { $tunnelUrl = "$value".Trim() } else { Start-Sleep -Seconds 10 }
        }
        if ($tunnelUrl) { Write-Host "Public HTTPS URL (Cloudflare): $tunnelUrl" }
        else { Write-Host "Tunnel URL not ready yet. Later run: aws ssm get-parameter --name $($outputMap['TunnelUrlParameter']) --region $Region --query Parameter.Value --output text" }
    }
    Write-Host "Save this bucket name for cleanup: $bucket"
    Write-Host "The app may take several minutes to finish its first boot."
}
finally {
    if (Test-Path $tempRoot) {
        Remove-Item -LiteralPath $tempRoot -Recurse -Force
    }
}
