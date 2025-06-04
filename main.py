from astrbot.api.event import AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api import AstrBotConfig
from astrbot.core.star.filter.event_message_type import EventMessageType

from astrbot.api.event import filter
from astrbot.core import AstrBotConfig
from astrbot.core.platform import AstrMessageEvent
import astrbot.core.message.components as Comp
import re
from typing import List

from . import cfg

from .dbService import g_pDBService
from .json import g_pJsonManager
from .farm.farm import g_pFarmManager
from .database.database import g_pSqlManager
from .tool import g_pToolManager


@register("astrbot_plugin_farm", "真寻农场", "农场快乐时光", "1.0.0")
class CAstrbotPluginFarm(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        cfg.g_pConfigManager.sFarmDrawQuality = config.get("FarmDrawQuality", "low")
        cfg.g_pConfigManager.sFarmServerUrl = config.get(
            "FarmDrawQuality", "http://diuse.work"
        )
        cfg.g_pConfigManager.sFarmPrefix = config.get("FarmPrefix", "")

        self.commands = {"开通农场": self.registerFarm, "我的农场": self.myFarm}

    async def initialize(self):
        """可选择实现异步的插件初始化方法，当实例化该插件类之后会自动调用该方法。"""
        # 初始化数据库
        await g_pSqlManager.init()

        # 初始化读取Json
        await g_pJsonManager.init()

        await g_pDBService.init()

    @filter.event_message_type(EventMessageType.ALL)
    async def farmHandle(self, event: AstrMessageEvent):
        prefix = cfg.g_pConfigManager.sFarmPrefix

        # 前缀模式
        if prefix:
            chain = event.get_messages()
            if not chain:
                return
            first_seg = chain[0]
            # 前缀触发
            if isinstance(first_seg, Comp.Plain):
                if not first_seg.text.startswith(prefix):
                    return
            elif isinstance(first_seg, Comp.Reply) and len(chain) > 1:
                second_seg = chain[1]
                if isinstance(
                    second_seg, Comp.Plain
                ) and not second_seg.text.startswith(prefix):
                    return
            # @bot触发
            elif isinstance(first_seg, Comp.At):
                if str(first_seg.qq) != str(event.get_self_id()):
                    return
            else:
                return

        message = event.get_message_str().removeprefix(prefix)

        if not message:
            return

        pattern = r"(\S+)\s*(.*)"
        match = re.match(pattern, message)

        if match:
            cmd = match.group(1)
            args = match.group(2)

            # 解析参数，按空格分割
            params = re.split(r"\s+", args.strip())

            if cmd in self.commands:
                async for result in self.commands[cmd](event, params):
                    yield result

    async def registerFarm(self, event: AstrMessageEvent, params: List[str]):
        """开通农场"""
        if not event.is_at_or_wake_command:
            return

        uid = event.get_sender_id()
        name = event.get_sender_name()

        user = await g_pDBService.user.getUserInfoByUid(uid)

        if user:
            chain = [
                Comp.At(qq=uid),
                Comp.Plain("🎉 您已经开通农场啦~"),
            ]

            yield event.chain_result(chain)
            return

        try:
            safe_name = g_pToolManager.sanitize_username(name)

            # 初始化用户信息
            success = await g_pDBService.user.initUserInfoByUid(
                uid=uid, name=safe_name, exp=0, point=500
            )

            msg = (
                "✅ 农场开通成功！\n💼 初始资金：500农场币"
                if success
                else "⚠️ 开通失败，请稍后再试"
            )
            logger.info(f"用户注册 {'成功' if success else '失败'}：{uid}")
        except Exception as e:
            msg = "⚠️ 系统繁忙，请稍后再试"
            logger.error(f"注册异常 | UID:{uid} | 错误：{e}")

        chain = [
            Comp.At(qq=uid),
            Comp.Plain(f"{msg}"),
        ]

        yield event.chain_result(chain)

    async def myFarm(self, event: AstrMessageEvent, params: List[str]):
        uid = event.get_sender_id()

        exist = await g_pDBService.user.isUserExist(uid)
        if not exist:
            chain = [
                Comp.At(qq=uid),
                Comp.Plain("尚未开通农场，快at我发送 开通农场 开通吧"),
            ]

            yield event.chain_result(chain)
            return

        image = await g_pFarmManager.drawFarmByUid(uid)

        chain = [
            Comp.At(qq=uid),
            Comp.Image.fromBase64(image),
        ]

        yield event.chain_result(chain)

    async def terminate(self):
        """可选择实现异步的插件销毁方法，当插件被卸载/停用时会调用。"""
        await g_pSqlManager.cleanup()

        await g_pDBService.cleanup()
