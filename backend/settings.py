"""Provider configuration stays outside booking transactions."""
import json
import os
from pathlib import Path
from urllib.parse import quote, urlencode
from urllib.parse import urlsplit


class ConfigurationError(RuntimeError):
    pass


def read_secret(arn, client=None):
    if not arn:
        raise ConfigurationError('Thiếu ARN của bí mật được cấu hình.')
    try:
        if client is None:
            import boto3
            client = boto3.client('secretsmanager', region_name=os.environ.get('AWS_REGION'))
        value = json.loads(client.get_secret_value(SecretId=arn)['SecretString'])
        if not isinstance(value, dict): raise ValueError()
        return value
    except Exception as error:
        # Never include SDK messages, secret contents, DSNs or credentials.
        raise ConfigurationError('Không đọc được cấu hình bí mật; kiểm tra quyền workload và định dạng JSON.') from None


def database_target(root, client=None):
    production = os.environ.get('PORTAL_ENV') == 'production'
    arn = os.environ.get('PORTAL_DATABASE_SECRET_ARN')
    if production and (os.environ.get('PORTAL_AUTH_MODE') != 'cognito' or not arn):
        raise ConfigurationError('Môi trường production cần Cognito và ARN bí mật DB; chế độ demo chỉ dành cho máy cục bộ.')
    if production:
        names=('COGNITO_REGION','COGNITO_USER_POOL_ID','COGNITO_CLIENT_ID','COGNITO_DOMAIN','COGNITO_REDIRECT_URI','COGNITO_LOGOUT_URI','PORTAL_EXPORT_BUCKET')
        if not all(os.environ.get(name) for name in names):raise ConfigurationError('Thiếu cấu hình Cognito hoặc kho riêng tư cho production.')
        for name in ('COGNITO_DOMAIN','COGNITO_REDIRECT_URI','COGNITO_LOGOUT_URI'):
            url=urlsplit(os.environ[name])
            if url.scheme!='https' or not url.hostname or url.username or url.password:
                raise ConfigurationError('Cognito và URL ứng dụng production bắt buộc HTTPS.')
    if arn:
        value = read_secret(arn, client)
        try:
            host = os.environ['PORTAL_DATABASE_HOST']
            port = int(os.environ.get('PORTAL_DATABASE_PORT', '5432'))
            name = os.environ.get('PORTAL_DATABASE_NAME', 'campus')
            ca = os.environ['PORTAL_DATABASE_CA']
            if not Path(ca).is_file() or not 1 <= port <= 65535: raise ValueError()
            username, password = value['username'], value['password']
            if not all(isinstance(x,str) and x for x in (host,name,username,password)): raise ValueError()
            return f'postgresql://{quote(username,safe="")}:{quote(password,safe="")}@{host}:{port}/{quote(name,safe="")}?'+urlencode({'sslmode':'verify-full','sslrootcert':ca})
        except (KeyError, ValueError, TypeError):
            raise ConfigurationError('Thiếu host/cổng/tên DB, CA TLS hoặc thông tin người dùng DB hợp lệ.') from None
    return os.environ.get('PORTAL_DATABASE_URL') or os.environ.get('PORTAL_DB',str(Path(root)/'portal.sqlite3'))


def auto_migrate():
    return os.environ.get('PORTAL_ENV') != 'production' and os.environ.get('PORTAL_AUTO_MIGRATE','1') == '1'
