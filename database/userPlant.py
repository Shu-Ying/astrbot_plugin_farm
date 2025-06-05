from typing import Dict, Optional

from astrbot.api import logger

from .database import CSqlManager


class CUserPlantDB(CSqlManager):
    @classmethod
    async def initDB(cls):
        userPlant = {
            "uid": "TEXT NOT NULL",  # 用户Uid
            "plant": "TEXT NOT NULL",  # 作物名称
            "count": "INTEGER NOT NULL DEFAULT 0",  # 数量
            "PRIMARY KEY": "(uid, plant)",
        }

        await cls.ensureTableSchema("userPlant", userPlant)

    @classmethod
    async def addUserPlantByUid(cls, uid: str, plant: str, count: int = 1) -> bool:
        """根据用户uid添加作物信息

        Args:
            uid (str): 用户uid
            plant (str): 作物名称
            count (int): 数量

        Returns:
            bool: 是否添加成功
        """
        try:
            async with cls._transaction():
                # 检查是否已存在该作物
                async with cls.m_pDB.execute(
                    "SELECT count FROM userPlant WHERE uid = ? AND plant = ?",
                    (uid, plant),
                ) as cursor:
                    row = await cursor.fetchone()

                if row:
                    # 如果作物已存在，则更新数量
                    new_count = row[0] + count
                    await cls.m_pDB.execute(
                        "UPDATE userPlant SET count = ? WHERE uid = ? AND plant = ?",
                        (new_count, uid, plant),
                    )
                else:
                    # 如果作物不存在，则插入新记录
                    await cls.m_pDB.execute(
                        "INSERT INTO userPlant (uid, plant, count) VALUES (?, ?, ?)",
                        (uid, plant, count),
                    )
            return True
        except Exception as e:
            logger.warning("addUserPlantByUid 失败！", e=e)
            return False

    @classmethod
    async def getUserPlantByUid(cls, uid: str) -> Dict[str, int]:
        """根据用户uid获取全部作物信息

        Args:
            uid (str): 用户uid

        Returns:
            Dict[str, int]: 作物名称和数量
        """
        cursor = await cls.m_pDB.execute(
            "SELECT plant, count FROM userPlant WHERE uid=?", (uid,)
        )
        rows = await cursor.fetchall()
        return {row["plant"]: row["count"] for row in rows}

    @classmethod
    async def getUserPlantByName(cls, uid: str, plant: str) -> Optional[int]:
        """根据作物名称获取用户的作物数量

        Args:
            uid (str): 用户uid
            plant (str): 作物名称

        Returns:
            Optional[int]: 作物数量
        """
        try:
            async with cls.m_pDB.execute(
                "SELECT count FROM userPlant WHERE uid = ? AND plant = ?", (uid, plant)
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None
        except Exception as e:
            logger.warning("getUserPlantByName 查询失败！", e=e)
            return None

    @classmethod
    async def updateUserPlantByName(cls, uid: str, plant: str, count: int) -> bool:
        """更新 userPlant 表中某个作物的数量

        Args:
            uid (str): 用户uid
            plant (str): 作物名称
            count (int): 新的作物数量

        Returns:
            bool: 是否更新成功
        """
        try:
            if count <= 0:
                return await cls.deleteUserPlantByName(uid, plant)

            async with cls._transaction():
                await cls.m_pDB.execute(
                    "UPDATE userPlant SET count = ? WHERE uid = ? AND plant = ?",
                    (count, uid, plant),
                )
            return True
        except Exception as e:
            logger.warning("updateUserPlantByName失败！", e=e)
            return False

    @classmethod
    async def deleteUserPlantByName(cls, uid: str, plant: str) -> bool:
        """从 userPlant 表中删除某个作物记录

        Args:
            uid (str): 用户uid
            plant (str): 作物名称

        Returns:
            bool: 是否删除成功
        """
        try:
            async with cls._transaction():
                await cls.m_pDB.execute(
                    "DELETE FROM userPlant WHERE uid = ? AND plant = ?", (uid, plant)
                )
            return True
        except Exception as e:
            logger.warning("deleteUserPlantByName 失败！", e=e)
            return False
