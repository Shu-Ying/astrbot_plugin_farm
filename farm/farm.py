import math
import random
from typing import List

from astrbot.api import logger

from ..cfg import g_pConfigManager
from ..dbService import g_pDBService
from ..event.event import g_pEventManager
from ..json import g_pJsonManager
from ..tool import g_pToolManager
from ..zhenxun_utils._build_image import BuildImage
from ..zhenxun_utils.image_utils import ImageTemplate


class CFarmManager:
    @classmethod
    async def drawFarmByUid(cls, uid: str) -> str:
        """绘制用户农场

        Args:
            uid (str): 用户UID

        Returns:
            str: 返回绘制图片base64
        """
        img = BuildImage(
            background=g_pConfigManager.sResourcePath / "background/background.jpg"
        )

        soilSize = g_pJsonManager.m_pSoil["size"]

        grass = BuildImage(
            background=g_pConfigManager.sResourcePath / "soil/草土地.png"
        )
        await grass.resize(0, soilSize[0], soilSize[1])

        soilPos = g_pJsonManager.m_pSoil["soil"]

        userInfo = await g_pDBService.user.getUserInfoByUid(uid)
        soilUnlock = int(userInfo["soil"])

        x = 0
        y = 0
        isFirstExpansion = True  # 首次添加扩建图片
        isFirstRipe = True
        plant = None
        for index in range(0, 30):
            x = soilPos[str(index + 1)]["x"]
            y = soilPos[str(index + 1)]["y"]

            # 如果土地已经到达对应等级
            if index < soilUnlock:
                soilUrl = ""
                # TODO 缺少判断用户土地资源状况
                soilInfo = await g_pDBService.userSoil.getUserSoil(uid, index + 1)

                if not soilInfo:
                    soilUrl = "soil/普通土地.png"
                else:
                    soilLevel = soilInfo.get("soilLevel", 0)

                    if soilLevel == 1:
                        soilUrl = "soil/红土地.png"
                    elif soilLevel == 2:
                        soilUrl = "soil/黑土地.png"
                    elif soilLevel == 3:
                        soilUrl = "soil/金土地.png"
                    else:
                        soilUrl = "soil/普通土地.png"

                soil = BuildImage(background=g_pConfigManager.sResourcePath / soilUrl)
                await soil.resize(0, soilSize[0], soilSize[1])

                await img.paste(soil, (x, y))

                isPlant, plant, isRipe, offsetX, offsetY = await cls.drawSoilPlant(
                    uid, index + 1
                )

                if isPlant:
                    await img.paste(
                        plant,
                        (
                            x + soilSize[0] // 2 - plant.width // 2 + offsetX,
                            y + soilSize[1] // 2 - plant.height // 2 + offsetY,
                        ),
                    )

                # 1700 275
                # 首次添加可收获图片
                if isRipe and isFirstRipe:
                    ripe = BuildImage(
                        background=g_pConfigManager.sResourcePath
                        / "background/ripe.png"
                    )

                    await img.paste(
                        ripe,
                        (x + soilSize[0] // 2 - ripe.width // 2, y - ripe.height // 2),
                    )

                    isFirstRipe = False
            else:
                await img.paste(grass, (x, y))

                if isFirstExpansion:
                    isFirstExpansion = False

                    # 首次添加扩建图片
                    expansion = BuildImage(
                        background=g_pConfigManager.sResourcePath
                        / "background/expansion.png"
                    )
                    await expansion.resize(0, 69, 69)
                    await img.paste(
                        expansion,
                        (
                            x + soilSize[0] // 2 - expansion.width // 2,
                            y + soilSize[1] // 2 - expansion.height,
                        ),
                    )

        # 左上角绘制用户信息
        # 头像
        image = await g_pToolManager.get_user_avatar(uid)

        if image:
            avatar = BuildImage(background=image)

            await img.paste(avatar, (125, 85))

        # 头像框
        frame = BuildImage(
            background=g_pConfigManager.sResourcePath / "background/frame.png"
        )
        await img.paste(frame, (75, 44))

        # 用户名
        nameImg = await BuildImage.build_text_image(
            userInfo["name"], size=24, font_color=(77, 35, 4)
        )
        await img.paste(nameImg, (300, 92))

        # 经验值
        level = await g_pDBService.user.getUserLevelByUid(uid)

        beginX = 309
        endX = 627
        # 绘制宽度计算公式为 (当前经验值 / 经验值上限) * 宽度
        width = int((level[2] / level[1]) * (endX - beginX))
        await img.rectangle((beginX, 188, beginX + width, 222), (171, 194, 41))

        expImg = await BuildImage.build_text_image(
            f"{level[2]} / {level[1]}", size=24, font_color=(102, 120, 19)
        )
        await img.paste(expImg, (390, 193))

        # 等级
        levelImg = await BuildImage.build_text_image(
            str(level[0]), size=32, font_color=(214, 111, 1)
        )
        await img.paste(levelImg, (660, 187))

        # 金币
        pointImg = await BuildImage.build_text_image(
            str(userInfo["point"]), size=24, font_color=(253, 253, 253)
        )
        await img.paste(pointImg, (330, 255))

        # 点券 TODO
        bondsImg = await BuildImage.build_text_image(
            "0", size=24, font_color=(253, 253, 253)
        )
        await img.paste(bondsImg, (570, 255))

        # 清晰度
        definition = g_pConfigManager.sFarmDrawQuality
        if definition == "medium":
            await img.resize(0.6)
        elif definition == "hight":
            await img.resize(0.8)
        elif definition == "original":
            pass
        else:
            await img.resize(0.4)

        return img.pic2base64()

    @classmethod
    async def drawDetailFarmByUid(cls, uid: str) -> list:
        info = []

        farm = await cls.drawFarmByUid(uid)

        info.append(farm)

        dataList = []
        columnName = [
            "-",
            "土地ID",
            "土地等级",
            "作物名称",
            "成熟时间",
            "土地状态",
            "被偷数量",
            "剩余产出",
        ]

        icon = ""
        soilNumber = await g_pDBService.user.getUserSoilByUid(uid)

        for i in range(1, soilNumber + 1):
            soilInfo = await g_pDBService.userSoil.getUserSoil(uid, i)

            if soilInfo:
                match soilInfo.get("soilLevel", 0):
                    case 1:
                        name = "红土地.png"
                    case 2:
                        name = "黑土地.png"
                    case 3:
                        name = "金土地.png"
                    case _:
                        name = "普通土地.png"
                iconPath = g_pConfigManager.sResourcePath / "soil" / name

                if iconPath.exists():
                    icon = (iconPath, 33, 33)

                plantName = soilInfo.get("plantName", "-")

                if plantName == "-":
                    matureTime = "-"
                    soilStatus = "-"
                    totalNumber = "-"
                    plantNumber = "-"
                else:
                    matureTime = (
                        g_pToolManager.dateTime()
                        .fromtimestamp(int(soilInfo.get("matureTime", 0)))
                        .strftime("%Y-%m-%d %H:%M:%S")
                    )
                    soilStatus = await g_pDBService.userSoil.getUserSoilStatus(uid, i)

                    totalNumber = await g_pDBService.userSteal.getTotalStolenCount(
                        uid, i
                    )
                    planInfo = await g_pDBService.plant.getPlantByName(plantName)

                    if not planInfo:
                        plantNumber = "None"
                    else:
                        plantNumber = f"{planInfo['harvest'] - totalNumber}"

                dataList.append(
                    [
                        icon,
                        i,
                        await g_pDBService.userSoil.getSoilLevelText(
                            soilInfo["soilLevel"]
                        ),
                        plantName,
                        matureTime,
                        soilStatus,
                        totalNumber,
                        plantNumber,
                    ]
                )

                if len(dataList) >= 15:
                    result = await ImageTemplate.table_page(
                        "土地详细信息",
                        "",
                        columnName,
                        dataList,
                    )

                    info.append(result.pic2base64())
                    dataList.clear()

            if i >= soilNumber:
                result = await ImageTemplate.table_page(
                    "土地详细信息",
                    "",
                    columnName,
                    dataList,
                )

                info.append(result.pic2base64())
                dataList.clear()

        return info

    @classmethod
    async def drawSoilPlant(
        cls, uid: str, soilIndex: int
    ) -> tuple[bool, BuildImage, bool, int, int]:
        """绘制植物资源

        Args:
            uid (str): 用户Uid
            soilIndex (int): 土地索引 从1开始

        Returns:
            tuple[bool, BuildImage]: [绘制是否成功，资源图片, 是否成熟]
        """

        plant = None
        soilInfo = await g_pDBService.userSoil.getUserSoil(uid, soilIndex)

        if not soilInfo:
            return False, None, False, 0, 0  # type: ignore

        # 是否枯萎
        if int(soilInfo.get("wiltStatus", 0)) == 1:
            plant = BuildImage(
                background=g_pConfigManager.sResourcePath / "plant/basic/9.png"
            )
            await plant.resize(0, 150, 212)
            return True, plant, False, 0, 0

        # 获取作物详细信息
        plantInfo = await g_pDBService.plant.getPlantByName(soilInfo["plantName"])
        if not plantInfo:
            logger.error(f"绘制植物资源失败: {soilInfo['plantName']}")
            return False, None, False, 0, 0  # type: ignore

        offsetX = plantInfo.get("officX", 0)
        offsetY = plantInfo.get("officY", 0)
        offsetW = plantInfo.get("officW", 0)
        offsetH = plantInfo.get("officH", 0)

        currentTime = g_pToolManager.dateTime().now().timestamp()
        phaseList = await g_pDBService.plant.getPlantPhaseByName(soilInfo["plantName"])

        # 如果当前时间大于成熟时间 说明作物成熟
        if currentTime >= soilInfo["matureTime"]:
            plant = BuildImage(
                background=g_pConfigManager.sResourcePath
                / f"plant/{soilInfo['plantName']}/{len(phaseList)}.png"
            )

            return True, plant, True, offsetX, offsetY
        else:
            # 如果是多阶段作物 且没有成熟 #早期思路 多阶段作物 直接是倒数第二阶段图片
            # if soilInfo["harvestCount"] >= 1:
            #     plant = BuildImage(
            #         background=g_sResourcePath
            #         / f"plant/{soilInfo['plantName']}/{plantInfo['phase'] - 1}.png"
            #     )

            #     return True, plant, False, offsetX, offsetY

            # 如果没有成熟 则根据当前阶段进行绘制
            elapsedTime = currentTime - soilInfo["plantTime"]
            currentStage = sum(1 for thr in phaseList if elapsedTime >= thr)

            if currentStage <= 0:
                if not plantInfo.get("general", False):
                    plant = BuildImage(
                        background=g_pConfigManager.sResourcePath
                        / f"plant/{soilInfo['plantName']}/0.png"
                    )
                else:
                    plant = BuildImage(
                        background=g_pConfigManager.sResourcePath / "plant/basic/0.png"
                    )

                await plant.resize(0, 35 + offsetW, 58 + offsetH)
            else:
                plant = BuildImage(
                    background=g_pConfigManager.sResourcePath
                    / f"plant/{soilInfo['plantName']}/{currentStage}.png"
                )

        return True, plant, False, offsetX, offsetY

    @classmethod
    async def getUserSeedByUid(cls, uid: str) -> str:
        """获取用户种子仓库"""
        dataList = []
        columnNames = [
            "-",
            "种子名称",
            "数量",
            "收获经验",
            "收获数量",
            "成熟时间（小时）",
            "收获次数",
            "是否可以上架交易行",
        ]

        # 从数据库获取结构化数据
        seedRecords = await g_pDBService.userSeed.getUserSeedByUid(uid) or {}

        if not seedRecords:
            result = await ImageTemplate.table_page(
                "种子仓库",
                "播种示例：@小真寻 播种 大白菜 [数量]",
                columnNames,
                dataList,
            )
            return result.pic2base64()

        for seedName, count in seedRecords.items():
            try:
                plantInfo = await g_pDBService.plant.getPlantByName(seedName)
                if not plantInfo:
                    continue

                iconPath = g_pConfigManager.sResourcePath / f"plant/{seedName}/icon.png"
                icon = (iconPath, 33, 33) if iconPath.exists() else ""
                sellable = "可以" if plantInfo["sell"] else "不可以"

                dataList.append(
                    [
                        icon,
                        seedName,
                        count,
                        plantInfo["experience"],
                        plantInfo["harvest"],
                        plantInfo["time"],
                        plantInfo["crop"],
                        sellable,
                    ]
                )
            except KeyError:
                continue

        result = await ImageTemplate.table_page(
            "种子仓库",
            "播种示例：@小真寻 播种 大白菜 [数量]",
            columnNames,
            dataList,
        )
        return result.pic2base64()

    @classmethod
    async def sowing(cls, uid: str, name: str, num: int = -1) -> str:
        """播种

        Args:
            uid (str): 用户Uid
            name (str): 播种种子名称
            num (int, optional): 播种数量

        Returns:
            str: 返回结果
        """
        try:
            # 获取用户的种子数量
            count = await g_pDBService.userSeed.getUserSeedByName(uid, name)
            if count is None:
                count = 0  # 如果返回 None，则视为没有种子

            if count <= 0:
                return g_pConfigManager.sTranslation["sowing"]["noSeed"].format(
                    name=name
                )

            # 如果播种数量超过仓库种子数量
            if count < num and num != -1:
                return g_pConfigManager.sTranslation["sowing"]["noNum"].format(
                    name=name, num=count
                )

            # 获取用户土地数量
            soilNumber = await g_pDBService.user.getUserSoilByUid(uid)

            # 如果播种数量为 -1，表示播种所有可播种的土地
            if num == -1:
                num = count

            # 发送播种前信号
            await g_pEventManager.m_beforePlant.emit(uid=uid, name=name, num=num)  # type: ignore

            # 记录是否成功播种
            successCount = 0
            for i in range(1, soilNumber + 1):
                if count > 0 and num > 0:
                    success = await g_pDBService.userSoil.sowingByPlantName(
                        uid, i, name
                    )
                    if success:
                        # 更新种子数量
                        num -= 1
                        count -= 1

                        # 记录种子消耗数量
                        successCount += 1

                        # 发送播种后信号
                        await g_pEventManager.m_afterPlant.emit(  # type: ignore
                            uid=uid, name=name, soilIndex=i
                        )

            # 确保用户仓库数量更新
            if successCount > 0:
                await g_pDBService.userSeed.updateUserSeedByName(uid, name, count)

            # 根据播种结果给出反馈
            if num == 0:
                return g_pConfigManager.sTranslation["sowing"]["success"].format(
                    name=name, num=count
                )
            else:
                return g_pConfigManager.sTranslation["sowing"]["success2"].format(
                    name=name, num=count
                )

        except Exception as e:
            logger.warning("播种操作失败！", e=e)
            return g_pConfigManager.sTranslation["sowing"]["error"]

    @classmethod
    async def harvest(cls, uid: str) -> str:
        """收获作物

        Args:
            uid (str): 用户Uid

        Returns:
            str: 返回
        """
        try:
            await g_pEventManager.m_beforeHarvest.emit(uid=uid)  # type: ignore

            soilNumber = await g_pDBService.user.getUserSoilByUid(uid)

            harvestRecords = []  # 收获日志记录
            experience = 0  # 总经验值
            harvestCount = 0  # 成功收获数量

            for i in range(1, soilNumber + 1):
                soilInfo = await g_pDBService.userSoil.getUserSoil(uid, i)
                if not soilInfo:
                    continue

                # 如果没有种植
                if soilInfo.get("isSoilPlanted", 1) == 0:
                    continue

                level = soilInfo.get("soilLevel", 0)

                # 如果是枯萎状态
                if soilInfo.get("wiltStatus", 1) == 1:
                    continue

                plantInfo = await g_pDBService.plant.getPlantByName(
                    soilInfo["plantName"]
                )
                if not plantInfo:
                    continue

                currentTime = g_pToolManager.dateTime().now()
                matureTime = g_pToolManager.dateTime().fromtimestamp(
                    int(soilInfo["matureTime"])
                )

                if currentTime >= matureTime:
                    number = plantInfo["harvest"]

                    # 处理偷菜扣除数量
                    stealNum = await g_pDBService.userSteal.getTotalStolenCount(uid, i)
                    number -= stealNum

                    # 处理土地等级带来的数量增长 向下取整
                    percent = await g_pDBService.userSoil.getSoilLevelHarvestNumber(
                        level
                    )
                    number = math.floor(number * (100 + percent) // 100)

                    if number <= 0:
                        continue

                    harvestCount += 1
                    experience += plantInfo["experience"]

                    # 处理土地等级带来的经验增长 向下取整
                    percent = await g_pDBService.userSoil.getSoilLevelHarvestExp(level)
                    experience = math.floor(experience * (100 + percent) // 100)

                    harvestRecords.append(
                        g_pConfigManager.sTranslation["harvest"]["append"].format(
                            name=soilInfo["plantName"],
                            num=number,
                            exp=plantInfo["experience"],
                        )
                    )

                    await g_pDBService.userPlant.addUserPlantByUid(
                        uid, soilInfo["plantName"], number
                    )

                    # 如果到达收获次数上限
                    if soilInfo["harvestCount"] + 1 >= plantInfo["crop"]:
                        await g_pDBService.userSoil.updateUserSoil(
                            uid, i, "wiltStatus", 1
                        )
                    else:
                        phase = await g_pDBService.plant.getPlantPhaseByName(
                            soilInfo["plantName"]
                        )

                        ts, hc = (
                            int(currentTime.timestamp()),
                            soilInfo["harvestCount"] + 1,
                        )
                        p1, p2, *rest = phase

                        await g_pDBService.userSoil.updateUserSoilFields(
                            uid,
                            i,
                            {
                                "harvestCount": hc,
                                "plantTime": ts - p1 - p2,
                                "matureTime": ts + p2 + sum(rest),
                            },
                        )

                    await g_pEventManager.m_afterHarvest.emit(  # type: ignore
                        uid=uid, name=soilInfo["plantName"], num=number, soilIndex=i
                    )

            if experience > 0:
                exp = await g_pDBService.user.getUserExpByUid(uid)
                await g_pDBService.user.updateUserExpByUid(uid, exp + experience)
                harvestRecords.append(
                    g_pConfigManager.sTranslation["harvest"]["exp"].format(
                        exp=experience,
                    )
                )

            if harvestCount <= 0:
                return g_pConfigManager.sTranslation["harvest"]["no"]
            else:
                return "\n".join(harvestRecords)

        except Exception as e:
            logger.warning("收获操作失败！", e=e)
            return g_pConfigManager.sTranslation["harvest"]["error"]

    @classmethod
    async def eradicate(cls, uid: str) -> str:
        """铲除作物
        TODO 缺少随意铲除作物 目前只能铲除荒废作物
        Args:
            uid (str): 用户Uid

        Returns:
            str: 返回
        """
        soilNumber = await g_pDBService.user.getUserSoilByUid(uid)

        await g_pEventManager.m_beforeEradicate.emit(uid=uid)  # type: ignore

        experience = 0
        for i in range(1, soilNumber + 1):
            soilInfo = await g_pDBService.userSoil.getUserSoil(uid, i)
            if not soilInfo:
                continue

            # 如果没有种植
            if soilInfo.get("isSoilPlanted", 1) == 0:
                continue

            # 如果不是枯萎状态
            if soilInfo.get("wiltStatus", 0) == 0:
                continue

            experience += 3

            if g_pConfigManager.bIsDebug:
                experience += 999

            # 更新数据库操作
            await g_pDBService.userSoil.deleteUserSoil(uid, i)

            await g_pDBService.userSoil.updateUserSoilFields(
                uid,
                i,
                {
                    "plantName": "",
                    "plantTime": 0,
                    "matureTime": 0,
                    "wiltStatus": 0,
                    "isSoilPlanted": 0,
                },
            )

            # 铲除作物会将偷菜记录清空
            await g_pDBService.userSteal.deleteStealRecord(uid, i)

            await g_pEventManager.m_afterEradicate.emit(uid=uid, soilIndex=i)  # type: ignore

        if experience > 0:
            exp = await g_pDBService.user.getUserExpByUid(uid)
            await g_pDBService.user.updateUserExpByUid(uid, exp + experience)

            return g_pConfigManager.sTranslation["eradicate"]["success"].format(
                exp=experience
            )
        else:
            return g_pConfigManager.sTranslation["eradicate"]["error"]

    @classmethod
    async def getUserPlantByUid(cls, uid: str) -> str:
        """获取用户作物仓库

        Args:
            uid (str): 用户Uid

        Returns:
            str: 返回图片
        """
        data_list = []
        column_name = ["-", "作物名称", "数量", "单价", "总价", "是否可以上架交易行"]

        plant = await g_pDBService.userPlant.getUserPlantByUid(uid)

        if plant is None:
            result = await ImageTemplate.table_page(
                "作物仓库",
                "出售示例：@小真寻 出售作物 大白菜 [数量]",
                column_name,
                data_list,
            )
            return result.pic2base64()

        sell = ""
        for name, count in plant.items():
            plantInfo = await g_pDBService.plant.getPlantByName(name)
            if not plantInfo:
                continue

            icon = ""
            icon_path = g_pConfigManager.sResourcePath / f"plant/{name}/icon.png"
            if icon_path.exists():
                icon = (icon_path, 33, 33)

            if not plantInfo.get("sell", False):
                sell = "可以"
            else:
                sell = "不可以"

            number = int(count) * plantInfo["price"]

            data_list.append([icon, name, count, plantInfo["price"], number, sell])

        result = await ImageTemplate.table_page(
            "作物仓库",
            "出售示例：@小真寻 出售作物 大白菜 [数量]",
            column_name,
            data_list,
        )

        return result.pic2base64()

    @classmethod
    async def stealing(cls, uid: str, target: str) -> str:
        """偷菜

        Args:
            uid (str): 用户Uid
            target (str): 被偷用户Uid

        Returns:
            str: 返回
        """
        # 用户信息
        userInfo = await g_pDBService.user.getUserInfoByUid(uid)

        stealTime = userInfo.get("stealTime", "")
        stealCount = int(userInfo["stealCount"])

        if stealTime == "" or not stealTime:
            stealTime = g_pToolManager.dateTime().date().today().strftime("%Y-%m-%d")
            stealCount = 5
        elif (
            g_pToolManager.dateTime().date().fromisoformat(stealTime)
            != g_pToolManager.dateTime().date().today()
        ):
            stealTime = g_pToolManager.dateTime().date().today().strftime("%Y-%m-%d")
            stealCount = 5

        if stealCount <= 0:
            return g_pConfigManager.sTranslation["stealing"]["max"]

        # 获取用户解锁地块数量
        soilNumber = await g_pDBService.user.getUserSoilByUid(target)
        harvestRecords: List[str] = []
        isStealingNumber = 0
        isStealingPlant = 0

        for i in range(1, soilNumber + 1):
            soilInfo = await g_pDBService.userSoil.getUserSoil(target, i)
            if not soilInfo:
                continue

            # 如果没有种植
            if soilInfo.get("isSoilPlanted", 1) == 0:
                continue

            # 如果是枯萎状态
            if soilInfo.get("wiltStatus", 1) == 1:
                continue

            # 作物信息
            plantInfo = await g_pDBService.plant.getPlantByName(soilInfo["plantName"])
            if not plantInfo:
                continue

            currentTime = g_pToolManager.dateTime().now()
            matureTime = g_pToolManager.dateTime().fromtimestamp(
                int(soilInfo["matureTime"])
            )

            if currentTime >= matureTime:
                # 如果偷过，则跳过该土地
                if await g_pDBService.userSteal.hasStealed(target, i, uid):
                    isStealingNumber += 1
                    continue

                stealingNumber = plantInfo[
                    "harvest"
                ] - await g_pDBService.userSteal.getTotalStolenCount(target, i)
                randomNumber = random.choice([1, 2])
                randomNumber = min(randomNumber, stealingNumber)

                if randomNumber > 0:
                    await g_pDBService.userPlant.addUserPlantByUid(
                        uid, soilInfo["plantName"], randomNumber
                    )

                    harvestRecords.append(
                        g_pConfigManager.sTranslation["stealing"]["info"].format(
                            name=soilInfo["plantName"], num=randomNumber
                        )
                    )

                    isStealingPlant += 1

                    # 如果将作物偷完，就直接更新状态 并记录用户偷取过
                    if plantInfo["harvest"] - randomNumber + stealingNumber == 0:
                        # 如果作物 是最后一阶段作物且偷完 则直接枯萎
                        if soilInfo["harvestCount"] + 1 >= plantInfo["crop"]:
                            await g_pDBService.userSoil.updateUserSoil(
                                target, i, "wiltStatus", 1
                            )
                        else:
                            phase = await g_pDBService.plant.getPlantPhaseByName(
                                soilInfo["plantName"]
                            )

                            ts, hc = (
                                int(currentTime.timestamp()),
                                soilInfo["harvestCount"] + 1,
                            )
                            p1, p2, *rest = phase

                            await g_pDBService.userSoil.updateUserSoilFields(
                                uid,
                                i,
                                {
                                    "harvestCount": hc,
                                    "plantTime": ts - p1 - p2,
                                    "matureTime": ts + p2 + sum(rest),
                                },
                            )

                            await g_pDBService.userSteal.addStealRecord(
                                target,
                                i,
                                uid,
                                randomNumber,
                                int(g_pToolManager.dateTime().now().timestamp()),
                            )

                    else:
                        await g_pDBService.userSteal.addStealRecord(
                            target,
                            i,
                            uid,
                            randomNumber,
                            int(g_pToolManager.dateTime().now().timestamp()),
                        )

        if isStealingPlant <= 0 and isStealingNumber <= 0:
            return g_pConfigManager.sTranslation["stealing"]["noPlant"]
        elif isStealingPlant <= 0 and isStealingNumber > 0:
            return g_pConfigManager.sTranslation["stealing"]["repeat"]
        else:
            stealCount -= 1

            await g_pDBService.user.updateStealCountByUid(uid, stealTime, stealCount)

            return "\n".join(harvestRecords)

    @classmethod
    async def reclamationCondition(cls, uid: str) -> str:
        """获取开垦条件

        Args:
            uid (str): 用户Uid

        Returns:
            str: 返回条件文本信息
        """
        userInfo = await g_pDBService.user.getUserInfoByUid(uid)
        rec = g_pJsonManager.m_pLevel["reclamation"]

        try:
            if userInfo["soil"] >= 30:
                return g_pConfigManager.sTranslation["reclamation"]["perfect"]

            rec = rec[f"{userInfo['soil'] + 1}"]

            level = rec["level"]
            point = rec["point"]
            item = rec["item"]

            str = ""
            if len(item) == 0:
                str = g_pConfigManager.sTranslation["reclamation"]["next"].format(
                    level=level, num=point
                )
            else:
                str = g_pConfigManager.sTranslation["reclamation"]["next2"].format(
                    level=level, num=point, item=item
                )

            return str
        except Exception:
            return g_pConfigManager.sTranslation["reclamation"]["error"]

    @classmethod
    async def reclamation(cls, uid: str) -> str:
        """开垦

        Args:
            uid (str): 用户Uid

        Returns:
            str: _description_
        """
        userInfo = await g_pDBService.user.getUserInfoByUid(uid)
        level = await g_pDBService.user.getUserLevelByUid(uid)

        rec = g_pJsonManager.m_pLevel["reclamation"]

        try:
            if userInfo["soil"] >= 30:
                return g_pConfigManager.sTranslation["reclamation"]["perfect"]

            rec = rec[f"{userInfo['soil'] + 1}"]

            levelFileter = rec["level"]
            point = rec["point"]

            if level[0] < levelFileter:
                return g_pConfigManager.sTranslation["reclamation"]["nextLevel"].format(
                    level=level[0], next=levelFileter
                )

            if userInfo["point"] < point:
                return g_pConfigManager.sTranslation["reclamation"]["noNum"].format(
                    num=point
                )

            # TODO 缺少判断消耗的item
            await g_pDBService.user.updateUserPointByUid(uid, userInfo["point"] - point)
            await g_pDBService.user.updateUserSoilByUid(uid, userInfo["soil"] + 1)

            return g_pConfigManager.sTranslation["reclamation"]["success"]
        except Exception:
            return g_pConfigManager.sTranslation["reclamation"]["error1"]

    @classmethod
    async def soilUpgradeCondition(cls, uid: str, soilIndex: int) -> str:
        """获取土地升级条件

        Args:
            uid (str): 用户Uid
            soilIndex (str): 土地索引

        Returns:
            str: 返回土地升级条件
        """
        soilInfo = await g_pDBService.userSoil.getUserSoil(uid, soilIndex)

        if not soilInfo:
            return g_pConfigManager.sTranslation["soilInfo"]["error"]

        soilLevel = soilInfo.get("soilLevel", 0) + 1
        if soilLevel >= g_pConfigManager.iSoilLevelMax:
            return g_pConfigManager.sTranslation["soilInfo"]["error1"]

        # 获取用户当前土地 的下一级土地 数量
        countSoil = await g_pDBService.userSoil.countSoilByLevel(uid, soilLevel)

        # 获取升级所需
        soilLevelText = await g_pDBService.userSoil.getSoilLevel(soilLevel)
        fileter = g_pJsonManager.m_pSoil["upgrade"][soilLevelText][countSoil]

        nextLevel = await g_pDBService.userSoil.getSoilLevelText(soilLevel)

        lines = ["将土地升级至：" + nextLevel + "。", "所需："]
        fields = [
            ("level", "等级"),
            ("point", "金币"),
            ("vipPoint", "点券"),
        ]
        for key, label in fields:
            value = fileter.get(key, 0)
            if value > 0:
                lines.append(f"{label}：{value}")

        items = fileter.get("item", {})
        for name, qty in items.items():
            if qty:
                lines.append(f"{name}：{qty}")

        lines.append("回复“是”将执行升级")

        return "\n".join(lines)

    @classmethod
    async def soilUpgrade(cls, uid: str, soilIndex: int) -> str:
        """土地升级

        Args:
            uid (str): 用户Uid
            soilIndex (int): 土地索引

        Returns:
            str:
        """
        userInfo = await g_pDBService.user.getUserInfoByUid(uid)
        soilInfo = await g_pDBService.userSoil.getUserSoil(uid, soilIndex)

        if not soilInfo:
            return g_pConfigManager.sTranslation["soilInfo"]["error"].format(
                e="字面意思"
            )

        soilLevel = soilInfo.get("soilLevel", 0) + 1
        if soilLevel >= g_pConfigManager.iSoilLevelMax:
            return g_pConfigManager.sTranslation["soilInfo"]["error1"]

        countSoil = await g_pDBService.userSoil.countSoilByLevel(uid, soilLevel)

        soilLevelText = await g_pDBService.userSoil.getSoilLevel(soilLevel)
        fileter = g_pJsonManager.m_pSoil["upgrade"][soilLevelText][countSoil]

        getters = {
            "level": (await g_pDBService.user.getUserLevelByUid(uid))[0],
            "point": userInfo.get("point", 0),
            "vipPoint": userInfo.get("vipPoint", 0),
        }

        requirements = {
            "level": "等级",
            "point": "金币",
            "vipPoint": "点券",
        }

        for key, val in getters.items():
            need = fileter.get(key, 0)
            if val < need:
                return f"你的{requirements[key]}不够哦~"

        # 缺少item判断

        # 更新数据库字段
        await g_pDBService.userSoil.updateUserSoil(
            uid, soilIndex, "soilLevel", soilLevel
        )

        # 如果有作物的话直接成熟
        await g_pDBService.userSoil.matureNow(uid, soilIndex)

        # 更新数据库字段
        point = userInfo.get("point", 0) - fileter.get("point", 0)
        await g_pDBService.user.updateUserPointByUid(uid, point)

        vipPoint = userInfo.get("vipPoint", 0) - fileter.get("vipPoint", 0)
        await g_pDBService.user.updateUserVipPointByUid(uid, vipPoint)

        return g_pConfigManager.sTranslation["soilInfo"]["success"].format(
            name=await g_pDBService.userSoil.getSoilLevelText(soilLevel),
            text=g_pConfigManager.sTranslation["soilInfo"][soilLevelText],
        )


g_pFarmManager = CFarmManager()
