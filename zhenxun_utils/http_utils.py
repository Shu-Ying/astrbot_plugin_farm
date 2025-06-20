import asyncio
import time
from asyncio.exceptions import TimeoutError
from pathlib import Path
from typing import Any, ClassVar

import aiofiles
import httpx
import rich
from httpx import ConnectTimeout, HTTPStatusError, Response
from astrbot.api import logger
from retrying import retry

from .user_agent import get_user_agent

# from .browser import get_browser


class AsyncHttpx:
    proxy: ClassVar[dict[str, str | None]] = {}

    @classmethod
    @retry(stop_max_attempt_number=3)
    async def get(
        cls,
        url: str | list[str],
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        cookies: dict[str, str] | None = None,
        verify: bool = True,
        use_proxy: bool = True,
        proxy: dict[str, str] | None = None,
        timeout: int = 30,
        **kwargs,
    ) -> Response:
        """Get

        参数:
            url: url
            params: params
            headers: 请求头
            cookies: cookies
            verify: verify
            use_proxy: 使用默认代理
            proxy: 指定代理
            timeout: 超时时间
        """
        urls = [url] if isinstance(url, str) else url
        return await cls._get_first_successful(
            urls,
            params=params,
            headers=headers,
            cookies=cookies,
            verify=verify,
            use_proxy=use_proxy,
            proxy=proxy,
            timeout=timeout,
            **kwargs,
        )

    @classmethod
    async def _get_first_successful(
        cls,
        urls: list[str],
        **kwargs,
    ) -> Response:
        last_exception = None
        for url in urls:
            try:
                return await cls._get_single(url, **kwargs)
            except Exception as e:
                last_exception = e
                if url != urls[-1]:
                    logger.warning(f"获取 {url} 失败, 尝试下一个")
        raise last_exception or Exception("All URLs failed")

    @classmethod
    async def _get_single(
        cls,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        cookies: dict[str, str] | None = None,
        verify: bool = True,
        use_proxy: bool = True,
        proxy: dict[str, str] | None = None,
        timeout: int = 30,
        **kwargs,
    ) -> Response:
        if not headers:
            headers = get_user_agent()
        _proxy = proxy or (cls.proxy if use_proxy else None)
        async with httpx.AsyncClient(verify=verify) as client:
            if _proxy:
                client.proxies = _proxy

            return await client.get(
                url,
                params=params,
                headers=headers,
                cookies=cookies,
                timeout=timeout,
                **kwargs,
            )

    @classmethod
    async def head(
        cls,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        cookies: dict[str, str] | None = None,
        verify: bool = True,
        use_proxy: bool = True,
        proxy: dict[str, str] | None = None,
        timeout: int = 30,
        **kwargs,
    ) -> Response:
        """Get

        参数:
            url: url
            params: params
            headers: 请求头
            cookies: cookies
            verify: verify
            use_proxy: 使用默认代理
            proxy: 指定代理
            timeout: 超时时间
        """
        if not headers:
            headers = get_user_agent()
        _proxy = proxy or (cls.proxy if use_proxy else None)
        async with httpx.AsyncClient(verify=verify) as client:
            if _proxy:
                client.proxies = _proxy

            return await client.head(
                url,
                params=params,
                headers=headers,
                cookies=cookies,
                timeout=timeout,
                **kwargs,
            )

    @classmethod
    async def post(
        cls,
        url: str,
        *,
        data: dict[str, Any] | None = None,
        content: Any = None,
        files: Any = None,
        verify: bool = True,
        use_proxy: bool = True,
        proxy: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        cookies: dict[str, str] | None = None,
        timeout: int = 30,
        **kwargs,
    ) -> Response:
        """
        说明:
            Post
        参数:
            url: url
            data: data
            content: content
            files: files
            use_proxy: 是否默认代理
            proxy: 指定代理
            json: json
            params: params
            headers: 请求头
            cookies: cookies
            timeout: 超时时间
        """
        if not headers:
            headers = get_user_agent()
        _proxy = proxy or (cls.proxy if use_proxy else None)
        async with httpx.AsyncClient(verify=verify) as client:
            if _proxy:
                client.proxies = _proxy

            return await client.post(
                url,
                content=content,
                data=data,
                files=files,
                json=json,
                params=params,
                headers=headers,
                cookies=cookies,
                timeout=timeout,
                **kwargs,
            )

    @classmethod
    async def get_content(cls, url: str, **kwargs) -> bytes | None:
        res = await cls.get(url, **kwargs)
        return res.content if res and res.status_code == 200 else None

    @classmethod
    async def download_file(
        cls,
        url: str | list[str],
        path: str | Path,
        *,
        params: dict[str, str] | None = None,
        verify: bool = True,
        use_proxy: bool = True,
        proxy: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        cookies: dict[str, str] | None = None,
        timeout: int = 30,
        stream: bool = False,
        follow_redirects: bool = True,
        **kwargs,
    ) -> bool:
        """下载文件

        参数:
            url: url
            path: 存储路径
            params: params
            verify: verify
            use_proxy: 使用代理
            proxy: 指定代理
            headers: 请求头
            cookies: cookies
            timeout: 超时时间
            stream: 是否使用流式下载（流式写入+进度条，适用于下载大文件）
        """
        if isinstance(path, str):
            path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            for _ in range(3):
                if not isinstance(url, list):
                    url = [url]
                for u in url:
                    try:
                        if not stream:
                            response = await cls.get(
                                u,
                                params=params,
                                headers=headers,
                                cookies=cookies,
                                use_proxy=use_proxy,
                                proxy=proxy,
                                timeout=timeout,
                                follow_redirects=follow_redirects,
                                **kwargs,
                            )
                            response.raise_for_status()
                            content = response.content
                            async with aiofiles.open(path, "wb") as wf:
                                await wf.write(content)
                                logger.info(f"下载 {u} 成功.. Path：{path.absolute()}")
                        else:
                            if not headers:
                                headers = get_user_agent()
                            _proxy = proxy or (cls.proxy if use_proxy else None)
                            async with httpx.AsyncClient(
                                proxies=_proxy,  # type: ignore
                                verify=verify,
                            ) as client:
                                async with client.stream(
                                    "GET",
                                    u,
                                    params=params,
                                    headers=headers,
                                    cookies=cookies,
                                    timeout=timeout,
                                    follow_redirects=True,
                                    **kwargs,
                                ) as response:
                                    response.raise_for_status()
                                    logger.info(
                                        f"开始下载 {path.name}.. "
                                        f"Path: {path.absolute()}"
                                    )
                                    async with aiofiles.open(path, "wb") as wf:
                                        total = int(
                                            response.headers.get("Content-Length", 0)
                                        )
                                        with rich.progress.Progress(  # type: ignore
                                            rich.progress.TextColumn(path.name),  # type: ignore
                                            "[progress.percentage]{task.percentage:>3.0f}%",  # type: ignore
                                            rich.progress.BarColumn(bar_width=None),  # type: ignore
                                            rich.progress.DownloadColumn(),  # type: ignore
                                            rich.progress.TransferSpeedColumn(),  # type: ignore
                                        ) as progress:
                                            download_task = progress.add_task(
                                                "Download",
                                                total=total or None,
                                            )
                                            async for chunk in response.aiter_bytes():
                                                await wf.write(chunk)
                                                await wf.flush()
                                                progress.update(
                                                    download_task,
                                                    completed=response.num_bytes_downloaded,
                                                )
                                        logger.info(
                                            f"下载 {u} 成功.. Path：{path.absolute()}"
                                        )
                        return True
                    except (TimeoutError, ConnectTimeout, HTTPStatusError):
                        logger.warning(f"下载 {u} 失败.. 尝试下一个地址..")
            logger.error(f"下载 {url} 下载超时.. Path：{path.absolute()}")
        except Exception as e:
            logger.error(f"下载 {url} 错误 Path：{path.absolute()}, {type(e)}:{e}")
        return False

    @classmethod
    async def gather_download_file(
        cls,
        url_list: list[str] | list[list[str]],
        path_list: list[str | Path],
        *,
        limit_async_number: int | None = None,
        params: dict[str, str] | None = None,
        use_proxy: bool = True,
        proxy: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        cookies: dict[str, str] | None = None,
        timeout: int = 30,
        **kwargs,
    ) -> list[bool]:
        """分组同时下载文件

        参数:
            url_list: url列表
            path_list: 存储路径列表
            limit_async_number: 限制同时请求数量
            params: params
            use_proxy: 使用代理
            proxy: 指定代理
            headers: 请求头
            cookies: cookies
            timeout: 超时时间
        """
        if n := len(url_list) != len(path_list):
            raise UrlPathNumberNotEqual(
                f"Url数量与Path数量不对等，Url：{len(url_list)}，Path：{len(path_list)}"
            )
        if limit_async_number and n > limit_async_number:
            m = float(n) / limit_async_number
            x = 0
            j = limit_async_number
            _split_url_list = []
            _split_path_list = []
            for _ in range(int(m)):
                _split_url_list.append(url_list[x:j])
                _split_path_list.append(path_list[x:j])
                x += limit_async_number
                j += limit_async_number
            if int(m) < m:
                _split_url_list.append(url_list[j:])
                _split_path_list.append(path_list[j:])
        else:
            _split_url_list = [url_list]
            _split_path_list = [path_list]
        tasks = []
        result_ = []
        for x, y in zip(_split_url_list, _split_path_list):
            for url, path in zip(x, y):
                tasks.append(
                    asyncio.create_task(
                        cls.download_file(
                            url,
                            path,
                            params=params,
                            headers=headers,
                            cookies=cookies,
                            use_proxy=use_proxy,
                            timeout=timeout,
                            proxy=proxy,
                            **kwargs,
                        )
                    )
                )
            _x = await asyncio.gather(*tasks)
            result_ = result_ + list(_x)
            tasks.clear()
        return result_

    @classmethod
    async def get_fastest_mirror(cls, url_list: list[str]) -> list[str]:
        assert url_list

        async def head_mirror(client: type[AsyncHttpx], url: str) -> dict[str, Any]:
            begin_time = time.time()

            response = await client.head(url=url, timeout=6)

            elapsed_time = (time.time() - begin_time) * 1000
            content_length = int(response.headers.get("content-length", 0))

            return {
                "url": url,
                "elapsed_time": elapsed_time,
                "content_length": content_length,
            }

        logger.debug(f"开始获取最快镜像，可能需要一段时间... | URL列表：{url_list}")
        results = await asyncio.gather(
            *(head_mirror(cls, url) for url in url_list),
            return_exceptions=True,
        )
        _results: list[dict[str, Any]] = []
        for result in results:
            if isinstance(result, BaseException):
                logger.warning(f"获取镜像失败，错误：{result}")
            else:
                logger.debug(f"获取镜像成功，结果：{result}")
                _results.append(result)
        _results = sorted(iter(_results), key=lambda r: r["elapsed_time"])
        return [result["url"] for result in _results]


class UrlPathNumberNotEqual(Exception):
    pass


class BrowserIsNone(Exception):
    pass
