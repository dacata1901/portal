# AWS demo deployment

This deployment uses a single Ubuntu EC2 instance and a separate encrypted gp3
EBS volume for SQLite. It is intentionally small for a classroom project, not a
high-availability or production architecture. Seed data and bookings survive an
EC2 reboot because the database is stored on the EBS data volume. Deleting the
CloudFormation stack deletes the instance **and the database volume**.

## Requirements

- An AWS account with permissions to create CloudFormation stacks, EC2/VPC
  resources, IAM roles and profiles, and S3 buckets/objects.
- AWS CLI v2 installed and authenticated (`aws configure` or an existing
  credential profile).
- Windows PowerShell 5.1+; choose a region that supports EC2 `t3.micro` and
  Canonical's Ubuntu 24.04 SSM AMI parameter.
- An IPv4 CIDR for the users who need to access the demo. Prefer a single
  address `/32`; the portal's demo identities can be impersonated, so never
  expose it as `0.0.0.0/0`.

The script packages only `server.py`, `fixtures.json`, `backend/`, and `dist/`.
It creates a private, encrypted S3 bucket, uploads the package, then deploys
`campus-ec2.yaml`. The instance role can read only that package object. The
template creates an isolated VPC, public subnet, Internet gateway, security
group, one EC2 instance, and the encrypted EBS data volume. No SSH rule is
created; port 4173 is the only inbound port and is limited to the CIDR entered.

## Deploy

From the project root:

```powershell
.\deploy\aws\deploy-aws.ps1 -Region ap-southeast-1
```

Optionally specify `-StackName`, `-AllowedCidr`, and `-Region`. The CloudFormation
stack reports an application URL and `/healthz`. Wait a few minutes after stack
creation for the Ubuntu bootstrap to install packages, mount EBS, and start the
service. If `/healthz` is not ready, inspect the instance's cloud-init output in
the EC2 console or the stack events in CloudFormation.

The first request seeds the reference data. To verify the known result, choose
the demo student and confirm Cloud Lab shows 20 seats available; the seeded
catalog also has 86/120 AI & You registrations and a full Hack Day event. Use
the student, organizer, and administrator demo accounts exposed by the UI.
As an organizer, open the organizer dashboard and choose **Tạo sự kiện**. A
published event appears in the public catalog, starts with its full capacity,
and is immediately available for student registration. The organizer dashboard
shows its roster and can export active registrations as CSV.

## Important limitations

- `X-Demo-User` is not authentication; any allowed visitor can impersonate a
  student or organizer. Restrict the network range and use synthetic data only.
- HTTP is unencrypted. This is suitable only for a controlled classroom demo.
- SQLite and `BEGIN IMMEDIATE` are correct for this one-instance setup but do
  not support multiple application instances or shared network filesystems.
- The deploy script is for a fresh classroom deployment. It uploads a new
  release each run; changing the EC2 user-data parameter does not itself run
  cloud-init again on an existing instance. Do not treat rerunning it as an
  application upgrade. For a new release, plan an explicit instance replacement
  and back up the EBS database first.
- AWS charges for EC2, EBS, S3, and data transfer may apply. Check current
  regional prices and free-tier eligibility before deployment.

For production, add verified OIDC/JWT identity and server-side role mapping,
HTTPS, a managed PostgreSQL database with row-level locking/unique idempotency
constraints, backup/restore drills, monitoring, alerting, and a deployment
pipeline. Do not add real student data or financial actions to this demo.

## Remove AWS resources

Save the private bucket name printed by the deployment script. When the demo is
finished, delete the CloudFormation stack (this deletes the EC2 instance and its
EBS database volume), then remove the uploaded package and its bucket:

```powershell
aws cloudformation delete-stack --stack-name campus-event-portal --region ap-southeast-1
aws cloudformation wait stack-delete-complete --stack-name campus-event-portal --region ap-southeast-1
aws s3 rm s3://YOUR-PRINTED-BUCKET-NAME --recursive --region ap-southeast-1
aws s3 rb s3://YOUR-PRINTED-BUCKET-NAME --region ap-southeast-1
```

Replace the stack name, region, and bucket name with the values used for your
deployment. Deleting the stack permanently deletes the event database.
