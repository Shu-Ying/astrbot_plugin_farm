import math

from astrbot.api import logger
from ..zhenxun_utils.image_utils import ImageTemplate

from ..cfg import g_sResourcePath
from ..dbService import g_pDBService


class CShopManager:
    @classmethod
    async def getSeedShopImage(cls, filterKey: str | int = 1, num: int = 1) -> bytes:
        """获取商店页面

        Args:
            filterKey (str|int):
                - 字符串: 根据关键字筛选种子名称
                - 整数: 翻至对应页（无筛选）
            num (int, optional): 当 filterKey 为字符串时，用于指定页码。Defaults to 1.

        Returns:
            bytes: 返回商店图片bytes
        """
        # 解析参数：区分筛选关键字和页码
        filterStr = None
        if isinstance(filterKey, int):
            page = filterKey
        else:
            filterStr = filterKey
            page = num

        # 表头定义
        columnName = [
            "-",
            "种子名称",
            "种子单价",
            "解锁等级",
            "果实单价",
            "收获经验",
            "收获数量",
            "成熟时间（小时）",
            "收获次数",
            "是否可以上架交易行",
        ]

        # 查询所有可购买作物，并根据筛选关键字过滤
        plants = await g_pDBService.plant.listPlants()
        filteredPlants = []
        for plant in plants:
            # 跳过未解锁购买的种子
            if plant["isBuy"] == 0:
                continue
            # 字符串筛选
            if filterStr and filterStr not in plant["name"]:
                continue
            filteredPlants.append(plant)

        # 计算分页
        totalCount = len(filteredPlants)
        pageCount = math.ceil(totalCount / 15) if totalCount else 1
        startIndex = (page - 1) * 15
        pageItems = filteredPlants[startIndex : startIndex + 15]

        # 构建数据行
        dataList = []
        for plant in pageItems:
            # 图标处理
            icon = ""
            iconPath = g_sResourcePath / f"plant/{plant['name']}/icon.png"
            if iconPath.exists():
                icon = (iconPath, 33, 33)

            # 交易行标记
            sell = "可以" if plant["sell"] else "不可以"

            dataList.append(
                [
                    icon,
                    plant["name"],  # 种子名称
                    plant["buy"],  # 种子单价
                    plant["level"],  # 解锁等级
                    plant["price"],  # 果实单价
                    plant["experience"],  # 收获经验
                    plant["harvest"],  # 收获数量
                    plant["time"],  # 成熟时间（小时）
                    plant["crop"],  # 收获次数
                    sell,  # 是否可上架交易行
                ]
            )

        # 页码标题
        title = f"种子商店 页数: {page}/{pageCount}"

        # 渲染表格并返回图片bytes
        result = await ImageTemplate.table_page(
            title,
            "购买示例：@小真寻 购买种子 大白菜 5",
            columnName,
            dataList,
        )
        return result.pic2bytes()

    @classmethod
    async def buySeed(cls, uid: str, name: str, num: int = 1) -> str:
        """购买种子

        Args:
            uid (str): 用户Uid
            name (str): 植物名称
            num (int, optional): 购买数量

        Returns:
            str:
        """

        if num <= 0:
            return "请输入购买数量！"

        plantInfo = await g_pDBService.plant.getPlantByName(name)
        if not plantInfo:
            return "购买出错！请检查需购买的种子名称！"

        level = await g_pDBService.user.getUserLevelByUid(uid)

        if level[0] < int(plantInfo["level"]):
            return "你的等级不够哦，努努力吧"

        point = await g_pDBService.user.getUserPointByUid(uid)
        total = int(plantInfo["buy"]) * num

        logger.debug(
            f"用户：{uid}购买{name}，数量为{num}。用户农场币为{point}，购买需要{total}"
        )

        if point < total:
            return "你的农场币不够哦~ 快速速氪金吧！"
        else:
            await g_pDBService.user.updateUserPointByUid(uid, point - total)

            if not await g_pDBService.userSeed.addUserSeedByUid(uid, name, num):
                return "购买失败，执行数据库错误！"

            return f"成功购买{name}，花费{total}农场币, 剩余{point - total}农场币"

    @classmethod
    async def sellPlantByUid(cls, uid: str, name: str = "", num: int = 1) -> str:
        """出售作物

        Args:
            uid (str): 用户Uid

        Returns:
            str:
        """
        if not isinstance(name, str) or name.strip() == "":
            name = ""

        plant = await g_pDBService.userPlant.getUserPlantByUid(uid)
        if not plant:
            return "你仓库没有可以出售的作物"

        point = 0
        totalSold = 0
        isAll = num == -1

        if name == "":
            for plantName, count in plant.items():
                plantInfo = await g_pDBService.plant.getPlantByName(plantName)
                if not plantInfo:
                    continue

                point += plantInfo["price"] * count
                await g_pDBService.userPlant.updateUserPlantByName(uid, plantName, 0)
        else:
            if name not in plant:
                return f"出售作物{name}出错：仓库中不存在该作物"
            available = plant[name]
            sellAmount = available if isAll else min(available, num)
            if sellAmount <= 0:
                return f"出售作物{name}出错：数量不足"
            await g_pDBService.userPlant.updateUserPlantByName(
                uid, name, available - sellAmount
            )
            totalSold = sellAmount

        if name == "":
            totalPoint = point
        else:
            plantInfo = await g_pDBService.plant.getPlantByName(name)
            if not plantInfo:
                price = 0
            else:
                price = plantInfo["price"]

            totalPoint = totalSold * price

        currentPoint = await g_pDBService.user.getUserPointByUid(uid)
        await g_pDBService.user.updateUserPointByUid(uid, currentPoint + totalPoint)

        if name == "":
            return f"成功出售所有作物，获得农场币：{totalPoint}，当前农场币：{currentPoint + totalPoint}"
        else:
            return f"成功出售{name}，获得农场币：{totalPoint}，当前农场币：{currentPoint + totalPoint}"


g_pShopManager = CShopManager()
