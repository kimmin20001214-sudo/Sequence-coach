"""팀장용 계정 관리. backend 폴더에서 실행해요.

  python -m app.manage add student01            (비밀번호는 실행 중에 물어봐요)
  python -m app.manage add leader --admin
  python -m app.manage password student01
  python -m app.manage disable student01        (로그인 막기)
  python -m app.manage enable student01
  python -m app.manage list
"""
import argparse
import getpass
import re
import sys

from . import auth, db


def _ask_password() -> str:
    pw = getpass.getpass("비밀번호: ")
    if len(pw) < auth.MIN_PASSWORD:
        sys.exit(f"비밀번호는 {auth.MIN_PASSWORD}자 이상이어야 해요.")
    if pw != getpass.getpass("비밀번호 한 번 더: "):
        sys.exit("두 비밀번호가 달라요.")
    return pw


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="python -m app.manage", description="계정 관리")
    sub = p.add_subparsers(dest="cmd", required=True)
    add = sub.add_parser("add", help="계정 만들기")
    add.add_argument("username")
    add.add_argument("--admin", action="store_true", help="팀장 계정")
    for name in ("password", "disable", "enable"):
        sub.add_parser(name).add_argument("username")
    sub.add_parser("list", help="계정 목록")
    a = p.parse_args(argv)

    if a.cmd == "list":
        for u in db.list_users():
            print(f"{u['username']}\t{u['role']}\t{'막힘' if u['disabled'] else '사용 중'}")
        return
    name = a.username.strip().lower()
    if a.cmd == "add":
        if not re.fullmatch(r"[a-z0-9_.-]{3,40}", name):
            sys.exit("아이디는 영문 소문자·숫자·_ . - 로 3~40자여야 해요.")
        ok = db.create_user(name, auth.hash_password(_ask_password()), "admin" if a.admin else "student")
        if not ok:
            sys.exit("이미 있는 아이디예요.")
        print(f"{name} 계정을 만들었어요.")
    elif a.cmd == "password":
        if not db.get_user(name):
            sys.exit("없는 아이디예요.")
        db.set_password(name, auth.hash_password(_ask_password()))
        print("비밀번호를 바꿨어요. 이 계정의 로그인 상태는 모두 풀려요.")
    else:
        if not db.set_disabled(name, a.cmd == "disable"):
            sys.exit("없는 아이디예요.")
        print("로그인을 막았어요." if a.cmd == "disable" else "다시 쓸 수 있어요.")


if __name__ == "__main__":
    main()
