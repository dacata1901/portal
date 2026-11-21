param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("local-backup", "local-restore", "ebs-snapshot", "cfn-rollback")]
    [string]$Action,
    [string]$BackupFile = "campus-backup.json",
    [string]$Region = "ap-southeast-2",
    [string]$StackName = "campus-event-portal",
    [string]$SnapshotDescription = "Campus Portal EBS data snapshot"
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path

function Ensure-AwsCli {
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
}

Push-Location $projectRoot
try {
    switch ($Action) {
        "local-backup" {
            & py -3 server.py backup --file $BackupFile
            if ($LASTEXITCODE -ne 0) { throw "Local database backup failed." }
        }
        "local-restore" {
            & py -3 server.py restore --file $BackupFile
            if ($LASTEXITCODE -ne 0) { throw "Local database restore failed." }
        }
        "ebs-snapshot" {
            Ensure-AwsCli
            $volumeId = & aws cloudformation describe-stacks --stack-name $StackName --region $Region --query "Stacks[0].Outputs[?OutputKey=='DataVolumeId'].OutputValue | [0]" --output text
            if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($volumeId) -or $volumeId -eq "None") {
                throw "Could not resolve DataVolumeId from stack '$StackName' in $Region."
            }
            $snapshotId = & aws ec2 create-snapshot --volume-id $volumeId --description $SnapshotDescription --region $Region --query "SnapshotId" --output text
            if ($LASTEXITCODE -ne 0) { throw "Failed to create EBS snapshot for volume '$volumeId'." }
            Write-Host "Created EBS snapshot: $snapshotId (volume: $volumeId)"
        }
        "cfn-rollback" {
            Ensure-AwsCli
            $status = & aws cloudformation describe-stacks --stack-name $StackName --region $Region --query "Stacks[0].StackStatus" --output text
            if ($LASTEXITCODE -ne 0) { throw "Could not query CloudFormation stack '$StackName' in $Region." }
            Write-Host "Current stack status: $status"
            if ($status -eq "UPDATE_FAILED") {
                & aws cloudformation rollback-stack --stack-name $StackName --region $Region
                if ($LASTEXITCODE -ne 0) { throw "CloudFormation rollback-stack failed." }
                & aws cloudformation wait stack-rollback-complete --stack-name $StackName --region $Region
                Write-Host "Stack rollback completed."
            }
            elseif ($status -eq "CREATE_FAILED") {
                Write-Host "Stack is in CREATE_FAILED; deleting failed stack..."
                & aws cloudformation delete-stack --stack-name $StackName --region $Region
                if ($LASTEXITCODE -ne 0) { throw "CloudFormation delete-stack failed." }
                & aws cloudformation wait stack-delete-complete --stack-name $StackName --region $Region
                Write-Host "Failed stack deleted."
            }
            else {
                Write-Host "No active failure requiring rollback. Latest stack events:"
                & aws cloudformation describe-stack-events --stack-name $StackName --region $Region --max-items 5 --output table
            }
        }
    }
}
finally {
    Pop-Location
}
