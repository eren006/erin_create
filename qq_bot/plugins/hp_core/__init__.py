from . import storage

storage.init_db()

PLATFORM = "qq"


class UnknownPlayerError(Exception):
    pass


def resolve(name: str) -> str:
    """把玩家名字解析成uid。所有面向玩家的指令都用名字，不用QQ号。"""
    uid = storage.get_uid_by_name(name.strip())
    if uid is None:
        raise UnknownPlayerError(f"学校里没有叫「{name.strip()}」的人，名字要打全。")
    return uid
