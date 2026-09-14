from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, MessageSegment
from nonebot.params import CommandArg

echo = on_command("echo", aliases={"复读"})


@echo.handle()
async def handle_echo(event: MessageEvent, args=CommandArg()):
    text = args.extract_plain_text().strip()
    if text:
        await echo.finish(text)


ping = on_command("在吗")


@ping.handle()
async def handle_ping(event: MessageEvent):
    await ping.finish(MessageSegment.text("频道D已接通。拿破仑·索罗在线——放心，一切照常。"))
