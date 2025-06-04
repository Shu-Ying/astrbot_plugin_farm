import json
import os

import httpx

from astrbot.api import logger

from .cfg import g_pConfigManager
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
            async with httpx.AsyncClient(timeout=10.0) as client:
                requestArgs: dict = {"headers": headers}
                if params:
                    requestArgs["params"] = params
                if jsonData:
                    requestArgs["json"] = jsonData

                response = await client.request("GET", url, **requestArgs)

                if response.status_code == 200:
                    fullPath = os.path.join(savePath, fileName)
                    os.makedirs(os.path.dirname(fullPath), exist_ok=True)
                    with open(fullPath, "wb") as f:
                        f.write(response.content)
                    return True
                else:
                    logger.warning(
                        f"文件下载失败: HTTP {response.status_code} {response.text}"
                    )
                    return False

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
        url = f"{baseUrl.rstrip('/')}/{endpoint.lstrip('/')}"
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
        url = f"{baseUrl.rstrip('/')}/{endpoint.lstrip('/')}"
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
                with open(g_pConfigManager.sSignInPath, "r", encoding="utf-8") as f:
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

            await cls.download(url, path, "signTemp.json", jsonData={"date": yearMonth})
            g_pToolManager.renameFile(f"{path}/signTemp.json", "sign_in.json")

            return True
        except Exception as e:
            logger.error("下载签到文件失败", e=e)
            return False


g_pRequestManager = CRequestManager()
