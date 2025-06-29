import json
import os

import httpx
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

from astrbot.api import logger

from .cfg import g_pConfigManager
from .dbService import g_pDBService
from .tool import g_pToolManager


class CRequestManager:
    m_sTokens = "xZ%?z5LtWV7H:0-Xnwp+bNRNQ-jbfrxG"

    @classmethod
    async def download(
        cls,
        url: str,
        savePath: str,
        fileName: str,
        params: dict | None = None,
        jsonData: dict | None = None,
    ) -> bool:
        """下载文件到指定路径并覆盖已存在的文件

        Args:
            url (str): 文件的下载链接
            savePath (str): 保存文件夹路径
            fileName (str): 保存后的文件名
            params (dict | None): 可选的 URL 查询参数
            jsonData (dict | None): 可选的 JSON 请求体

        Returns:
            bool: 是否下载成功
        """
        headers = {"token": cls.m_sTokens}

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                requestArgs: dict = {"headers": headers}
                if params:
                    requestArgs["params"] = params
                if jsonData:
                    requestArgs["json"] = jsonData

                response = await client.request(
                    "GET", url, **requestArgs, follow_redirects=True
                )

                if response.status_code != 200:
                    logger.warning(
                        f"文件下载失败: HTTP {response.status_code} {response.text}"
                    )
                    return False

                totalLength = int(response.headers.get("Content-Length", 0))
                fullPath = os.path.join(savePath, fileName)
                os.makedirs(os.path.dirname(fullPath), exist_ok=True)

                with Progress(
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    DownloadColumn(),
                    TransferSpeedColumn(),
                    TimeRemainingColumn(),
                    transient=True,
                ) as progress:
                    task = progress.add_task(
                        f"[green]【真寻农场】正在下载 {fileName}", total=totalLength
                    )

                    with open(fullPath, "wb") as f:
                        async for chunk in response.aiter_bytes(chunk_size=1024):
                            f.write(chunk)
                            progress.advance(task, len(chunk))

                return True

        except Exception as e:
            logger.warning(f"下载文件异常: {e}")
            return False

    @classmethod
    async def post(cls, endpoint: str, name: str = "", jsonData: dict = {}) -> dict:
        """发送POST请求到指定接口，统一调用，仅支持JSON格式数据

        Args:
            endpoint (str): 请求的接口路径
            name (str, optional): 操作名称用于日志记录
            jsonData (dict): 以JSON格式发送的数据

        Raises:
            ValueError: 当jsonData未提供时抛出

        Returns:
            dict: 返回请求结果的JSON数据
        """
        baseUrl = g_pConfigManager.sFarmServerUrl
        url = f"{baseUrl.rstrip('/')}:8998/{endpoint.lstrip('/')}"
        headers = {"token": cls.m_sTokens}

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(url, json=jsonData, headers=headers)

                if response.status_code == 200:
                    return response.json()
                else:
                    logger.warning(
                        f"{name}请求失败: HTTP {response.status_code} {response.text}"
                    )
                    return {}
        except httpx.RequestError as e:
            logger.warning(f"{name}请求异常", e=e)
            return {}
        except Exception as e:
            logger.warning(f"{name}处理异常", e=e)
            return {}

    @classmethod
    async def get(cls, endpoint: str, name: str = "") -> dict:
        """发送GET请求到指定接口，统一调用，仅支持无体的查询

        Args:
            endpoint (str): 请求的接口路径
            name (str, optional): 操作名称用于日志记录

        Returns:
            dict: 返回请求结果的JSON数据
        """
        baseUrl = g_pConfigManager.sFarmServerUrl
        url = f"{baseUrl.rstrip('/')}:8998/{endpoint.lstrip('/')}"
        headers = {"token": cls.m_sTokens}

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(url, headers=headers)

                if response.status_code == 200:
                    return response.json()
                else:
                    logger.warning(
                        f"{name}请求失败: HTTP {response.status_code} {response.text}"
                    )
                    return {}
        except httpx.RequestError as e:
            logger.warning(f"{name}请求异常", e=e)
            return {}
        except Exception as e:
            logger.warning(f"{name}处理异常", e=e)
            return {}

    @classmethod
    async def initSignInFile(cls) -> bool:
        if os.path.exists(g_pConfigManager.sSignInPath):
            try:
                with open(g_pConfigManager.sSignInPath, encoding="utf-8") as f:
                    content = f.read()
                    sign = json.loads(content)

                date = sign.get("date", "")
                yearMonth = g_pToolManager.dateTime().now().strftime("%Y%m")

                if date == yearMonth:
                    logger.debug("真寻农场签到文件检查完毕")
                    return True
                else:
                    logger.warning("真寻农场签到文件检查失败, 即将下载")
                    return await cls.downloadSignInFile()
            except json.JSONDecodeError:
                logger.warning("真寻农场签到文件格式错误, 即将下载")
                return await cls.downloadSignInFile()
        else:
            return await cls.downloadSignInFile()

    @classmethod
    async def downloadSignInFile(cls) -> bool:
        try:
            baseUrl = g_pConfigManager.sFarmServerUrl

            url = f"{baseUrl.rstrip('/')}:8998/sign_in"
            path = str(g_pConfigManager.sSignInPath.parent.resolve(strict=False))
            yearMonth = g_pToolManager.dateTime().now().strftime("%Y%m")

            # 下载为 signTemp.json
            success = await cls.download(
                url=url,
                savePath=path,
                fileName="signTemp.json",
                jsonData={"date": yearMonth},
            )

            if not success:
                return False

            # 重命名为 sign_in.json
            g_pToolManager.renameFile(f"{path}/signTemp.json", "sign_in.json")
            return True
        except Exception as e:
            logger.error("下载签到文件失败", e=e)
            return False

    @classmethod
    async def initPlantDBFile(cls) -> bool:
        """检查本地 plant.db 版本，如远程版本更新则重新下载

        Returns:
            bool: 是否为最新版或成功更新
        """
        versionPath = os.path.join(
            os.path.dirname(g_pConfigManager.sPlantPath), "version.json"
        )

        try:
            with open(versionPath, encoding="utf-8") as f:
                localVersion = json.load(f).get("version", 0)
        except Exception as e:
            logger.warning(f"读取本地版本失败，默认版本为0: {e}")
            localVersion = 0

        remoteInfo = await cls.get("plant_version", name="版本检查")
        remoteVersion = remoteInfo.get("version")

        if remoteVersion is None:
            logger.warning("获取远程版本失败")
            return False

        if float(remoteVersion) <= float(localVersion):
            logger.debug("plant.db 已为最新版本")
            return True

        logger.warning(
            f"发现新版本 plant.db（远程: {remoteVersion} / 本地: {localVersion}），开始更新..."
        )

        # 先断开数据库连接
        await g_pDBService.cleanup()

        return await cls.downloadPlantDBFile(remoteVersion)

    @classmethod
    async def downloadPlantDBFile(cls, remoteVersion: float) -> bool:
        """下载最新版 plant.db 并更新本地 version.json

        Args:
            remoteVersion (float): 远程版本号

        Returns:
            bool: 是否下载并更新成功
        """
        baseUrl = g_pConfigManager.sFarmServerUrl

        savePath = os.path.dirname(g_pConfigManager.sPlantPath)
        success = await cls.download(
            url=f"{baseUrl.rstrip('/')}:8998/file/plant.db",
            savePath=savePath,
            fileName="plantTemp.db",
        )

        if not success:
            return False

        # 重命名为 sign_in.json
        g_pToolManager.renameFile(f"{savePath}/plantTemp.db", "plant.db")

        versionPath = os.path.join(savePath, "version.json")
        try:
            with open(versionPath, "w", encoding="utf-8") as f:
                json.dump({"version": remoteVersion}, f)
            logger.debug("版本文件已更新")
        except Exception as e:
            logger.warning(f"写入版本文件失败: {e}")
            return False

        await g_pDBService.plant.init()
        await g_pDBService.plant.downloadPlant()

        return True


g_pRequestManager = CRequestManager()
