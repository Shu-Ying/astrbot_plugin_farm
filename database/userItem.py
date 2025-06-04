from typing import Optional

from astrbot.api import logger
from .database import CSqlManager


class CUserItemDB(CSqlManager):
    @classmethod
    async def initDB(cls):
        userItem = {
            "uid": "TEXT NOT NULL",  # 用户Uid
            "item": "TEXT NOT NULL",  # 物品名称
            "count": "INTEGER NOT NULL DEFAULT 0",  # 数量
            "PRIMARY KEY": "(uid, item)",
        }

        await cls.ensureTableSchema("userItem", userItem)

    @classmethod
    async def getUserItemByName(cls, uid: str, item: str) -> Optional[int]:
        """根据道具名称查询某一项数量

        Args:
            uid (str): 用户uid
            item (str): 道具名称

        Returns:
            Optional[int]: 数量（不存在返回None）
        """
        if not uid or not item:
            return None
        try:
            async with cls.m_pDB.execute(
                "SELECT count FROM userItem WHERE uid = ? AND item = ?", (uid, item)
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None
        except Exception as e:
            logger.warning("getUserItemByName查询失败！", e=e)
            return None

    @classmethod
    async def getUserItemByUid(cls, uid: str) -> dict:
        """根据用户Uid获取全部道具信息

        Args:
            uid (str): 用户uid

        Returns:
            dict: {itemName: count, ...}
        """
        if not uid:
            return {}
        try:
            cursor = await cls.m_pDB.execute(
                "SELECT item, count FROM userItem WHERE uid = ?", (uid,)
            )
            rows = await cursor.fetchall()
            return {row["item"]: row["count"] for row in rows}
        except Exception as e:
            logger.warning("getUserItemByUid查询失败！", e=e)
            return {}

    @classmethod
    async def deleteUserItemByName(cls, uid: str, item: str) -> bool:
        """根据道具名删除道具

        Args:
            uid (str): 用户uid
            item (str): 道具名称

        Returns:
            bool: 是否删除成功
        """
        if not uid or not item:
            return False
        try:
            async with cls._transaction():
                await cls.m_pDB.execute(
                    "DELETE FROM userItem WHERE uid = ? AND item = ?", (uid, item)
                )
            return True
        except Exception as e:
            logger.warning("deleteUserItemByName失败！", e=e)
            return False

    @classmethod
    async def updateUserItemByName(cls, uid: str, item: str, count: int) -> bool:
        """根据道具名直接更新道具数量

        Args:
            uid (str): 用户uid
            item (str): 道具名称
            count (int): 要更新的新数量

        Returns:
            bool: 是否更新成功
        """
        if not uid or not item:
            return False
        try:
            async with cls._transaction():
                if count <= 0:
                    await cls.m_pDB.execute(
                        "DELETE FROM userItem WHERE uid = ? AND item = ?", (uid, item)
                    )
                else:
                    await cls.m_pDB.execute(
                        "UPDATE userItem SET count = ? WHERE uid = ? AND item = ?",
                        (count, uid, item),
                    )
            return True
        except Exception as e:
            logger.warning("updateUserItemByName失败！", e=e)
            return False

    @classmethod
    async def addUserItemByUid(cls, uid: str, item: str, count: int = 1) -> bool:
        """根据用户uid添加道具信息

        Args:
            uid (str): 用户uid
            item (str): 道具名称
            count (int, optional): 数量.Defaults to 1.

        Returns:
            bool: 是否添加成功
        """
        if not uid or not item:
            return False
        try:
            async with cls._transaction():
                async with cls.m_pDB.execute(
                    "SELECT count FROM userItem WHERE uid = ? AND item = ?", (uid, item)
                ) as cursor:
                    row = await cursor.fetchone()

                if row:
                    newCount = row[0] + count
                    if newCount <= 0:
                        await cls.m_pDB.execute(
                            "DELETE FROM userItem WHERE uid = ? AND item = ?",
                            (uid, item),
                        )
                    else:
                        await cls.m_pDB.execute(
                            "UPDATE userItem SET count = ? WHERE uid = ? AND item = ?",
                            (newCount, uid, item),
                        )
                else:
                    if count > 0:
                        await cls.m_pDB.execute(
                            "INSERT INTO userItem (uid, item, count) VALUES (?, ?, ?)",
                            (uid, item, count),
                        )
            return True
        except Exception as e:
            logger.warning("addUserItemByUid失败！", e=e)
            return False
