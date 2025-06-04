import os
import re
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite

from astrbot.api import logger

from ..cfg import g_pConfigManager


class CSqlManager:
    def __init__(self):
        dbPath = Path(g_pConfigManager.sDBPath)
        if dbPath and not dbPath.exists():
            os.makedirs(dbPath, exist_ok=True)

    @classmethod
    async def cleanup(cls):
        if hasattr(cls, "m_pDB") and cls.m_pDB:
            await cls.m_pDB.close()

    @classmethod
    async def init(cls) -> bool:
        try:
            cls.m_pDB = await aiosqlite.connect(g_pConfigManager.sDBFilePath)
            cls.m_pDB.row_factory = aiosqlite.Row
            return True
        except Exception as e:
            logger.warning(f"初始化总数据库失败{e}")
            return False

    @classmethod
    @asynccontextmanager
    async def _transaction(cls):
        await cls.m_pDB.execute("BEGIN;")
        try:
            yield
        except:
            await cls.m_pDB.execute("ROLLBACK;")
            raise
        else:
            await cls.m_pDB.execute("COMMIT;")

    @classmethod
    async def getTableInfo(cls, tableName: str) -> list:
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", tableName):
            raise ValueError(f"Illegal table name: {tableName}")
        try:
            cursor = await cls.m_pDB.execute(f'PRAGMA table_info("{tableName}")')
            rows = await cursor.fetchall()
            return [{"name": row[1], "type": row[2]} for row in rows]
        except aiosqlite.Error:
            return []

    @classmethod
    async def ensureTableSchema(cls, tableName: str, columns: dict) -> bool:
        """由AI生成
        创建表或为已存在表添加缺失字段。
        返回 True 表示有变更（创建或新增列），False 则无操作

        Args:
            tableName (_type_): 表名
            columns (_type_): 字典

        Returns:
            _type_: _description_
        """

        info = await cls.getTableInfo(tableName)
        existing = {col["name"]: col["type"].upper() for col in info}
        desired = {k: v.upper() for k, v in columns.items() if k != "PRIMARY KEY"}
        primaryKey = columns.get("PRIMARY KEY", "")

        if not existing:
            colsDef = ", ".join(f'"{k}" {v}' for k, v in desired.items())
            if primaryKey:
                colsDef += f", PRIMARY KEY {primaryKey}"
            await cls.m_pDB.execute(f'CREATE TABLE "{tableName}" ({colsDef});')
            return True

        toAdd = [k for k in desired if k not in existing]
        toRemove = [k for k in existing if k not in desired]
        typeMismatch = [
            k for k in desired if k in existing and existing[k] != desired[k]
        ]

        if toAdd and not toRemove and not typeMismatch:
            for col in toAdd:
                await cls.m_pDB.execute(
                    f'ALTER TABLE "{tableName}" ADD COLUMN "{col}" {columns[col]}'
                )
            return True

        async with cls._transaction():
            tmpTable = f"{tableName}_new"
            colsDef = ", ".join(f'"{k}" {v}' for k, v in desired.items())
            if primaryKey:
                colsDef += f", PRIMARY KEY {primaryKey}"
            await cls.m_pDB.execute(f'CREATE TABLE "{tmpTable}" ({colsDef});')

            commonCols = [k for k in desired if k in existing]
            if commonCols:
                colsStr = ", ".join(f'"{c}"' for c in commonCols)
                await cls.m_pDB.execute(
                    f'INSERT INTO "{tmpTable}" ({colsStr}) SELECT {colsStr} FROM "{tableName}";'
                )
            await cls.m_pDB.execute(f'DROP TABLE "{tableName}";')
            await cls.m_pDB.execute(
                f'ALTER TABLE "{tmpTable}" RENAME TO "{tableName}";'
            )
        return True

    @classmethod
    async def executeDB(cls, command: str) -> bool:
        """执行自定义SQL

        Args:
            command (str): SQL语句

        Returns:
            bool: 是否执行成功
        """
        if not command:
            logger.warning("数据库语句长度为空！")
            return False

        try:
            async with cls._transaction():
                await cls.m_pDB.execute(command)
            return True
        except Exception as e:
            logger.warning(f"数据库语句执行出错: {command} {e}")
            return False


g_pSqlManager = CSqlManager()
