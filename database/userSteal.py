from astrbot.api import logger

from .database import CSqlManager


class CUserStealDB(CSqlManager):
    @classmethod
    async def initDB(cls):
        userSteal = {
            "uid": "TEXT NOT NULL",             #被偷用户Uid
            "soilIndex": "INTEGER NOT NULL",    #被偷的地块索引 从1开始
            "stealerUid": "TEXT NOT NULL",      #偷菜用户Uid
            "stealCount": "INTEGER NOT NULL",   #被偷数量
            "stealTime": "INTEGER NOT NULL",    #被偷时间
            "PRIMARY KEY": "(uid, soilIndex, stealerUid)"
        }
        await cls.ensureTableSchema("userSteal", userSteal)

    @classmethod
    async def addStealRecord(cls, uid: str, soilIndex: int, stealerUid: str, stealCount: int, stealTime: int) -> bool:
        """添加偷菜记录

        Args:
            uid (str): 被偷用户Uid
            soilIndex (int): 被偷地块索引
            stealerUid (str): 偷菜用户Uid
            stealCount (int): 被偷数量
            stealTime (int): 被偷时间（时间戳）

        Returns:
            bool: 操作是否成功
        """
        try:
            async with cls._transaction():
                await cls.m_pDB.execute(
                    'INSERT INTO "userSteal"(uid, soilIndex, stealerUid, stealCount, stealTime) VALUES(?, ?, ?, ?, ?);',
                    (uid, soilIndex, stealerUid, stealCount, stealTime)
                )
            return True
        except Exception as e:
            logger.warning("添加偷菜记录失败", e=e)
            return False

    @classmethod
    async def getStealRecordsByUid(cls, uid: str) -> list:
        """根据用户Uid获取所有偷菜记录

        Args:
            uid (str): 被偷用户Uid

        Returns:
            list: 偷菜记录字典列表，每条包含 soilIndex, stealerUid, stealCount, stealTime
        """
        try:
            async with cls._transaction():
                cursor = await cls.m_pDB.execute(
                    'SELECT soilIndex, stealerUid, stealCount, stealTime FROM "userSteal" WHERE uid=?;',
                    (uid,)
                )
                rows = await cursor.fetchall()
            return [
                {
                    "uid": uid,
                    "soilIndex": row[0],
                    "stealerUid": row[1],
                    "stealCount": row[2],
                    "stealTime": row[3]
                }
                for row in rows
            ]
        except Exception as e:
            logger.warning("获取偷菜记录失败", e=e)
            return []

    @classmethod
    async def getStealRecord(cls, uid: str, soilIndex: int) -> list:
        """获取指定地块的所有偷菜记录

        Args:
            uid (str): 被偷用户Uid
            soilIndex (int): 被偷地块索引

        Returns:
            list: 偷菜记录字典列表，每条包含 stealerUid, stealCount, stealTime
        """
        try:
            async with cls._transaction():
                cursor = await cls.m_pDB.execute(
                    'SELECT stealerUid, stealCount, stealTime FROM "userSteal" WHERE uid=? AND soilIndex=?;',
                    (uid, soilIndex)
                )
                rows = await cursor.fetchall()
            return [
                {
                    "uid": uid,
                    "soilIndex": soilIndex,
                    "stealerUid": row[0],
                    "stealCount": row[1],
                    "stealTime": row[2]
                }
                for row in rows
            ]
        except Exception as e:
            logger.warning("获取单地块偷菜记录失败", e=e)
            return []

    @classmethod
    async def getTotalStolenCount(cls, uid: str, soilIndex: int) -> int:
        """计算指定地块被偷的总数量（所有用户偷取数量之和）

        Args:
            uid (str): 被偷用户Uid
            soilIndex (int): 被偷地块索引

        Returns:
            int: 被偷的总数量，如果无记录则返回 0
        """
        try:
            async with cls._transaction():
                cursor = await cls.m_pDB.execute(
                    'SELECT SUM(stealCount) FROM "userSteal" WHERE uid=? AND soilIndex=?;',
                    (uid, soilIndex)
                )
                row = await cursor.fetchone()
            return row[0] or 0 # type: ignore
        except Exception as e:
            logger.warning("计算总偷菜数量失败", e=e)
            return 0

    @classmethod
    async def getStealerCount(cls, uid: str, soilIndex: int) -> int:
        """计算指定地块被多少人偷过（不同偷菜用户数量）

        Args:
            uid (str): 被偷用户Uid
            soilIndex (int): 被偷地块索引

        Returns:
            int: 偷菜者总数，如果无记录则返回 0
        """
        try:
            async with cls._transaction():
                cursor = await cls.m_pDB.execute(
                    'SELECT COUNT(DISTINCT stealerUid) FROM "userSteal" WHERE uid=? AND soilIndex=?;',
                    (uid, soilIndex)
                )
                row = await cursor.fetchone()
            return row[0] or 0 # type: ignore
        except Exception as e:
            logger.warning("计算偷菜者数量失败", e=e)
            return 0

    @classmethod
    async def hasStealed(cls, uid: str, soilIndex: int, stealerUid: str) -> bool:
        """判断指定用户是否曾偷取过该地块

        Args:
            uid (str): 被偷用户Uid
            soilIndex (int): 被偷地块索引
            stealerUid (str): 偷菜用户Uid

        Returns:
            bool: 若存在记录返回 True，否则返回 False
        """
        try:
            async with cls._transaction():
                cursor = await cls.m_pDB.execute(
                    'SELECT 1 FROM "userSteal" WHERE uid=? AND soilIndex=? AND stealerUid=? LIMIT 1;',
                    (uid, soilIndex, stealerUid)
                )
                row = await cursor.fetchone()
            return bool(row)
        except Exception as e:
            logger.warning("检查偷菜记录失败", e=e)
            return False

    @classmethod
    async def updateStealRecord(cls, uid: str, soilIndex: int, stealerUid: str, stealCount: int, stealTime: int) -> bool:
        """更新偷菜记录的数量和时间

        Args:
            uid (str): 被偷用户Uid
            soilIndex (int): 被偷地块索引
            stealerUid (str): 偷菜用户Uid
            stealCount (int): 新的偷菜数量
            stealTime (int): 新的偷菜时间（时间戳）

        Returns:
            bool: 操作是否成功
        """
        try:
            async with cls._transaction():
                await cls.m_pDB.execute(
                    'UPDATE "userSteal" SET stealCount=?, stealTime=? WHERE uid=? AND soilIndex=? AND stealerUid=?;',
                    (stealCount, stealTime, uid, soilIndex, stealerUid)
                )
            return True
        except Exception as e:
            logger.warning("更新偷菜记录失败", e=e)
            return False

    @classmethod
    async def deleteStealRecord(cls, uid: str, soilIndex: int) -> bool:
        """删除指定偷菜记录（只需被偷用户Uid和地块索引）

        Args:
            uid (str): 被偷用户Uid
            soilIndex (int): 被偷地块索引

        Returns:
            bool: 删除是否成功
        """
        try:
            async with cls._transaction():
                await cls.m_pDB.execute(
                    'DELETE FROM "userSteal" WHERE uid=? AND soilIndex=?;',
                    (uid, soilIndex)
                )
            return True
        except Exception as e:
            logger.warning("删除偷菜记录失败", e=e)
            return False
