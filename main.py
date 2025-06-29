import asyncio
import inspect
import re
from typing import List

import astrbot.core.message.components as Comp
from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import Image, Node
from astrbot.api.star import Context, Star, register
from astrbot.core import AstrBotConfig
from astrbot.core.platform import AstrMessageEvent
from astrbot.core.star.filter.event_message_type import EventMessageType
from astrbot.core.utils.session_waiter import (
    SessionController,
    session_waiter,
)

from . import cfg
from .database.database import g_pSqlManager
from .dbService import g_pDBService
from .farm.farm import g_pFarmManager
from .farm.shop import g_pShopManager
from .json import g_pJsonManager
from .request import g_pRequestManager
from .tool import g_pToolManager


@register("astrbot_plugin_farm", "真寻农场", "农场快乐时光", "1.5.0")
class CAstrbotPluginFarm(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        cfg.g_pConfigManager.sFarmDrawQuality = config.get("FarmDrawQuality", "low")
        cfg.g_pConfigManager.sFarmServerUrl = config.get(
            "FarmServerUrl", "http://diuse.work"
        )
        cfg.g_pConfigManager.sFarmPrefix = config.get("FarmPrefix", "")

        self.commands = {
            "开通农场": self.registerFarm,
            "我的农场": self.myFarm,
            "农场详述": self.detail,
            "我的农场币": self.myPoint,
            "种子商店": self.seedShop,
            "购买种子": self.buySeed,
            "我的种子": self.mySeed,
            "播种": self.sowing,
            "收获": self.harvest,
            "铲除": self.eradicate,
            "我的作物": self.myPlant,
            "开垦": self.reclamation,
            "出售作物": self.sellPlant,
            "偷菜": self.stealing,
            "更改农场名": self.changeName,
            "农场签到": self.signIn,
            "农场下阶段": self.god,
            "土地升级": self.soilUpgrade,
        }

    async def initialize(self):
        """可选择实现异步的插件初始化方法，当实例化该插件类之后会自动调用该方法。"""
        # 初始化数据库
        await g_pSqlManager.init()

        # 初始化读取Json
        await g_pJsonManager.init()

        await g_pDBService.init()

        # 检查作物文件是否缺失 or 更新
        await g_pRequestManager.initPlantDBFile()

    @filter.event_message_type(EventMessageType.ALL)
    async def farmHandle(self, event: AstrMessageEvent):
        prefix = cfg.g_pConfigManager.sFarmPrefix

        # 前缀模式
        if prefix:
            chain = event.get_messages()
            if not chain:
                return

            first = chain[0]
            # 前缀触发
            if isinstance(first, Comp.Plain):
                if not first.text.startswith(prefix):
                    return
            elif isinstance(first, Comp.Reply) and len(chain) > 1:
                second_seg = chain[1]
                if isinstance(
                    second_seg, Comp.Plain
                ) and not second_seg.text.startswith(prefix):
                    return
            # @bot触发
            elif isinstance(first, Comp.At):
                if str(first.qq) != str(event.get_self_id()):
                    return
            else:
                return

        message = event.get_message_str().removeprefix(prefix)

        if not message:
            return

        pattern = r"(\S+)\s*(.*)"
        match = re.match(pattern, message)

        if not match:
            return

        cmd = match.group(1)
        args = match.group(2)

        # 解析参数，按空格分割
        if args:
            params = re.split(r"\s+", args)
        else:
            params = []

        if cmd not in self.commands:
            return

        cmdFunc = self.commands[cmd]

        if inspect.isasyncgenfunction(cmdFunc):
            agen = cmdFunc(event, params)
            try:
                async for piece in agen:
                    yield piece
            except StopAsyncIteration as stop:
                value = stop.value

                if value is not None:
                    yield Comp.Plain(f"执行完毕，返回：{value}")
        elif asyncio.iscoroutinefunction(cmdFunc):
            await cmdFunc(event, params)
        else:
            try:
                cmdFunc(event, params)
            except Exception as e:
                logger.exception(f"执行命令 {cmd} 时出错：{e}")

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
                Comp.Plain(cfg.g_pConfigManager.sTranslation["register"]["repeat"]),
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
                cfg.g_pConfigManager.sTranslation["register"]["success"].format(
                    point=500
                )
                if success
                else cfg.g_pConfigManager.sTranslation["register"]["error"]
            )
            logger.info(f"用户注册 {'成功' if success else '失败'}：{uid}")
        except Exception as e:
            msg = cfg.g_pConfigManager.sTranslation["register"]["error"]
            logger.error(f"注册异常 | UID:{uid} | 错误：{e}")

        chain = [
            Comp.At(qq=uid),
            Comp.Plain(f"{msg}"),
        ]

        yield event.chain_result(chain)

    async def myFarm(self, event: AstrMessageEvent, params: List[str]):
        """我的农场"""
        uid = event.get_sender_id()

        exist = await g_pDBService.user.isUserExist(uid)
        if not exist:
            chain = [
                Comp.At(qq=uid),
                Comp.Plain(cfg.g_pConfigManager.sTranslation["basic"]["notFarm"]),
            ]

            yield event.chain_result(chain)
            return

        image = await g_pFarmManager.drawFarmByUid(uid)

        chain = [
            Comp.At(qq=uid),
            Comp.Image.fromBase64(image),
        ]

        yield event.chain_result(chain)

    async def detail(self, event: AstrMessageEvent, params: List[str]):
        """农场详述"""
        uid = event.get_sender_id()

        exist = await g_pDBService.user.isUserExist(uid)
        if not exist:
            chain = [
                Comp.At(qq=uid),
                Comp.Plain(cfg.g_pConfigManager.sTranslation["basic"]["notFarm"]),
            ]

            yield event.chain_result(chain)
            return

        images = await g_pFarmManager.drawDetailFarmByUid(uid)

        node = Node(
            uin=event.message_obj.self_id,
            content=[Image.fromBase64(img) for img in images],
        )
        yield event.chain_result([node])

    async def myPoint(self, event: AstrMessageEvent, params: List[str]):
        """农场币"""
        uid = event.get_sender_id()
        point = await g_pDBService.user.getUserPointByUid(uid)

        if point < 0:
            chain = [
                Comp.At(qq=uid),
                Comp.Plain(cfg.g_pConfigManager.sTranslation["basic"]["notFarm"]),
            ]

            yield event.chain_result(chain)
            return

        chain = [
            Comp.At(qq=uid),
            Comp.Plain(f"你的当前农场币为: {point}"),
        ]

        yield event.chain_result(chain)

    async def seedShop(self, event: AstrMessageEvent, params: List[str]):
        """种子商店"""
        uid = event.get_sender_id()

        exist = await g_pDBService.user.isUserExist(uid)
        if not exist:
            chain = [
                Comp.At(qq=uid),
                Comp.Plain(cfg.g_pConfigManager.sTranslation["basic"]["notFarm"]),
            ]

            yield event.chain_result(chain)
            return

        filterKey: str | int | None = None
        page: int = 1

        if len(params) >= 1 and params[0] is not None:
            first = params[0]
            if isinstance(first, str) and first.isdigit():
                page = int(first)
            else:
                filterKey = first

        if (
            len(params) >= 2
            and params[1] is not None
            and isinstance(params[1], str)
            and params[1].isdigit()
        ):
            page = int(params[1])

        if filterKey is None:
            image = await g_pShopManager.getSeedShopImage(page)
        else:
            image = await g_pShopManager.getSeedShopImage(filterKey, page)

        chain = [
            Comp.At(qq=uid),
            Comp.Image.fromBase64(image),
        ]

        yield event.chain_result(chain)

    async def buySeed(self, event: AstrMessageEvent, params: List[str]):
        """购买种子"""
        uid = event.get_sender_id()

        if not params:
            chain = [
                Comp.At(qq=uid),
                Comp.Plain(cfg.g_pConfigManager.sTranslation["buySeed"]["notSeed"]),
            ]

            yield event.chain_result(chain)
            return

        exist = await g_pDBService.user.isUserExist(uid)
        if not exist:
            chain = [
                Comp.At(qq=uid),
                Comp.Plain(cfg.g_pConfigManager.sTranslation["basic"]["notFarm"]),
            ]

            yield event.chain_result(chain)
            return

        seedName = params[0]
        count = None
        if len(params) > 1:
            try:
                count = int(params[1])
            except (ValueError, TypeError):
                count = None

        if count is not None:
            result = await g_pShopManager.buySeed(uid, seedName, count)
        else:
            result = await g_pShopManager.buySeed(uid, seedName)

        chain = [
            Comp.At(qq=uid),
            Comp.Plain(result),
        ]

        yield event.chain_result(chain)

    async def mySeed(self, event: AstrMessageEvent, params: List[str]):
        """我的种子"""
        uid = event.get_sender_id()

        exist = await g_pDBService.user.isUserExist(uid)
        if not exist:
            chain = [
                Comp.At(qq=uid),
                Comp.Plain(cfg.g_pConfigManager.sTranslation["basic"]["notFarm"]),
            ]

            yield event.chain_result(chain)
            return

        result = await g_pFarmManager.getUserSeedByUid(uid)

        chain = [
            Comp.At(qq=uid),
            Comp.Image.fromBase64(result),
        ]

        yield event.chain_result(chain)

    async def sowing(self, event: AstrMessageEvent, params: List[str]):
        """播种"""
        uid = event.get_sender_id()

        if not params:
            chain = [
                Comp.At(qq=uid),
                Comp.Plain(cfg.g_pConfigManager.sTranslation["sowing"]["notSeed"]),
            ]

            yield event.chain_result(chain)
            return

        exist = await g_pDBService.user.isUserExist(uid)
        if not exist:
            chain = [
                Comp.At(qq=uid),
                Comp.Plain(cfg.g_pConfigManager.sTranslation["basic"]["notFarm"]),
            ]

            yield event.chain_result(chain)
            return

        seedName = params[0]
        count = None
        if len(params) > 1:
            try:
                count = int(params[1])
            except (ValueError, TypeError):
                count = None

        if count is not None:
            result = await g_pFarmManager.sowing(uid, seedName, count)
        else:
            result = await g_pFarmManager.sowing(uid, seedName)

        chain = [
            Comp.At(qq=uid),
            Comp.Plain(result),
        ]

        yield event.chain_result(chain)

    async def harvest(self, event: AstrMessageEvent, params: List[str]):
        """收获"""
        uid = event.get_sender_id()

        exist = await g_pDBService.user.isUserExist(uid)
        if not exist:
            chain = [
                Comp.At(qq=uid),
                Comp.Plain(cfg.g_pConfigManager.sTranslation["basic"]["notFarm"]),
            ]

            yield event.chain_result(chain)
            return

        result = await g_pFarmManager.harvest(uid)

        chain = [
            Comp.At(qq=uid),
            Comp.Plain(result),
        ]

        yield event.chain_result(chain)

    async def eradicate(self, event: AstrMessageEvent, params: List[str]):
        """铲除"""
        uid = event.get_sender_id()

        exist = await g_pDBService.user.isUserExist(uid)
        if not exist:
            chain = [
                Comp.At(qq=uid),
                Comp.Plain(cfg.g_pConfigManager.sTranslation["basic"]["notFarm"]),
            ]

            yield event.chain_result(chain)
            return

        result = await g_pFarmManager.eradicate(uid)

        chain = [
            Comp.At(qq=uid),
            Comp.Plain(result),
        ]

        yield event.chain_result(chain)

    async def myPlant(self, event: AstrMessageEvent, params: List[str]):
        """我的作物"""
        uid = event.get_sender_id()

        exist = await g_pDBService.user.isUserExist(uid)
        if not exist:
            chain = [
                Comp.At(qq=uid),
                Comp.Plain(cfg.g_pConfigManager.sTranslation["basic"]["notFarm"]),
            ]

            yield event.chain_result(chain)
            return

        result = await g_pFarmManager.getUserPlantByUid(uid)

        chain = [
            Comp.At(qq=uid),
            Comp.Image.fromBase64(result),
        ]

        yield event.chain_result(chain)

    async def reclamation(self, event: AstrMessageEvent, params: List[str]):
        """开垦"""
        uid = event.get_sender_id()

        exist = await g_pDBService.user.isUserExist(uid)
        if not exist:
            chain = [
                Comp.At(qq=uid),
                Comp.Plain(cfg.g_pConfigManager.sTranslation["basic"]["notFarm"]),
            ]

            yield event.chain_result(chain)
            return

        try:
            condition = await g_pFarmManager.reclamationCondition(uid)
            condition += (
                f"\n{cfg.g_pConfigManager.sTranslation['reclamation']['confirm']}"
            )

            chain = [
                Comp.At(qq=uid),
                Comp.Plain(condition),
            ]

            yield event.chain_result(chain)

            @session_waiter(timeout=60, record_history_chains=False)
            async def check(controller: SessionController, event: AstrMessageEvent):
                if not event.message_str == "是":
                    controller.stop()
                    return

                res = await g_pFarmManager.reclamation(uid)

                message = event.make_result()
                message.chain = [
                    Comp.At(qq=uid),
                    Comp.Plain(res),
                ]
                await event.send(message)

                controller.stop()

            try:
                await check(event)
            except TimeoutError as _:  # 当超时后，会话控制器会抛出 TimeoutError
                yield event.plain_result(
                    cfg.g_pConfigManager.sTranslation["reclamation"]["timeOut"]
                )
            except Exception as e:
                yield event.plain_result(
                    cfg.g_pConfigManager.sTranslation["reclamation"]["error1"].format(
                        e=e
                    )
                )
            finally:
                event.stop_event()
        except Exception as e:
            logger.error(
                cfg.g_pConfigManager.sTranslation["reclamation"]["error2"].format(e=e)
            )

    async def sellPlant(self, event: AstrMessageEvent, params: List[str]):
        """出售作物"""
        uid = event.get_sender_id()

        exist = await g_pDBService.user.isUserExist(uid)
        if not exist:
            chain = [
                Comp.At(qq=uid),
                Comp.Plain(cfg.g_pConfigManager.sTranslation["basic"]["notFarm"]),
            ]

            yield event.chain_result(chain)
            return

        if params:
            seedName = params[0]
        else:
            seedName = ""

        count = None
        if len(params) > 1:
            try:
                count = int(params[1])
            except (ValueError, TypeError):
                count = None

        if count is not None:
            result = await g_pShopManager.sellPlantByUid(uid, seedName, count)
        else:
            result = await g_pShopManager.sellPlantByUid(uid, seedName)

        chain = [
            Comp.At(qq=uid),
            Comp.Plain(result),
        ]

        yield event.chain_result(chain)

    async def stealing(self, event: AstrMessageEvent, params: List[str]):
        """偷菜"""
        uid = event.get_sender_id()

        exist = await g_pDBService.user.isUserExist(uid)
        if not exist:
            chain = [
                Comp.At(qq=uid),
                Comp.Plain(cfg.g_pConfigManager.sTranslation["basic"]["notFarm"]),
            ]

            yield event.chain_result(chain)
            return

        targetList = []

        for comp in event.message_obj.message:
            if isinstance(comp, Comp.At):
                if isinstance(comp.qq, int):
                    targetList.append(str(comp.qq))

        if not targetList:
            chain = [
                Comp.At(qq=uid),
                Comp.Plain(cfg.g_pConfigManager.sTranslation["stealing"]["noTarget"]),
            ]

            yield event.chain_result(chain)
            return

        # 只处理第一个用户
        exist = await g_pDBService.user.isUserExist(targetList[0])
        if not exist:
            chain = [
                Comp.At(qq=uid),
                Comp.Plain(
                    cfg.g_pConfigManager.sTranslation["stealing"]["targetNotFarm"]
                ),
            ]

            yield event.chain_result(chain)
            return

        result = await g_pFarmManager.stealing(uid, targetList[0])

        chain = [
            Comp.At(qq=uid),
            Comp.Plain(result),
        ]

        yield event.chain_result(chain)

    async def changeName(self, event: AstrMessageEvent, params: List[str]):
        """更改农场名"""
        uid = event.get_sender_id()

        if not params:
            chain = [
                Comp.At(qq=uid),
                Comp.Plain(cfg.g_pConfigManager.sTranslation["changeName"]["noName"]),
            ]

            yield event.chain_result(chain)
            return

        exist = await g_pDBService.user.isUserExist(uid)
        if not exist:
            chain = [
                Comp.At(qq=uid),
                Comp.Plain(cfg.g_pConfigManager.sTranslation["basic"]["notFarm"]),
            ]

            yield event.chain_result(chain)
            return

        safeName = g_pToolManager.sanitize_username(params[0])

        if safeName == "神秘农夫":
            chain = [
                Comp.At(qq=uid),
                Comp.Plain(cfg.g_pConfigManager.sTranslation["changeName"]["error"]),
            ]

            yield event.chain_result(chain)
            return

        result = await g_pDBService.user.updateUserNameByUid(uid, safeName)

        if result:
            message = cfg.g_pConfigManager.sTranslation["changeName"]["success"]
        else:
            message = cfg.g_pConfigManager.sTranslation["changeName"]["error1"]

        chain = [
            Comp.At(qq=uid),
            Comp.Plain(message),
        ]

        yield event.chain_result(chain)

    async def signIn(self, event: AstrMessageEvent, params: List[str]):
        """农场签到"""
        uid = event.get_sender_id()

        exist = await g_pDBService.user.isUserExist(uid)
        if not exist:
            chain = [
                Comp.At(qq=uid),
                Comp.Plain(cfg.g_pConfigManager.sTranslation["basic"]["notFarm"]),
            ]

            yield event.chain_result(chain)
            return

        if not cfg.g_pConfigManager.bSignStatus:
            chain = [
                Comp.At(qq=uid),
                Comp.Plain(cfg.g_pConfigManager.sTranslation["signIn"]["error"]),
            ]

            yield event.chain_result(chain)
            return

        toDay = g_pToolManager.dateTime().date().today()
        message = ""
        status = await g_pDBService.userSign.sign(uid, toDay.strftime("%Y-%m-%d"))

        # 如果完成签到
        if status == 1 or status == 2:
            # 获取签到总天数
            signDay = await g_pDBService.userSign.getUserSignCountByDate(
                uid, toDay.strftime("%Y-%m")
            )
            exp, point = await g_pDBService.userSign.getUserSignRewardByDate(
                uid, toDay.strftime("%Y-%m-%d")
            )

            message += cfg.g_pConfigManager.sTranslation["signIn"]["success"].format(
                day=signDay, exp=exp, num=point
            )

            reward = g_pJsonManager.m_pSign["continuou"].get(f"{signDay}", None)

            if reward:
                extraPoint = reward.get("point", 0)
                extraExp = reward.get("exp", 0)

                plant = reward.get("plant", {})

                message += cfg.g_pConfigManager.sTranslation["signIn"][
                    "grandTotal"
                ].format(exp=extraExp, num=extraPoint)

                vipPoint = reward.get("vipPoint", 0)

                if vipPoint > 0:
                    message += cfg.g_pConfigManager.sTranslation["signIn"][
                        "grandTotal1"
                    ].format(num=vipPoint)

                if plant:
                    for key, value in plant.items():
                        message += cfg.g_pConfigManager.sTranslation["signIn"][
                            "grandTotal2"
                        ].format(name=key, num=value)
        else:
            message = "签到失败！未知错误"

        chain = [
            Comp.At(qq=uid),
            Comp.Plain(message),
        ]

        yield event.chain_result(chain)

    async def god(self, event: AstrMessageEvent, params: List[str]):
        """农场下阶段"""  # 非常规手段才可以进该函数 故不做判断
        uid = event.get_sender_id()

        await g_pDBService.userSoil.nextPhase(uid, int(params[0]))

    async def soilUpgrade(self, event: AstrMessageEvent, params: List[str]):
        """土地升级"""
        uid = event.get_sender_id()

        if not params:
            chain = [
                Comp.At(qq=uid),
                Comp.Plain(cfg.g_pConfigManager.sTranslation["soilInfo"]["noSoil"]),
            ]

            yield event.chain_result(chain)
            return

        exist = await g_pDBService.user.isUserExist(uid)
        if not exist:
            chain = [
                Comp.At(qq=uid),
                Comp.Plain(cfg.g_pConfigManager.sTranslation["basic"]["notFarm"]),
            ]

            yield event.chain_result(chain)
            return

        try:
            soilIndex = int(params[0])
            condition = await g_pFarmManager.soilUpgradeCondition(uid, soilIndex)

            chain = [
                Comp.At(qq=uid),
                Comp.Plain(condition),
            ]

            yield event.chain_result(chain)

            if not condition.startswith("将土地升级至："):
                return

            @session_waiter(timeout=60, record_history_chains=False)
            async def check(controller: SessionController, event: AstrMessageEvent):
                if not event.message_str == "是":
                    controller.stop()
                    return

                res = await g_pFarmManager.soilUpgrade(uid, soilIndex)

                message = event.make_result()
                message.chain = [
                    Comp.At(qq=uid),
                    Comp.Plain(res),
                ]
                await event.send(message)

                controller.stop()

            try:
                await check(event)
            except TimeoutError as _:  # 当超时后，会话控制器会抛出 TimeoutError
                yield event.plain_result(
                    cfg.g_pConfigManager.sTranslation["soilInfo"]["timeOut"]
                )
            except Exception as e:
                yield event.plain_result(
                    cfg.g_pConfigManager.sTranslation["soilInfo"]["error"].format(e=e)
                )
            finally:
                event.stop_event()
        except Exception as e:
            logger.error(
                cfg.g_pConfigManager.sTranslation["soilInfo"]["error2"].format(e=e)
            )

    async def terminate(self):
        """可选择实现异步的插件销毁方法，当插件被卸载/停用时会调用。"""
        await g_pSqlManager.cleanup()

        await g_pDBService.cleanup()
