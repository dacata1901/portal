"""Bounded email and CSRF validation for the basic local account flow."""
import hmac
import re


def normalize_email(value):
    if not isinstance(value, str):
        raise ValueError('Địa chỉ email không hợp lệ.')
    value = value.strip().lower()
    if len(value) > 254 or value.count('@') != 1:
        raise ValueError('Địa chỉ email không hợp lệ.')
    local, domain = value.split('@')
    if not 1 <= len(local) <= 64 or not re.fullmatch(r"[a-z0-9!#$%&'*+/=?^_`{|}~.-]+", local) or local.startswith('.') or local.endswith('.') or '..' in local:
        raise ValueError('Địa chỉ email không hợp lệ.')
    labels = domain.split('.')
    if len(labels) < 2 or not re.fullmatch(r'[a-z]{2,63}', labels[-1]):
        raise ValueError('Địa chỉ email không hợp lệ.')
    if any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label) for label in labels):
        raise ValueError('Địa chỉ email không hợp lệ.')
    return value


def valid_csrf(expected, supplied):
    return isinstance(supplied, str) and bool(re.fullmatch(r'[A-Za-z0-9_-]{20,128}', supplied)) and hmac.compare_digest(expected, supplied)
