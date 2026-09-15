import re
import time

from nonebot import logger, on_command
from nonebot.adapters.qq import Bot, MessageEvent, MessageSegment
from nonebot.params import CommandArg

from plugins.changri_core import PLATFORM
from plugins.changri_core.api import (
    get_role_group,
    get_role_name,
    get_uid_by_role_name,
    is_admin,
    is_feature_enabled,
)

from . import api

CHUNK_CHAR_LIMIT = 3000


def _require_role(uid: str) -> str | None:
    return get_role_name(PLATFORM, uid)


def _pack_segments(segments: list[str], limit: int = CHUNK_CHAR_LIMIT) -> list[str]:
    """把若干段文本尽量塞满每条消息，单段内容本身不会被截断/拆散。"""
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for seg in segments:
        seg_len = len(seg)
        if current and current_len + seg_len > limit:
            chunks.append("\n\n".join(current))
            current, current_len = [], 0
        current.append(seg)
        current_len += seg_len
    if current:
        chunks.append("\n\n".join(current))
    return chunks


async def _send_markdown_chunks(bot: Bot, event: MessageEvent, header: str, segments: list[str]) -> None:
    chunks = _pack_segments(segments) or [""]
    total = len(chunks)
    for i, chunk in enumerate(chunks, start=1):
        title = header if total == 1 else f"{header}（{i}/{total}）"
        text = f"{title}\n\n{chunk}" if chunk else title
        await bot.send(event, MessageSegment.markdown(text))


async def _push_to_group(bot: Bot, to_uid: str, title: str, text: str) -> None:
    target_gid = get_role_group(PLATFORM, to_uid)
    if not target_gid:
        return
    try:
        await bot.send_to_group(group_openid=target_gid, message=MessageSegment.markdown(f"# {title}\n\n{text}"))
    except Exception as e:
        logger.warning(f"[社交] 推送到群失败：{e}")


# ── 论坛 ──────────────────────────────────────────────────────────────

post_forum_cmd = on_command("发帖")


@post_forum_cmd.handle()
async def handle_post_forum(event: MessageEvent, args=CommandArg()):
    if not is_feature_enabled("forum"):
        await post_forum_cmd.finish("论坛系统现在关闭中")
        return
    uid = event.get_user_id()
    role_name = _require_role(uid)
    if role_name is None:
        await post_forum_cmd.finish("✨ 你还不是本系统的会员，请先使用「/创建新角色」来认领你的身份吧。")
        return

    raw = args.extract_plain_text().strip()
    if not raw:
        await post_forum_cmd.finish("💡 请输入帖子内容！\n格式：/发帖 内容 或 /发帖 署名 内容")
        return
    tokens = raw.split()
    if len(tokens) > 1:
        author, content = tokens[0], raw.split(maxsplit=1)[1]
    else:
        author, content = role_name, raw

    ok, result = api.create_post(PLATFORM, uid, author, content)
    if not ok:
        await post_forum_cmd.finish(result)
        return
    await post_forum_cmd.finish(f"✅ 帖子 [{result}] 发布成功！")


reply_post_cmd = on_command("回复帖子")


@reply_post_cmd.handle()
async def handle_reply_post(bot: Bot, event: MessageEvent, args=CommandArg()):
    if not is_feature_enabled("forum"):
        await reply_post_cmd.finish("论坛系统现在关闭中")
        return
    uid = event.get_user_id()
    role_name = _require_role(uid)
    if role_name is None:
        await reply_post_cmd.finish("✨ 你还不是本系统的会员，请先使用「/创建新角色」来认领你的身份吧。")
        return

    raw = args.extract_plain_text().strip()
    tokens = raw.split()
    if len(tokens) < 2:
        await reply_post_cmd.finish(
            "❌ 格式错误！\n格式：/回复帖子 贴号 内容\n引用楼层：/回复帖子 贴号 引用N 内容（引用0=楼主）"
        )
        return

    post_id = tokens[0]
    quote_floor = None
    quote_match = re.fullmatch(r"引用(\d+)", tokens[1]) if len(tokens) >= 3 else None
    if quote_match:
        quote_floor = int(quote_match.group(1))
        author = role_name
        content = raw.split(maxsplit=2)[2]
    elif len(tokens) >= 3:
        author = tokens[1]
        content = raw.split(maxsplit=2)[2]
    else:
        author = role_name
        content = raw.split(maxsplit=1)[1]

    ok, msg = api.add_reply(PLATFORM, post_id, uid, author, content, quote_floor)
    if not ok:
        await reply_post_cmd.finish(msg)
        return
    await reply_post_cmd.finish(f"✅ 已回复到帖子 [{post_id}]")

    for name in api.extract_mentions(PLATFORM, content):
        if name == author:
            continue
        mentioned_uid = get_uid_by_role_name(PLATFORM, name)
        if mentioned_uid:
            await _push_to_group(
                bot, mentioned_uid, "📣 论坛提及",
                f"「{author}」在帖子 [{post_id}] 的回复中提到了你：\n{content}",
            )


def _vote_args(args=CommandArg()):
    text = args.extract_plain_text().strip().split()
    return (text[0], text[1]) if len(text) >= 2 else (None, None)


like_post_cmd = on_command("点赞")


@like_post_cmd.handle()
async def handle_like_post(event: MessageEvent, args=CommandArg()):
    if not is_feature_enabled("forum"):
        return
    if _require_role(event.get_user_id()) is None:
        await like_post_cmd.finish("✨ 你还不是本系统的会员，请先使用「/创建新角色」来认领你的身份吧。")
        return
    post_id, author = _vote_args(args)
    if not post_id or not author:
        await like_post_cmd.finish("格式：/点赞 帖号 署名")
        return
    if api.get_post_detail(PLATFORM, post_id) is None:
        return
    ok, msg, likes, dislikes = api.vote_post(post_id, author, True)
    await like_post_cmd.finish(f"{msg}\n🔥 赞：{likes} | ❄️ 踩：{dislikes}" if ok else msg)


dislike_post_cmd = on_command("点踩")


@dislike_post_cmd.handle()
async def handle_dislike_post(event: MessageEvent, args=CommandArg()):
    if not is_feature_enabled("forum"):
        return
    if _require_role(event.get_user_id()) is None:
        await dislike_post_cmd.finish("✨ 你还不是本系统的会员，请先使用「/创建新角色」来认领你的身份吧。")
        return
    post_id, author = _vote_args(args)
    if not post_id or not author:
        await dislike_post_cmd.finish("格式：/点踩 帖号 署名")
        return
    if api.get_post_detail(PLATFORM, post_id) is None:
        return
    ok, msg, likes, dislikes = api.vote_post(post_id, author, False)
    await dislike_post_cmd.finish(f"{msg}\n🔥 赞：{likes} | ❄️ 踩：{dislikes}" if ok else msg)


like_floor_cmd = on_command("点赞楼层")


@like_floor_cmd.handle()
async def handle_like_floor(event: MessageEvent, args=CommandArg()):
    if not is_feature_enabled("forum"):
        return
    role_name = _require_role(event.get_user_id())
    if role_name is None:
        await like_floor_cmd.finish("✨ 你还不是本系统的会员，请先使用「/创建新角色」来认领你的身份吧。")
        return
    tokens = args.extract_plain_text().strip().split()
    if len(tokens) < 2 or not tokens[1].isdigit():
        await like_floor_cmd.finish("格式：/点赞楼层 帖ID 楼层号 (署名)")
        return
    post_id, floor = tokens[0], int(tokens[1])
    author = tokens[2] if len(tokens) >= 3 else role_name
    reply = api.get_reply_by_floor(post_id, floor)
    if reply is None:
        await like_floor_cmd.finish(f"❌ 楼层 L{floor} 不存在")
        return
    ok, msg, likes, dislikes = api.vote_reply(reply["id"], author, True)
    await like_floor_cmd.finish(f"✅ 对 L{floor} 点赞成功！👍 {likes} | 👎 {dislikes}" if ok else msg)


dislike_floor_cmd = on_command("点踩楼层")


@dislike_floor_cmd.handle()
async def handle_dislike_floor(event: MessageEvent, args=CommandArg()):
    if not is_feature_enabled("forum"):
        return
    role_name = _require_role(event.get_user_id())
    if role_name is None:
        await dislike_floor_cmd.finish("✨ 你还不是本系统的会员，请先使用「/创建新角色」来认领你的身份吧。")
        return
    tokens = args.extract_plain_text().strip().split()
    if len(tokens) < 2 or not tokens[1].isdigit():
        await dislike_floor_cmd.finish("格式：/点踩楼层 帖ID 楼层号 (署名)")
        return
    post_id, floor = tokens[0], int(tokens[1])
    author = tokens[2] if len(tokens) >= 3 else role_name
    reply = api.get_reply_by_floor(post_id, floor)
    if reply is None:
        await dislike_floor_cmd.finish(f"❌ 楼层 L{floor} 不存在")
        return
    ok, msg, likes, dislikes = api.vote_reply(reply["id"], author, False)
    await dislike_floor_cmd.finish(f"✅ 对 L{floor} 点踩成功！👍 {likes} | 👎 {dislikes}" if ok else msg)


view_posts_cmd = on_command("查看帖子")


@view_posts_cmd.handle()
async def handle_view_posts(bot: Bot, event: MessageEvent, args=CommandArg()):
    if not is_feature_enabled("forum"):
        await view_posts_cmd.finish("论坛系统现在关闭中")
        return
    if _require_role(event.get_user_id()) is None:
        await view_posts_cmd.finish("✨ 你还不是本系统的会员，请先使用「/创建新角色」来认领你的身份吧。")
        return

    post_id = args.extract_plain_text().strip()
    if post_id:
        post = api.get_post_detail(PLATFORM, post_id)
        if post is None:
            await view_posts_cmd.finish(f"❌ 找不到帖子 [{post_id}]")
            return
        op_lines = [f"**{post['author_name']}**（楼主）", post["content"], f"👍 {post['likes']} | 👎 {post['dislikes']}"]
        segments = ["\n".join(op_lines)]
        for i, r in enumerate(post["replies"], start=1):
            block = [f"**{r['author_name']}**（L{i}）"]
            if r.get("quote_floor") is not None:
                floor_label = "楼主" if r["quote_floor"] == 0 else f"L{r['quote_floor']}"
                block.append(f"> 引用 {floor_label}：{r['quote_content']}")
            block.append(r["content"])
            if r["likes"] or r["dislikes"]:
                block.append(f"👍 {r['likes']} | 👎 {r['dislikes']}")
            segments.append("\n".join(block))
        await _send_markdown_chunks(bot, event, f"# 📜 帖子 [{post['id']}]", segments)
        return

    posts = api.list_hot_posts(PLATFORM, limit=10)
    if not posts:
        await view_posts_cmd.finish("📭 论坛空空如也")
        return
    lines = ["# 🔥 论坛热榜", ""]
    for p in posts:
        preview = p["content"][:30] + ("…" if len(p["content"]) > 30 else "")
        lines.append(f"**[{p['id']}]** {p['author_name']}：{preview}")
        lines.append(f"💬 {p['reply_count']} | 👍 {p['likes']}")
        lines.append("")
    await view_posts_cmd.finish(MessageSegment.markdown("\n".join(lines)))


delete_post_cmd = on_command("删除帖子")


@delete_post_cmd.handle()
async def handle_delete_post(event: MessageEvent, args=CommandArg()):
    if not is_admin(PLATFORM, event.get_user_id()):
        await delete_post_cmd.finish("❌ 权限不足，仅管理员可用。")
        return
    post_id = args.extract_plain_text().strip()
    if not post_id:
        await delete_post_cmd.finish("用法：/删除帖子 贴号")
        return
    if api.delete_post(PLATFORM, post_id):
        await delete_post_cmd.finish(f"🗑️ 帖子 [{post_id}] 已成功下架。")
    else:
        await delete_post_cmd.finish("❌ 找不到该帖子或已被删除。")


# ── 关系线 ──────────────────────────────────────────────────────────────

add_rel_detail_cmd = on_command("拉线")


@add_rel_detail_cmd.handle()
async def handle_add_rel_detail(bot: Bot, event: MessageEvent, args=CommandArg()):
    if not is_feature_enabled("relationship"):
        await add_rel_detail_cmd.finish("❌ 关系线系统已关闭")
        return
    uid = event.get_user_id()
    role_name = _require_role(uid)
    if role_name is None:
        await add_rel_detail_cmd.finish("请先绑定角色")
        return
    raw = args.extract_plain_text().strip()
    tokens = raw.split()
    if len(tokens) < 2:
        await add_rel_detail_cmd.finish("格式：/拉线 对方名 内容")
        return
    to_name = tokens[0]
    content = raw.split(maxsplit=1)[1]

    ok, msg = api.add_relationship_detail(PLATFORM, uid, role_name, to_name, content)
    await add_rel_detail_cmd.finish(msg)
    if ok:
        to_uid = get_uid_by_role_name(PLATFORM, to_name)
        if to_uid:
            await _push_to_group(
                bot, to_uid, "🔗 关系线更新", f"「{role_name}」拉了一条新的关系细节：\n{content}"
            )


confirm_relationship_cmd = on_command("确认关系线")


@confirm_relationship_cmd.handle()
async def handle_confirm_relationship(bot: Bot, event: MessageEvent, args=CommandArg()):
    if not is_feature_enabled("relationship"):
        await confirm_relationship_cmd.finish("❌ 关系线系统已关闭")
        return
    uid = event.get_user_id()
    role_name = _require_role(uid)
    if role_name is None:
        await confirm_relationship_cmd.finish("请先绑定角色")
        return
    to_name = args.extract_plain_text().strip()
    if not to_name:
        await confirm_relationship_cmd.finish("用法：/确认关系线 对方角色名")
        return
    ok, msg = api.confirm_relationship(PLATFORM, uid, role_name, to_name)
    await confirm_relationship_cmd.finish(msg)
    if ok:
        to_uid = get_uid_by_role_name(PLATFORM, to_name)
        if to_uid:
            await _push_to_group(bot, to_uid, "🤝 关系线确认", f"「{role_name}」已确认并完成了你们的关系线！")


set_forced_rel_cmd = on_command("设置强制关系线")


@set_forced_rel_cmd.handle()
async def handle_set_forced_rel(event: MessageEvent, args=CommandArg()):
    if not is_admin(PLATFORM, event.get_user_id()):
        await set_forced_rel_cmd.finish("❌ 权限不足，仅管理员可用。")
        return
    raw = args.extract_plain_text().strip()
    tokens = raw.split()
    if len(tokens) < 3:
        await set_forced_rel_cmd.finish("格式：/设置强制关系线 角色A 角色B 描述内容")
        return
    name_a, name_b = tokens[0], tokens[1]
    content = raw.split(maxsplit=2)[2]
    ok, msg = api.set_forced_relationship(PLATFORM, name_a, name_b, content)
    await set_forced_rel_cmd.finish(msg)


del_rel_cmd = on_command("删除关系线")


@del_rel_cmd.handle()
async def handle_del_rel(event: MessageEvent, args=CommandArg()):
    if not is_admin(PLATFORM, event.get_user_id()):
        await del_rel_cmd.finish("❌ 权限不足，仅管理员可用。")
        return
    tokens = args.extract_plain_text().strip().split()
    if len(tokens) < 2:
        await del_rel_cmd.finish("格式：/删除关系线 角色A 角色B")
        return
    ok, msg = api.delete_relationship(PLATFORM, tokens[0], tokens[1])
    await del_rel_cmd.finish(msg)


clear_rel_cmd = on_command("清空关系线")


@clear_rel_cmd.handle()
async def handle_clear_rel(event: MessageEvent, args=CommandArg()):
    if not is_admin(PLATFORM, event.get_user_id()):
        await clear_rel_cmd.finish("❌ 权限不足，仅管理员可用。")
        return
    code = args.extract_plain_text().strip()
    expected = time.strftime("%m%d")
    if code != expected:
        await clear_rel_cmd.finish(f"⚠️ 危险操作！输入确认码：{expected}\n用法：/清空关系线 {expected}")
        return
    api.clear_relationships(PLATFORM)
    await clear_rel_cmd.finish("🔥 已清空当前平台所有关系线")


withdraw_relation_cmd = on_command("撤回关系")


@withdraw_relation_cmd.handle()
async def handle_withdraw_relation(bot: Bot, event: MessageEvent, args=CommandArg()):
    if not is_feature_enabled("relationship"):
        await withdraw_relation_cmd.finish("❌ 关系线系统已关闭")
        return
    uid = event.get_user_id()
    role_name = _require_role(uid)
    if role_name is None:
        await withdraw_relation_cmd.finish("请先绑定角色")
        return
    raw = args.extract_plain_text().strip()
    tokens = raw.split()
    if len(tokens) < 2:
        await withdraw_relation_cmd.finish("格式：/撤回关系 对方角色名 要撤回的内容")
        return
    to_name = tokens[0]
    content = raw.split(maxsplit=1)[1]
    ok, msg = api.withdraw_relationship_detail(PLATFORM, uid, role_name, to_name, content)
    await withdraw_relation_cmd.finish(msg)
    if ok:
        to_uid = get_uid_by_role_name(PLATFORM, to_name)
        if to_uid:
            await _push_to_group(bot, to_uid, "🗑️ 关系线撤回", f"「{role_name}」撤回了一条发给你的关系细节：\n{content}")


view_relationship_cmd = on_command("查看关系线")


@view_relationship_cmd.handle()
async def handle_view_relationship(bot: Bot, event: MessageEvent, args=CommandArg()):
    if not is_feature_enabled("relationship"):
        await view_relationship_cmd.finish("❌ 关系线系统已关闭")
        return
    uid = event.get_user_id()
    role_name = _require_role(uid)
    if role_name is None:
        await view_relationship_cmd.finish("请先绑定角色")
        return

    to_name = args.extract_plain_text().strip()
    if to_name:
        rel = api.get_relationship_with(PLATFORM, uid, to_name)
        if rel is None:
            await view_relationship_cmd.finish(f"你与「{to_name}」之间暂无关系记录。")
            return
        if not rel["details"]:
            await view_relationship_cmd.finish(f"你与「{to_name}」虽有关系线，但尚未添加任何细节。")
            return
        segments = [f"**{d['from_name']}**：{d['content']}" for d in rel["details"]]
        await _send_markdown_chunks(bot, event, f"# 📜 你与「{to_name}」的关系细节", segments)
        return

    config = api.get_config()
    my_rels = api.list_my_relationships(PLATFORM, uid)
    lines = [f"📚 「{role_name}」的关系线列表："]
    active_count = 0
    for r in my_rels:
        if not r["is_system"] and r["is_initiator"]:
            active_count += 1
        status_icon = "✅" if r["line"]["confirmed"] else "⏳"
        type_tag = "【强制】" if r["is_system"] else ("【发起】" if r["is_initiator"] else "【收到】")
        lines.append(f"{status_icon} {type_tag} 与「{r['other_name']}」（{r['detail_count']}条 | {r['total_chars']}字）")
    if len(lines) == 1:
        lines.append("（暂无任何记录）")
    else:
        lines.append(f"\n📊 额度占用：{active_count}/{config['max_relationships_per_user']}")
        lines.append("💡 输入「/查看关系线 名字」查看完整细节")
    await view_relationship_cmd.finish("\n".join(lines))


rel_stats_cmd = on_command("关系线统计")


@rel_stats_cmd.handle()
async def handle_rel_stats(event: MessageEvent):
    if not is_admin(PLATFORM, event.get_user_id()):
        await rel_stats_cmd.finish("❌ 权限不足，仅管理员可用。")
        return
    stats = api.get_relationship_stats(PLATFORM)
    if not stats:
        await rel_stats_cmd.finish("📭 当前平台没有任何关系线记录")
        return
    lines = [f"# 📊 角色关系线统计", "", f"共 {len(stats)} 个角色拥有关系线", ""]
    for i, s in enumerate(stats, start=1):
        lines.append(f"{i}. {s['role']}：{s['count']} 条关系线")
    await rel_stats_cmd.finish(MessageSegment.markdown("\n".join(lines)))


# ── 设置 ──────────────────────────────────────────────────────────────

SOCIAL_CONFIG_KEYS = {
    "论坛字数上限": "forum_max_length",
    "拉线单条字数上限": "max_detail_chars",
    "发起额度上限": "max_relationships_per_user",
    "拉线段数上限": "max_detail_count",
    "拉线总字数上限": "max_rel_total_chars",
}

social_settings_cmd = on_command("社交设置")


@social_settings_cmd.handle()
async def handle_social_settings(event: MessageEvent, args=CommandArg()):
    if not is_admin(PLATFORM, event.get_user_id()):
        await social_settings_cmd.finish("权限不足，仅管理员可用")
        return
    text = args.extract_plain_text().strip()
    if not text:
        config = api.get_config()
        lines = ["⚙️ 社交系统设置"]
        for label, key in SOCIAL_CONFIG_KEYS.items():
            lines.append(f"- {label}（{key}）：{config[key]}")
        lines.append("\n用法：/社交设置 " + "/".join(SOCIAL_CONFIG_KEYS.keys()) + " 数值")
        await social_settings_cmd.finish("\n".join(lines))
        return
    parts = text.split()
    if len(parts) != 2 or parts[0] not in SOCIAL_CONFIG_KEYS or not parts[1].isdigit():
        await social_settings_cmd.finish("用法：/社交设置 " + "/".join(SOCIAL_CONFIG_KEYS.keys()) + " 数值")
        return
    api.set_config(**{SOCIAL_CONFIG_KEYS[parts[0]]: int(parts[1])})
    await social_settings_cmd.finish(f"{parts[0]} 已设为 {parts[1]}")
