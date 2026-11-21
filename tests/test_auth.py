import os
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from backend.auth import AuthenticationError, identity_from_headers, identity_matches_role


class IdentityTests(unittest.TestCase):
    def test_demo_identity_and_role_mapping(self):
        with patch.dict(os.environ, {"PORTAL_AUTH_MODE": "demo"}):
            identity = identity_from_headers({"X-Demo-User": "stu-10001"})
        self.assertEqual(identity, {"user_id": "stu-10001", "groups": None})
        self.assertTrue(identity_matches_role(identity, "student"))

    def test_cognito_rejects_missing_bearer_token(self):
        with patch.dict(os.environ, {"PORTAL_AUTH_MODE": "cognito"}):
            with self.assertRaises(AuthenticationError):
                identity_from_headers({})

    def test_cognito_groups_must_match_database_role(self):
        self.assertTrue(identity_matches_role(
            {"user_id": "org-1", "groups": ["Organizers"]}, "organizer"
        ))
        self.assertFalse(identity_matches_role(
            {"user_id": "org-1", "groups": ["Students"]}, "organizer"
        ))

    def test_signed_cognito_access_token_is_verified(self):
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_key = private_key.public_key()
        claims = {
            "iss": "https://cognito-idp.ap-southeast-2.amazonaws.com/ap-southeast-2_test",
            "exp": int(time.time()) + 300,
            "token_use": "access",
            "client_id": "test-client",
            "username": "org-1",
            "cognito:groups": ["Organizers"],
        }
        token = jwt.encode(claims, private_key, algorithm="RS256")
        key_client = SimpleNamespace(
            get_signing_key_from_jwt=lambda value: SimpleNamespace(key=public_key)
        )
        env = {
            "PORTAL_AUTH_MODE": "cognito",
            "COGNITO_REGION": "ap-southeast-2",
            "COGNITO_USER_POOL_ID": "ap-southeast-2_test",
            "COGNITO_CLIENT_ID": "test-client",
        }
        with patch.dict(os.environ, env), patch("jwt.PyJWKClient", return_value=key_client), patch("backend.auth._jwks", {}):
            identity = identity_from_headers({"Authorization": f"Bearer {token}"})
        self.assertEqual(identity, {"user_id": "org-1", "groups": ["Organizers"]})

    def test_unknown_auth_mode_is_explicitly_rejected(self):
        with patch.dict(os.environ, {"PORTAL_AUTH_MODE": "unknown"}):
            with self.assertRaises(AuthenticationError):
                identity_from_headers({})


if __name__ == "__main__":
    unittest.main()
