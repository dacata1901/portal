import json
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.benchmark_e import run_benchmark


class _CfnLoader(yaml.SafeLoader):
    pass


for _tag in (
    "!Ref",
    "!Sub",
    "!GetAtt",
    "!Select",
    "!GetAZs",
    "!Equals",
    "!If",
    "!Not",
    "!And",
    "!Or",
    "!Join",
    "!FindInMap",
    "!Base64",
):
    _CfnLoader.add_constructor(
        _tag,
        lambda loader, node, tag=_tag: {
            tag: loader.construct_scalar(node)
            if isinstance(node, yaml.ScalarNode)
            else loader.construct_sequence(node)
            if isinstance(node, yaml.SequenceNode)
            else loader.construct_mapping(node)
        },
    )


class AwsIacAndBenchmarkTests(unittest.TestCase):
    def test_cloudformation_template_has_cognito_rds_and_monitoring(self):
        template_path = ROOT / "deploy" / "aws" / "campus-ec2.yaml"
        doc = yaml.load(template_path.read_text(encoding="utf-8"), Loader=_CfnLoader)

        expected_params = {
            "ArtifactBucket",
            "ArtifactKey",
            "AllowedCidr",
            "InstanceType",
            "UbuntuAmi",
            "AuthMode",
            "DatabaseUrl",
            "CognitoRegion",
            "CognitoUserPoolId",
            "CognitoClientId",
            "CognitoDomain",
            "CognitoRedirectUri",
            "CognitoLogoutUri",
            "ProvisionCognito",
            "ProvisionRds",
            "DbMasterPassword",
        }
        self.assertTrue(expected_params.issubset(doc["Parameters"].keys()))

        self.assertIn("CreateCognitoResources", doc["Conditions"])
        self.assertIn("CreateRdsResources", doc["Conditions"])

        resources = doc["Resources"]
        for logical_id in (
            "PortalVpc",
            "PortalSubnet",
            "PortalSubnetB",
            "PortalSecurityGroup",
            "PortalInstance",
            "PortalDataVolume",
            "CampusUserPool",
            "CampusUserPoolDomain",
            "CampusUserPoolClient",
            "CampusStudentsGroup",
            "CampusOrganizersGroup",
            "CampusAdminsGroup",
            "PortalRdsSecurityGroup",
            "PortalDbSubnetGroup",
            "PortalPostgresInstance",
            "PortalHighCpuAlarm",
            "PortalStatusCheckAlarm",
            "PortalCloudWatchDashboard",
        ):
            self.assertIn(logical_id, resources)

        self.assertEqual(resources["CampusUserPool"]["Condition"], "CreateCognitoResources")
        self.assertEqual(resources["PortalPostgresInstance"]["Condition"], "CreateRdsResources")
        self.assertTrue(resources["PortalPostgresInstance"]["Properties"]["StorageEncrypted"])

        dashboard_body = resources["PortalCloudWatchDashboard"]["Properties"]["DashboardBody"]["!Sub"]
        rendered = dashboard_body.replace("${AWS::Region}", "ap-southeast-2").replace("${PortalInstance}", "i-123456")
        parsed_dashboard = json.loads(rendered)
        self.assertGreaterEqual(len(parsed_dashboard["widgets"]), 2)

        for output_key in (
            "ApplicationUrl",
            "HealthCheckUrl",
            "InstanceId",
            "DataVolumeId",
            "DashboardName",
            "CognitoUserPoolId",
            "CognitoClientId",
            "CognitoDomain",
            "RdsEndpoint",
        ):
            self.assertIn(output_key, doc["Outputs"])

    def test_benchmark_e_produces_valid_report(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            report_path = Path(tmpdir) / "bench.json"
            report = run_benchmark(str(report_path))
            loaded = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertTrue(report["ok"])
            self.assertTrue(loaded["auditBefore"]["ok"])
            self.assertTrue(loaded["auditAfter"]["ok"])
            self.assertEqual(loaded["workloadE1"]["http201Count"], 20)
            self.assertEqual(loaded["workloadE1"]["http409EventFullCount"], 80)
            self.assertGreater(loaded["workloadE1"]["latency"]["p95Ms"], 0)
            self.assertTrue(loaded["workloadE2"]["faultInjected"])
            self.assertTrue(loaded["workloadE2"]["allReplayedHeaderTrue"])
            self.assertEqual(loaded["workloadE3"]["conflictStatus"], 409)
