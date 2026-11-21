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


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Đặt mật khẩu cho tài khoản đã có trên máy.')
    parser.add_argument('user_id', help='Ví dụ: org-1 hoặc admin-1')
    parser.add_argument('--db', default=str(ROOT/'portal.sqlite3'))
    args = parser.parse_args()
    try:
        password = getpass.getpass('Mật khẩu mới: ')
        if password != getpass.getpass('Nhập lại mật khẩu: '):
            raise ValueError('Hai mật khẩu chưa khớp.')
        set_password(args.db, args.user_id, password)
        print('Đã đặt mật khẩu. Đăng nhập qua form email/mật khẩu. Quyền tài khoản được giữ nguyên.')
    except (ValueError, db.DatabaseError) as error:
        print('Không đặt được mật khẩu. Kiểm tra mã tài khoản, cơ sở dữ liệu và điều kiện mật khẩu.', file=sys.stderr)
        sys.exit(1)
