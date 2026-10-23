"""QQ/OneBot头像读取；固定来源、有界缓存和可关闭的异步请求。"""

import asyncio
from collections import OrderedDict
import logging
import re
from time import monotonic

import aiohttp


logger = logging.getLogger(__name__)
MAX_BYTES = 2 * 1024 * 1024
MAX_ENTRIES = 16
FETCH_TIMEOUT = 2


async def download_avatar(user_id):
    """只访问固定腾讯HTTPS端点，不跟随重定向或读取用户提供的URL。"""
    if not re.fullmatch(r'[0-9]{1,20}', user_id):
        return None
    url = f'https://q1.qlogo.cn/g?b=qq&nk={user_id}&s=100'
    timeout = aiohttp.ClientTimeout(total=FETCH_TIMEOUT)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url, allow_redirects=False) as response:
            response.raise_for_status()
            if response.status != 200:
                return None
            if (response.content_length is not None
                    and response.content_length > MAX_BYTES):
                return None
            content = bytearray()
            async for chunk in response.content.iter_chunked(65536):
                if len(content) + len(chunk) > MAX_BYTES:
                    return None
                content.extend(chunk)
            return bytes(content) or None


class AvatarCache:
    """单事件循环使用；缓存最多16项，同一QQ的并发请求共享下载。"""

    def __init__(self):
        self._cache = OrderedDict()
        self._pending = {}
        self._closed = False

    async def get(self, platform, user_id):
        user_id = str(user_id)
        if (self._closed or platform != 'aiocqhttp'
                or not re.fullmatch(r'[0-9]{1,20}', user_id)):
            return None
        cached = self._cache.get(user_id)
        if cached and cached[0] > monotonic():
            self._cache.move_to_end(user_id)
            return cached[1]
        task = self._pending.get(user_id)
        if task is None:
            if len(self._pending) >= MAX_ENTRIES:
                return None
            task = asyncio.create_task(self._fetch(user_id))
            self._pending[user_id] = task
        return await asyncio.shield(task)

    async def _fetch(self, user_id):
        try:
            content = await asyncio.wait_for(
                download_avatar(user_id), timeout=FETCH_TIMEOUT,
            )
            if (not isinstance(content, bytes) or not content
                    or len(content) > MAX_BYTES):
                content = None
        except Exception:
            # 不记录QQ号、完整URL和异常中的潜在身份信息。
            logger.warning('farm astrbot avatar unavailable; using default')
            content = None
        finally:
            self._pending.pop(user_id, None)
        self._cache[user_id] = (
            monotonic() + (300 if content else 30), content,
        )
        self._cache.move_to_end(user_id)
        while len(self._cache) > MAX_ENTRIES:
            self._cache.popitem(last=False)
        return content

    async def close(self):
        self._closed = True
        tasks = list(self._pending.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._cache.clear()
