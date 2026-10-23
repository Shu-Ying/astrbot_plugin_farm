"""异步入口：一次快照、有限任务、共享绘制与关闭排空。"""

import asyncio
import logging
from time import perf_counter
import time
import hashlib

from .shop import render_shop
from .details import render_details
from .warehouse import render_warehouse
from .help import render_help

logger = logging.getLogger(__name__)


class RenderService:
    def __init__(self, renderer, concurrency=1, max_pending=8):
        if (type(concurrency) is not int or type(max_pending) is not int
                or concurrency < 1 or max_pending < concurrency):
            raise ValueError("Invalid render capacity")
        self.renderer = renderer
        self._semaphore = asyncio.Semaphore(concurrency)
        self._max_pending = max_pending
        self._pending = {}
        self._closed = False

    async def my_farm(
        self, source, identity, *, now=None, options=None, avatar=None,
        supported=("JPEG",),
    ):
        if self._closed:
            raise RuntimeError("Render service closed")
        started = perf_counter()
        snapshot = await source.snapshot(identity)
        logger.info("farm render query_ms=%.2f", (perf_counter()-started)*1000)
        return await self.render(
            identity, snapshot, int(time.time()) if now is None else now,
            options, avatar, supported,
        )

    async def render(
        self, identity, snapshot, now, options=None, avatar=None,
        supported=("JPEG",),
    ):
        if self._closed:
            raise RuntimeError("Render service closed")
        key = self.renderer.request_key(
            identity, snapshot, now, options, avatar, supported,
        )
        task = self._pending.get(key)
        if task is None:
            if len(self._pending) >= self._max_pending:
                raise RuntimeError("Render queue full")
            task = asyncio.create_task(self._run(
                identity, snapshot, now, options, avatar, supported,
            ))
            self._pending[key] = task

            def finished(done):
                self._pending.pop(key, None)
                if not done.cancelled():
                    done.exception()

            task.add_done_callback(finished)
        return await asyncio.shield(task)

    async def _run(self, *args):
        return await self._run_function(self.renderer.render, *args)

    async def seed_shop(self, plants, account, page, pages,
                        image_format='AUTO', quality=75):
        if self._closed:
            raise RuntimeError('Render service closed')
        key = 'shop:' + hashlib.sha256(
            repr((plants, account, page, pages, image_format,
                  quality)).encode(),
        ).hexdigest()
        task = self._pending.get(key)
        if task is None:
            if len(self._pending) >= self._max_pending:
                raise RuntimeError('Render queue full')
            task = asyncio.create_task(self._run_function(
                render_shop, self.renderer, plants, account, page, pages,
                image_format, quality,
            ))
            self._pending[key] = task

            def finished(done):
                self._pending.pop(key, None)
                if not done.cancelled():
                    done.exception()

            task.add_done_callback(finished)
        return await asyncio.shield(task)

    async def farm_details(self, identity, snapshot, now, page, theme,
                           image_format='AUTO', avatar=None, quality=75):
        if self._closed:
            raise RuntimeError('Render service closed')
        key = 'details:' + hashlib.sha256(repr((
            identity, snapshot, now, page, theme, image_format, avatar, quality,
        )).encode()).hexdigest()
        task = self._pending.get(key)
        if task is None:
            if len(self._pending) >= self._max_pending:
                raise RuntimeError('Render queue full')
            task = asyncio.create_task(self._run_function(
                render_details, self.renderer, identity, snapshot, now,
                page, theme, image_format, avatar, quality,
            ))
            self._pending[key] = task

            def finished(done):
                self._pending.pop(key, None)
                if not done.cancelled():
                    done.exception()

            task.add_done_callback(finished)
        return await asyncio.shield(task)

    async def warehouse(self, rows, snapshot, kind, page, pages,
                        image_format='AUTO', high=False, quality=75):
        if self._closed:
            raise RuntimeError('Render service closed')
        key = ('warehouse', rows, snapshot, kind, page, pages,
               image_format, high, quality)
        cached = self.renderer.results.get(key)
        if cached is not None:
            return cached
        task = self._pending.get(key)
        if task is None:
            if len(self._pending) >= self._max_pending:
                raise RuntimeError('Render queue full')
            task = asyncio.create_task(self._run_function(
                render_warehouse, self.renderer, rows, snapshot, kind,
                page, pages, image_format, high, quality,
            ))
            self._pending[key] = task

            def finished(done):
                self._pending.pop(key, None)
                if not done.cancelled():
                    done.exception()

            task.add_done_callback(finished)
        content = await asyncio.shield(task)
        self.renderer.results.put(key, content, len(content))
        return content

    async def help_menu(self, specs, platform, image_format='AUTO', quality=75):
        if self._closed:
            raise RuntimeError('Render service closed')
        key = ('help', specs, platform, image_format, quality)
        cached = self.renderer.results.get(key)
        if cached is not None:
            return cached
        task = self._pending.get(key)
        if task is None:
            if len(self._pending) >= self._max_pending:
                raise RuntimeError('Render queue full')
            task = asyncio.create_task(self._run_function(
                render_help, self.renderer, specs, platform,
                image_format, quality,
            ))
            self._pending[key] = task

            def finished(done):
                self._pending.pop(key, None)
                if not done.cancelled():
                    done.exception()

            task.add_done_callback(finished)
        content = await asyncio.shield(task)
        self.renderer.results.put(key, content, len(content))
        return content

    async def _run_function(self, function, *args):
        started = perf_counter()
        async with self._semaphore:
            logger.info(
                "farm render queue_ms=%.2f", (perf_counter()-started)*1000,
            )
            worker = asyncio.create_task(asyncio.to_thread(
                function, *args,
            ))
            try:
                return await asyncio.shield(worker)
            except asyncio.CancelledError:
                await worker
                raise

    async def close(self):
        self._closed = True
        pending = tuple(self._pending.values())
        if pending:
            await asyncio.shield(asyncio.gather(
                *pending, return_exceptions=True,
            ))

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.close()
