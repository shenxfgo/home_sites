"""口令哈希。直接用 bcrypt，不经 passlib —— 后者自 2020 年起停更，且与 bcrypt>=4 有兼容告警。"""

import bcrypt

# bcrypt 只看口令的前 72 字节，超过会直接报错，所以在入口处就把它当成上限。
MAX_PASSWORD_BYTES = 72

BCRYPT_ROUNDS = 12


def hash_password(plain: str) -> str:
    """返回可直接入库的 bcrypt 哈希。"""
    salt = bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
    return bcrypt.hashpw(plain.encode("utf-8"), salt).decode("ascii")


def verify_password(plain: str, hashed: str) -> bool:
    """定长比较；哈希损坏或格式不认识时按“不匹配”处理，不抛给调用方。"""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("ascii"))
    except ValueError:
        return False


def password_too_long(plain: str) -> bool:
    """口令是否超出 bcrypt 的处理上限。"""
    return len(plain.encode("utf-8")) > MAX_PASSWORD_BYTES
