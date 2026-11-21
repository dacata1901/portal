"""Set a password for an existing local account, without exposing it in the UI."""
import argparse
import getpass
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend import db
from backend.accounts import AccountStore, password_hash


def set_password(target, user_id, password):
    if os.environ.get('PORTAL_DATABASE_URL') or os.environ.get('PORTAL_AUTH_MODE','demo').lower() != 'demo':
        raise ValueError('Công cụ này chỉ dành cho cơ sở dữ liệu SQLite cục bộ.')
    if not Path(target).is_file():
        raise ValueError('Không tìm thấy cơ sở dữ liệu cục bộ đã có.')
    if not 12 <= len(password) <= 128 or not password.strip():
        raise ValueError('Mật khẩu cần có 12–128 ký tự.')
    AccountStore(db, str(target)).migrate()
    conn = db.connect(str(target))
    try:
        conn.execute('BEGIN IMMEDIATE')
        user = conn.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()
        if not user:
            raise ValueError('Không tìm thấy tài khoản đã có. Công cụ này không tạo người dùng hoặc đổi quyền.')
        student_key = user['student_id'].upper() if user['student_id'] else '__account_' + user_id
        import time
        conn.execute('INSERT INTO account_credentials VALUES(?,?,?,?,?) '
                     'ON CONFLICT(user_id) DO UPDATE SET email_key=excluded.email_key,student_key=excluded.student_key,password_hash=excluded.password_hash',
                     (user_id,user['email'].lower(),student_key,password_hash(password),int(time.time())))
        conn.execute('DELETE FROM account_sessions WHERE user_id=?', (user_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def set_role_passwords(target, role, password):
    if os.environ.get('PORTAL_DATABASE_URL') or os.environ.get('PORTAL_AUTH_MODE','demo').lower() != 'demo':
        raise ValueError('Công cụ này chỉ dành cho cơ sở dữ liệu SQLite cục bộ.')
    if not Path(target).is_file():
        raise ValueError('Không tìm thấy cơ sở dữ liệu cục bộ đã có.')
    if not 12 <= len(password) <= 128 or not password.strip():
        raise ValueError('Mật khẩu cần có 12–128 ký tự.')
    AccountStore(db, str(target)).migrate()
    encoded = password_hash(password)
    conn = db.connect(str(target))
    try:
        conn.execute('BEGIN IMMEDIATE')
        users = conn.execute('SELECT * FROM users WHERE role=?', (role,)).fetchall()
        if not users:
            raise ValueError('Không tìm thấy tài khoản nào thuộc vai trò này.')
        import time
        now = int(time.time())
        for user in users:
            uid = user['id']
            student_key = user['student_id'].upper() if user['student_id'] else '__account_' + uid
            conn.execute('INSERT INTO account_credentials VALUES(?,?,?,?,?) '
                         'ON CONFLICT(user_id) DO UPDATE SET email_key=excluded.email_key,student_key=excluded.student_key,password_hash=excluded.password_hash',
                         (uid, user['email'].lower(), student_key, encoded, now))
            conn.execute('DELETE FROM account_sessions WHERE user_id=?', (uid,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Đặt mật khẩu cho tài khoản đã có trên máy.')
    parser.add_argument('user_id', nargs='?', help='Ví dụ: stu-10001, org-1 hoặc admin-1')
    parser.add_argument('--role', choices=['student', 'organizer', 'administrator'], help='Đặt mật khẩu hàng loạt cho toàn bộ tài khoản thuộc vai trò này.')
    parser.add_argument('--db', default=str(ROOT/'portal.sqlite3'))
    parser.add_argument('--password-env', help='Đọc mật khẩu từ biến môi trường (dùng cho bootstrap máy chủ, không in ra log).')
    args = parser.parse_args()
    try:
        if not args.user_id and not args.role:
            raise ValueError('Cần truyền user_id hoặc --role.')
        if args.password_env:
            password = os.environ.get(args.password_env, '')
        else:
            password = getpass.getpass('Mật khẩu mới: ')
            if password != getpass.getpass('Nhập lại mật khẩu: '):
                raise ValueError('Hai mật khẩu chưa khớp.')
        if args.role:
            set_role_passwords(args.db, args.role, password)
        else:
            set_password(args.db, args.user_id, password)
        print('Đã đặt mật khẩu. Đăng nhập qua form email/mật khẩu. Quyền tài khoản được giữ nguyên.')
    except (ValueError, db.DatabaseError) as error:
        print('Không đặt được mật khẩu. Kiểm tra mã tài khoản, cơ sở dữ liệu và điều kiện mật khẩu.', file=sys.stderr)
        sys.exit(1)
