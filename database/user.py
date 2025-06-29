import math
from typing import List

from astrbot.api import logger

from ..tool import g_pToolManager
from .database import CSqlManager


class CUserDB(CSqlManager):
    @classmethod
    async def initDB(cls):
        """初始化用户表结构，确保user表存在且字段完整"""
        userInfo = {
            "uid": "TEXT PRIMARY KEY",  # 用户Uid
            "name": "TEXT NOT NULL",  # 农场名称
            "exp": "INTEGER DEFAULT 0",  # 经验值
            "point": "INTEGER DEFAULT 0",  # 金币
            "vipPoint": "INTEGER DEFAULT 0",  # 点券
            "soil": "INTEGER DEFAULT 3",  # 解锁土地数量
            "stealTime": "TEXT DEFAULT ''",  # 偷菜时间字符串
            "stealCount": "INTEGER DEFAULT 0",  # 剩余偷菜次数
        }
        await cls.ensureTableSchema("user", userInfo)

    @classmethod
    async def initUserInfoByUid(
        cls, uid: str, name: str = "", exp: int = 0, point: int = 500
    ) -> bool | str:
        """初始化用户信息，包含初始偷菜时间字符串与次数

        Args:
            uid (str): 用户Uid
            name (str): 农场名称
            exp (int): 农场经验
            point (int): 农场币

        Returns:
            bool | str: False 表示失败，字符串表示成功信息
        """
        nowStr = g_pToolManager.dateTime().date().today().strftime("%Y-%m-%d")
        sql = (
            f"INSERT INTO user (uid, name, exp, point, soil, stealTime, stealCount) "
            f"VALUES ({uid}, '{name}', {exp}, {point}, 3, '{nowStr}', 5)"
        )
        try:
            async with cls._transaction():
                await cls.m_pDB.execute(sql)
            return "开通农场成功"
        except Exception as e:
            logger.warning("initUserInfoByUid 事务执行失败！", e=e)
            return False

    @classmethod
    async def getAllUsers(cls) -> List[str]:
        """获取所有用户UID列表

        Returns:
            List[str]: 用户UID列表
        """
        cursor = await cls.m_pDB.execute("SELECT uid FROM user")
        rows = await cursor.fetchall()
        return [row[0] for row in rows]

    @classmethod
    async def isUserExist(cls, uid: str) -> bool:
        """判断用户是否存在

        Args:
            uid (str): 用户Uid

        Returns:
            bool: 如果用户存在返回True，否则返回False
        """
        if not uid:
            return False
        try:
            async with cls.m_pDB.execute(
                "SELECT 1 FROM user WHERE uid = ?", (uid,)
            ) as cursor:
                row = await cursor.fetchone()
                return row is not None
        except Exception as e:
            logger.warning("isUserExist 查询失败！", e=e)
            return False

    @classmethod
    async def getUserInfoByUid(cls, uid: str) -> dict:
        """获取指定用户完整信息

        Args:
            uid (str): 用户Uid

        Returns:
            dict: 包含所有用户字段的字典
        """
        if not uid:
            return {}
        try:
            async with cls.m_pDB.execute(
                "SELECT * FROM user WHERE uid = ?", (uid,)
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return {}

                result = dict(row)

            return result
        except Exception as e:
            logger.warning("getUserInfoByUid 查询失败！", e=e)
            return {}

    @classmethod
    async def getUserNameByUid(cls, uid: str) -> str:
        """根据用户Uid获取用户名

        Args:
            uid (str): 用户Uid

        Returns:
            str: 用户名，失败返回空字符串
        """
        if not uid:
            return ""
        try:
            async with cls.m_pDB.execute(
                "SELECT name FROM user WHERE uid = ?", (uid,)
            ) as cursor:
                row = await cursor.fetchone()
                return row["name"] if row else ""
        except Exception as e:
            logger.warning("getUserNameByUid 查询失败！", e=e)
            return ""

    @classmethod
    async def updateUserNameByUid(cls, uid: str, name: str) -> bool:
        """根据用户Uid更新用户名

        Args:
            uid (str): 用户Uid
            name (str): 新用户名

        Returns:
            bool: 是否更新成功
        """
        if not uid or not name:
            return False
        try:
            async with cls._transaction():
                await cls.m_pDB.execute(
                    "UPDATE user SET name = ? WHERE uid = ?", (name, uid)
                )
            return True
        except Exception as e:
            logger.warning("updateUserNameByUid 事务执行失败！", e=e)
            return False

    @classmethod
    async def getUserPointByUid(cls, uid: str) -> int:
        """获取指定用户农场币

        Args:
            uid (str): 用户Uid

        Returns:
            int: 农场币数量，失败返回 -1
        """
        if not uid:
            return -1
        try:
            async with cls.m_pDB.execute(
                "SELECT point FROM user WHERE uid = ?", (uid,)
            ) as cursor:
                row = await cursor.fetchone()
                return int(row[0]) if row and row[0] is not None else -1
        except Exception as e:
            logger.warning("getUserPointByUid 查询失败！", e=e)
            return -1

    @classmethod
    async def updateUserPointByUid(cls, uid: str, point: int) -> bool:
        """根据用户Uid更新农场币数量

        Args:
            uid (str): 用户Uid
            point (int): 新农场币数量

        Returns:
            bool: 是否更新成功
        """
        if not uid or point < 0:
            logger.warning("updateUserPointByUid 参数校验失败！")
            return False
        try:
            async with cls._transaction():
                await cls.m_pDB.execute(
                    "UPDATE user SET point = ? WHERE uid = ?", (point, uid)
                )
            return True
        except Exception as e:
            logger.error("updateUserPointByUid 事务执行失败！", e=e)
            return False

    @classmethod
    async def getUserVipPointByUid(cls, uid: str) -> int:
        """获取指定用户点券

        Args:
            uid (str): 用户Uid

        Returns:
            int: 点券数量，失败返回 -1
        """
        if not uid:
            return -1
        try:
            async with cls.m_pDB.execute(
                "SELECT vipPoint FROM user WHERE uid = ?", (uid,)
            ) as cursor:
                row = await cursor.fetchone()
                return int(row[0]) if row and row[0] is not None else -1
        except Exception as e:
            logger.warning("getUservipPointByUid 查询失败！", e=e)
            return -1

    @classmethod
    async def updateUserVipPointByUid(cls, uid: str, vipPoint: int) -> bool:
        """根据用户Uid更新点券数量

        Args:
            uid (str): 用户Uid
            vipPoint (int): 新点券数量

        Returns:
            bool: 是否更新成功
        """
        if not uid or vipPoint < 0:
            logger.warning("updateUservipPointByUid 参数校验失败！")
            return False
        try:
            async with cls._transaction():
                await cls.m_pDB.execute(
                    "UPDATE user SET vipPoint = ? WHERE uid = ?", (vipPoint, uid)
                )
            return True
        except Exception as e:
            logger.error("updateUservipPointByUid 事务执行失败！", e=e)
            return False

    @classmethod
    async def getUserExpByUid(cls, uid: str) -> int:
        """获取指定用户经验值

        Args:
            uid (str): 用户Uid

        Returns:
            int: 经验值，失败返回 -1
        """
        if not uid:
            return -1
        try:
            async with cls.m_pDB.execute(
                "SELECT exp FROM user WHERE uid = ?", (uid,)
            ) as cursor:
                row = await cursor.fetchone()
                return int(row[0]) if row and row[0] is not None else -1
        except Exception as e:
            logger.warning("getUserExpByUid 查询失败！", e=e)
            return -1

    @classmethod
    async def updateUserExpByUid(cls, uid: str, exp: int) -> bool:
        """根据用户Uid更新经验值

        Args:
            uid (str): 用户Uid
            exp (int): 新经验值

        Returns:
            bool: 是否更新成功
        """
        if not uid:
            return False
        try:
            async with cls._transaction():
                await cls.m_pDB.execute(
                    "UPDATE user SET exp = ? WHERE uid = ?", (exp, uid)
                )
            return True
        except Exception as e:
            logger.warning("updateUserExpByUid 事务执行失败！", e=e)
            return False

    @classmethod
    async def getUserLevelByUid(cls, uid: str) -> tuple[int, int, int]:
        """获取用户等级信息

        Args:
            uid (str): 用户Uid

        Returns:
            tuple[int, int, int]: 成功返回(当前等级, 升至下级还需经验, 当前等级已获经验)
            失败返回(-1, -1, -1)
        """
        if not uid:
            return -1, -1, -1

        try:
            async with cls.m_pDB.execute(
                "SELECT exp FROM user WHERE uid = ?", (uid,)
            ) as cursor:
                row = await cursor.fetchone()
                if not row or row[0] is None:
                    return -1, -1, -1

                expVal = int(row[0])
                levelStep = 200  # 每级经验增量

                discriminant = 1 + 8 * expVal / levelStep
                level = int((-1 + math.sqrt(discriminant)) // 2)
                if level < 0:
                    level = 0

                def cumExp(k: int) -> int:
                    return levelStep * k * (k + 1) // 2

                totalExpCurrentLevel = cumExp(level)
                totalExpNextLevel = cumExp(level + 1)

                currentExp = expVal - totalExpCurrentLevel

                return level, totalExpNextLevel, currentExp

            return -1, -1, -1
        except Exception as e:
            logger.warning("getUserLevelByUid 查询失败！", e=e)
            return -1, -1, -1

    @classmethod
    async def getUserSoilByUid(cls, uid: str) -> int:
        """获取解锁土地数量

        Args:
            uid (str): 用户Uid

        Returns:
            int: 解锁土地块数，失败返回0
        """
        if not uid:
            return 0
        try:
            async with cls.m_pDB.execute(
                "SELECT soil FROM user WHERE uid = ?", (uid,)
            ) as cursor:
                row = await cursor.fetchone()
                return int(row[0]) if row and row[0] is not None else 0
        except Exception as e:
            logger.warning("getUserSoilByUid 查询失败！", e=e)
            return 0

    @classmethod
    async def updateUserSoilByUid(cls, uid: str, soil: int) -> bool:
        """更新指定用户解锁土地数量

        Args:
            uid (str): 用户Uid
            soil (int): 新土地数量

        Returns:
            bool: 更新成功返回True，否则False
        """
        if not uid or soil < 0:
            return False
        try:
            async with cls._transaction():
                await cls.m_pDB.execute(
                    "UPDATE user SET soil = ? WHERE uid = ?", (soil, uid)
                )
            return True
        except Exception as e:
            logger.warning("updateUserSoilByUid 事务执行失败！", e=e)
            return False

    @classmethod
    async def getStealTimeByUid(cls, uid: str) -> str:
        """根据用户Uid获取偷菜时间字符串

        Args:
            uid (str): 用户Uid

        Returns:
            str: 偷菜时间字符串，失败返回空字符串
        """
        if not uid:
            return ""
        try:
            async with cls.m_pDB.execute(
                "SELECT stealTime FROM user WHERE uid = ?", (uid,)
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row and row[0] else ""
        except Exception as e:
            logger.warning("getStealTimeByUid 查询失败！", e=e)
            return ""

    @classmethod
    async def updateStealTimeByUid(cls, uid: str, stealTime: str) -> bool:
        """根据用户Uid更新偷菜时间字符串

        Args:
            uid (str): 用户Uid
            stealTime (str): 新偷菜时间字符串

        Returns:
            bool: 是否更新成功
        """
        if not uid or not stealTime:
            logger.warning("updateStealTimeByUid 参数校验失败！")
            return False
        try:
            async with cls._transaction():
                await cls.m_pDB.execute(
                    "UPDATE user SET stealTime = ? WHERE uid = ?", (stealTime, uid)
                )
            return True
        except Exception as e:
            logger.warning("updateStealTimeByUid 事务执行失败！", e=e)
            return False

    @classmethod
    async def getStealCountByUid(cls, uid: str) -> int:
        """根据用户Uid获取剩余偷菜次数

        Args:
            uid (str): 用户Uid

        Returns:
            int: 剩余偷菜次数，失败返回 -1
        """
        if not uid:
            return -1
        try:
            async with cls.m_pDB.execute(
                "SELECT stealCount FROM user WHERE uid = ?", (uid,)
            ) as cursor:
                row = await cursor.fetchone()
                return int(row[0]) if row and row[0] is not None else 0
        except Exception as e:
            logger.warning("getStealCountByUid 查询失败！", e=e)
            return -1

    @classmethod
    async def updateStealCountByUid(
        cls, uid: str, stealTime: str, stealCount: int
    ) -> bool:
        """根据用户Uid更新剩余偷菜次数

        Args:
            uid (str): 用户Uid
            stealTime (str): 偷菜日期
            stealCount (int): 新剩余偷菜次数

        Returns:
            bool: 是否更新成功
        """
        if not uid or stealCount < 0:
            logger.warning("updateStealCountByUid 参数校验失败！")
            return False
        try:
            async with cls._transaction():
                await cls.m_pDB.execute(
                    "UPDATE user SET stealTime = ?, stealCount = ? WHERE uid = ?",
                    (stealTime, stealCount, uid),
                )
            return True
        except Exception as e:
            logger.warning("updateStealCountByUid 事务执行失败！", e=e)
            return False
