from typing import Optional


class CDBService:
    @classmethod
    async def init(cls):
        from .database.plant import CPlantManager
        from .database.user import CUserDB
        from .database.userItem import CUserItemDB
        from .database.userPlant import CUserPlantDB
        from .database.userSeed import CUserSeedDB
        from .database.userSign import CUserSignDB
        from .database.userSoil import CUserSoilDB
        from .database.userSteal import CUserStealDB

        cls.plant = CPlantManager()
        await cls.plant.init()

        cls.user = CUserDB()
        await cls.user.initDB()

        cls.userSoil = CUserSoilDB()
        await cls.userSoil.initDB()

        cls.userPlant = CUserPlantDB()
        await cls.userPlant.initDB()

        cls.userSeed = CUserSeedDB()
        await cls.userSeed.initDB()

        cls.userItem = CUserItemDB()
        await cls.userItem.initDB()

        cls.userSteal = CUserStealDB()
        await cls.userSteal.initDB()

        cls.userSign = CUserSignDB()
        await cls.userSign.initDB()

        #迁移旧数据库
        await cls.userSoil.migrateOldFarmData()

    @classmethod
    async def cleanup(cls):
        await cls.plant.cleanup()

g_pDBService = CDBService()
