import os
from datetime import datetime
from zoneinfo import ZoneInfo

from astrbot.api import logger


from .zhenxun_utils.http_utils import AsyncHttpx


class CToolManager:
    @classmethod
    def sanitize_username(cls, username: str, max_length: int = 15) -> str:
        """
        安全处理用户名
        功能：
        1. 移除首尾空白
        2. 过滤危险字符
        3. 转义单引号
        4. 处理空值
        5. 限制长度
        """
        # 处理空值
        if not username:
            return "神秘农夫"

        # 基础清洗
        cleaned = username.strip()

        # 允许的字符白名单（可自定义扩展）
        # fmt: off
        safe_chars = {
            "_", "-", "!", "@", "#", "$", "%", "^", "&", "*", "(", ")",
            "+", "=", ".", ",", "~", "·", " ",
            "a","b","c","d","e","f","g","h","i","j","k","l","m",
            "n","o","p","q","r","s","t","u","v","w","x","y","z",
            "A","B","C","D","E","F","G","H","I","J","K","L","M",
            "N","O","P","Q","R","S","T","U","V","W","X","Y","Z",
            "0","1","2","3","4","5","6","7","8","9",
        }
        # fmt: on
        # 添加常用中文字符（Unicode范围）
        safe_chars.update(chr(c) for c in range(0x4E00, 0x9FFF + 1))

        # 过滤危险字符
        filtered = [
            c if c in safe_chars or 0x4E00 <= ord(c) <= 0x9FFF else "" for c in cleaned
        ]

        # 合并处理结果
        safe_str = "".join(filtered)

        # 转义单引号（双重保障）
        escaped = safe_str.replace("'", "''")

        # 处理空结果
        if not escaped:
            return "神秘农夫"

        # 长度限制
        return escaped[:max_length]

    @classmethod
    async def get_user_avatar(cls, uid: str) -> bytes | None:
        """快捷获取用户头像

        Args:
            uid: 用户id
        """
        url = None

        if uid.isdigit():
            url = f"http://q1.qlogo.cn/g?b=qq&nk={uid}&s=160"

        return await AsyncHttpx.get_content(url) if url else None

    @classmethod
    def renameFile(cls, currentFilePath: str, newFileName: str) -> bool:
        """重命名文件，如果目标文件名已存在则先删除再重命名

        Args:
            currentFilePath (str): 当前文件的完整路径
            newFileName (str): 重命名后的文件名

        Returns:
            bool: 重命名成功返回 True，否则返回 False
        """
        try:
            dirPath = os.path.dirname(currentFilePath)
            newFilePath = os.path.join(dirPath, newFileName)

            if os.path.exists(newFilePath):
                os.remove(newFilePath)

            os.rename(currentFilePath, newFilePath)
            return True
        except Exception as e:
            logger.warning(f"文件重命名失败: {e}")
            return False

    @classmethod
    def dateTime(cls) -> datetime:
        tz = ZoneInfo("Asia/Shanghai")
        return datetime.now(tz)


g_pToolManager = CToolManager()
