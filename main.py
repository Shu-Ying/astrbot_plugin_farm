from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api import AstrBotConfig

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

    async def initialize(self):
        """可选择实现异步的插件初始化方法，当实例化该插件类之后会自动调用该方法。"""
        # 初始化数据库
        await g_pSqlManager.init()

        # 初始化读取Json
        await g_pJsonManager.init()

        await g_pDBService.init()

    @filter.command("开通农场")
    async def _(self, event: AstrMessageEvent):
        if not event.is_at_or_wake_command:
            return

        uid = event.get_sender_id()
        name = event.get_sender_name()

        user = await g_pDBService.user.getUserInfoByUid(uid)

        if user:
            await event.plain_result("🎉 您已经开通农场啦~")
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

        yield event.plain_result(f"{msg}")

    @filter.command("我的农场")
    async def _(self, event: AstrMessageEvent):
        uid = event.get_sender_id()

        if not await g_pToolManager.isRegisteredByUid(uid):
            return

        image = await g_pFarmManager.drawFarmByUid(uid)
        yield event.make_result().file_image(image)

    # @filter.command("农场详述")
    # async def _(self, event: AstrMessageEvent):
    #     uid = event.get_sender_id()

    #     if not await g_pToolManager.isRegisteredByUid(uid):
    #         return

    #     info = await g_pFarmManager.drawDetailFarmByUid(uid)

    #     image = await g_pFarmManager.drawFarmByUid(uid)
    #     yield event.make_result().file_image(image)

    @filter.command("我的农场币")
    async def _(self, event: AstrMessageEvent):
        uid = event.get_sender_id()
        point = await g_pDBService.user.getUserPointByUid(uid)

        if point < 0:
            yield event.plain_result("尚未开通农场，快at我发送 开通农场 开通吧")

            return False

        yield event.plain_result(f"你的当前农场币为: {point}")

    @filter.command("种子商店")
    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def _(self, event: AstrMessageEvent):
        uid = event.get_sender_id()

        if not await g_pToolManager.isRegisteredByUid(uid):
            return

        image = await g_pFarmManager.drawFarmByUid(uid)
        self.da

        yield event.make_result().file_image(image)

    @filter.command("我的农场")
    async def _(self, event: AstrMessageEvent):
        uid = event.get_sender_id()

        if not await g_pToolManager.isRegisteredByUid(uid):
            return

        image = await g_pFarmManager.drawFarmByUid(uid)
        yield event.make_result().file_image(image)

    @filter.command("我的农场")
    async def _(self, event: AstrMessageEvent):
        uid = event.get_sender_id()

        if not await g_pToolManager.isRegisteredByUid(uid):
            return

        image = await g_pFarmManager.drawFarmByUid(uid)
        yield event.make_result().file_image(image)

    @filter.command("我的农场")
    async def _(self, event: AstrMessageEvent):
        uid = event.get_sender_id()

        if not await g_pToolManager.isRegisteredByUid(uid):
            return

        image = await g_pFarmManager.drawFarmByUid(uid)
        yield event.make_result().file_image(image)

    @filter.command("我的农场")
    async def _(self, event: AstrMessageEvent):
        uid = event.get_sender_id()

        if not await g_pToolManager.isRegisteredByUid(uid):
            return

        image = await g_pFarmManager.drawFarmByUid(uid)
        yield event.make_result().file_image(image)

    @filter.command("我的农场")
    async def _(self, event: AstrMessageEvent):
        uid = event.get_sender_id()

        if not await g_pToolManager.isRegisteredByUid(uid):
            return

        image = await g_pFarmManager.drawFarmByUid(uid)
        yield event.make_result().file_image(image)

    @filter.command("我的农场")
    async def _(self, event: AstrMessageEvent):
        uid = event.get_sender_id()

        if not await g_pToolManager.isRegisteredByUid(uid):
            return

        image = await g_pFarmManager.drawFarmByUid(uid)
        yield event.make_result().file_image(image)

    @filter.command("我的农场")
    async def _(self, event: AstrMessageEvent):
        uid = event.get_sender_id()

        if not await g_pToolManager.isRegisteredByUid(uid):
            return

        image = await g_pFarmManager.drawFarmByUid(uid)
        yield event.make_result().file_image(image)

    @filter.command("我的农场")
    async def _(self, event: AstrMessageEvent):
        uid = event.get_sender_id()

        if not await g_pToolManager.isRegisteredByUid(uid):
            return

        image = await g_pFarmManager.drawFarmByUid(uid)
        yield event.make_result().file_image(image)

    @filter.command("我的农场")
    async def _(self, event: AstrMessageEvent):
        uid = event.get_sender_id()

        if not await g_pToolManager.isRegisteredByUid(uid):
            return

        image = await g_pFarmManager.drawFarmByUid(uid)
        yield event.make_result().file_image(image)

    @filter.command("我的农场")
    async def _(self, event: AstrMessageEvent):
        uid = event.get_sender_id()

        if not await g_pToolManager.isRegisteredByUid(uid):
            return

        image = await g_pFarmManager.drawFarmByUid(uid)
        yield event.make_result().file_image(image)

    @filter.command("我的农场")
    async def _(self, event: AstrMessageEvent):
        uid = event.get_sender_id()

        if not await g_pToolManager.isRegisteredByUid(uid):
            return

        image = await g_pFarmManager.drawFarmByUid(uid)
        yield event.make_result().file_image(image)

    @filter.command("我的农场")
    async def _(self, event: AstrMessageEvent):
        uid = event.get_sender_id()

        if not await g_pToolManager.isRegisteredByUid(uid):
            return

        image = await g_pFarmManager.drawFarmByUid(uid)
        yield event.make_result().file_image(image)

    @filter.command("我的农场")
    async def _(self, event: AstrMessageEvent):
        uid = event.get_sender_id()

        if not await g_pToolManager.isRegisteredByUid(uid):
            return

        image = await g_pFarmManager.drawFarmByUid(uid)
        yield event.make_result().file_image(image)

    @filter.command("我的农场")
    async def _(self, event: AstrMessageEvent):
        uid = event.get_sender_id()

        if not await g_pToolManager.isRegisteredByUid(uid):
            return

        image = await g_pFarmManager.drawFarmByUid(uid)
        yield event.make_result().file_image(image)

    @filter.command("我的农场")
    async def _(self, event: AstrMessageEvent):
        uid = event.get_sender_id()

        if not await g_pToolManager.isRegisteredByUid(uid):
            return

        image = await g_pFarmManager.drawFarmByUid(uid)
        yield event.make_result().file_image(image)

    @filter.command("我的农场")
    async def _(self, event: AstrMessageEvent):
        uid = event.get_sender_id()

        if not await g_pToolManager.isRegisteredByUid(uid):
            return

        image = await g_pFarmManager.drawFarmByUid(uid)
        yield event.make_result().file_image(image)

    async def terminate(self):
        """可选择实现异步的插件销毁方法，当插件被卸载/停用时会调用。"""
        await g_pSqlManager.cleanup()

        await g_pDBService.cleanup()
