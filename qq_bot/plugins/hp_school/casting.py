"""施放非战斗咒语。战斗咒语归决斗系统管，这里只处理有日常用途的那些。

荧光闪烁的作用在禁林探险里（降低遇险概率），是被动生效的，不需要主动施放，
所以不在这里出现——等禁林系统做出来后由那边直接查"学没学会"。
"""

from plugins.hp_core import spells as spell_catalog
from plugins.hp_core import storage as core_storage


class CastError(Exception):
    pass


CASTABLE = {"scourgify", "reparo"}


def cast(uid: str, spell_input: str) -> dict:
    player = core_storage.get_player(uid)
    if not player or not player["house"]:
        raise CastError("你还没有分院，先发「/入学」完成入学测试。")

    spell = spell_catalog.find(spell_input.strip())
    if not spell:
        raise CastError("没有这个咒语。")
    key, name, latin, subject, min_grade, category, desc = spell

    if not core_storage.has_spell(uid, key):
        raise CastError(f"你还没学会「{name}」，多上几节课。")

    if key not in CASTABLE:
        raise CastError(f"「{name}」不是这么用的。（能主动施放的：清理一新、修复如初）")

    if key == "scourgify":
        return _cast_scourgify(uid, name)
    return _cast_reparo(uid, name)


def _cast_scourgify(uid: str, name: str) -> dict:
    cleared = core_storage.clear_active_effects(uid)
    if not cleared:
        raise CastError("你身上很干净，没什么好清理的。")
    return {"spell": name, "cleared": cleared}


def _cast_reparo(uid: str, name: str) -> dict:
    from plugins.hp_events import quidditch  # 延迟导入，避免插件加载顺序问题

    try:
        result = quidditch.repair_broom(uid)
    except quidditch.QuidditchError as e:
        raise CastError(str(e)) from e
    return {"spell": name, **result}
