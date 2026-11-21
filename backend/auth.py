"""Authentication helpers for local demos and Amazon Cognito access tokens."""
import os


class AuthenticationError(Exception):
    pass


_jwks = {}
_ROLE_GROUPS = {
    "student": "Students",
    "organizer": "Organizers",
    "administrator": "Administrators",
}


def identity_from_headers(headers):
    mode = os.environ.get("PORTAL_AUTH_MODE", "demo").lower()
    if mode == "demo":
        return {"user_id": headers.get("X-Demo-User", ""), "groups": None}
    if mode != "cognito":
        raise AuthenticationError("Cấu hình xác thực không hợp lệ")

    authorization = headers.get("Authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise AuthenticationError("Thiếu access token")

    region = os.environ.get("COGNITO_REGION", "")
    pool_id = os.environ.get("COGNITO_USER_POOL_ID", "")
    client_id = os.environ.get("COGNITO_CLIENT_ID", "")
    if not region or not pool_id or not client_id:
        raise AuthenticationError("Cognito chưa được cấu hình")

    issuer = f"https://cognito-idp.{region}.amazonaws.com/{pool_id}"
    jwks_url = f"{issuer}/.well-known/jwks.json"
    try:
        import jwt
        from jwt import PyJWKClient
    except ImportError as exc:
        raise RuntimeError("Cognito authentication requires PyJWT[crypto]") from exc
    try:
        client = _jwks.get(jwks_url)
        if client is None:
            client = PyJWKClient(jwks_url, cache_keys=True)
            _jwks[jwks_url] = client
        signing_key = client.get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            issuer=issuer,
            audience=os.environ.get('COGNITO_RESOURCE_AUDIENCE') or None,
            options={"verify_aud": bool(os.environ.get('COGNITO_RESOURCE_AUDIENCE')), "require": ["exp", "iss", "token_use", "client_id"]},
            leeway=60,
        )
    except (jwt.PyJWTError, OSError, ValueError) as exc:
        raise AuthenticationError("Access token không hợp lệ hoặc đã hết hạn") from exc

    if claims.get("token_use") != "access" or claims.get("client_id") != client_id:
        raise AuthenticationError("Access token không thuộc ứng dụng này")
    if claims.get('aud') and not os.environ.get('COGNITO_RESOURCE_AUDIENCE'):
        raise AuthenticationError('Ứng dụng chưa cấu hình resource audience của access token này')
    user_id = claims.get("username") or claims.get("cognito:username")
    if not isinstance(user_id, str) or not user_id:
        raise AuthenticationError("Token thiếu username")
    groups = claims.get("cognito:groups", [])
    if not isinstance(groups, list) or not all(isinstance(group, str) for group in groups):
        raise AuthenticationError("Danh sách nhóm trong token không hợp lệ")
    return {"user_id": user_id, "groups": groups}


def identity_matches_role(identity, role):
    groups = identity.get("groups")
    return groups is None or _ROLE_GROUPS.get(role) in groups


