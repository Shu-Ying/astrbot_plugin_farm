import json

from astrbot.api import logger

from . import cfg
from .request import g_pRequestManager


class CJsonManager:
    def __init__(self):
        self.m_pItem = {}
        self.m_pLevel = {}
        self.m_pSoil = {}
        self.m_pSign = {}

    async def init(self) -> bool:
        if not await self.initItem():
            return False

        if not await self.initLevel():
            return False

        if not await self.initSoil():
            return False

        return await self.initSignInFile()

    async def initItem(self) -> bool:
        try:
            with open(
                cfg.g_pConfigManager.sConfigPath / "item.json",
                encoding="utf-8",
            ) as file:
                self.m_pItem = json.load(file)

                return True
        except FileNotFoundError:
            logger.warning("item.json 打开失败")
            return False
        except json.JSONDecodeError as e:
            logger.warning(f"item.json JSON格式错误: {e}")
            return False

    async def initLevel(self) -> bool:
        try:
            with open(
                cfg.g_pConfigManager.sConfigPath / "level.json",
                encoding="utf-8",
            ) as file:
                self.m_pLevel = json.load(file)

                return True
        except FileNotFoundError:
            logger.warning("level.json 打开失败")
            return False
        except json.JSONDecodeError as e:
            logger.warning(f"level.json JSON格式错误: {e}")
            return False

    async def initSoil(self) -> bool:
        try:
            with open(
                cfg.g_pConfigManager.sConfigPath / "soil.json",
                encoding="utf-8",
            ) as file:
                self.m_pSoil = json.load(file)

                return True
        except FileNotFoundError:
            logger.warning("soil.json 打开失败")
            return False
        except json.JSONDecodeError as e:
            logger.warning(f"soil.json JSON格式错误: {e}")
            return False

    async def initSignInFile(self) -> bool:
        if not await g_pRequestManager.initSignInFile():
            cfg.g_pConfigManager.bSignStatus = False

            return False
        else:
            result = await self.initSign()

            cfg.g_pConfigManager.bSignStatus = result

            return result

    async def initSign(self) -> bool:
        try:
            with open(
                cfg.g_pConfigManager.sSignInPath,
                encoding="utf-8",
            ) as file:
                self.m_pSign = json.load(file)

                return True
        except FileNotFoundError:
            logger.warning("sign_in.json 打开失败")
            return False
        except json.JSONDecodeError as e:
            logger.warning(f"sign_in.json JSON格式错误: {e}")
            return False


g_pJsonManager = CJsonManager()
