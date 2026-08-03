from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, MessageSegment
from nonebot.params import CommandArg

echo = on_command("echo", aliases={"复读"})


@echo.handle()
async def handle_echo(event: MessageEvent, args=CommandArg()):
    text = args.extract_plain_text().strip()
    if text:
        await echo.finish(text)


ping = on_command("ping")


@ping.handle()
async def handle_ping(event: MessageEvent):
    await ping.finish(MessageSegment.text("pong"))
