"""AstrBot薄接入；业务、交易及绘图复用共享运行时。"""

import asyncio
import json
from pathlib import Path

from astrbot.api import AstrBotConfig
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import At, Image
from astrbot.api.star import Context, Star, StarTools

from .avatars import AvatarCache
from .runtime import Runtime, command_map

COMMANDS = command_map('astrbot')


class FarmPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self._lifecycle_lock = asyncio.Lock()
        self._closed = False
        self._avatars = AvatarCache()
        configured = config.get('data_dir', '')
        data_dir = (Path(configured).expanduser() if configured else
                    StarTools.get_data_dir('astrbot_plugin_farm'))
        image_format = str(config.get('image_format', 'AUTO')).upper()
        if image_format not in ('AUTO', 'JPEG', 'PNG'):
            raise ValueError('image_format must be AUTO, JPEG or PNG')
        self.runtime = Runtime(
            data_dir, deployment='astrbot', image_format=image_format,
            image_quality=config.get('image_quality', 75),
            image_quality_provider=lambda: self.config.get('image_quality', 75),
            framework='astrbot',
            resource_source=config.get('resource_source', 'Github'),
            service_url=config.get('farm_service_url', ''),
        )

    async def initialize(self):
        async with self._lifecycle_lock:
            if not self._closed:
                await self.runtime.start()

    @filter.command('农场帮助', alias=set(COMMANDS) - {'农场帮助'})
    async def farm(self, event: AstrMessageEvent):
        """农场帮助、注册、种植、仓库、交易及图片查询。"""
        if self._closed:
            yield event.plain_result('农场插件已关闭。')
            return
        await self.initialize()
        parts = event.get_message_str().strip().split(maxsplit=1)
        if not parts or parts[0] not in COMMANDS:
            return
        action = COMMANDS[parts[0]]
        arguments = parts[1] if len(parts) == 2 else ''
        target = None
        if action == 'steal':
            mentions = [str(segment.qq) for segment in event.get_messages()
                        if isinstance(segment, At)
                        and str(segment.qq) != str(event.get_self_id())]
            if len(mentions) != 1 or mentions[0] in ('', 'all', '0'):
                yield event.plain_result('请@一个具体的偷菜目标。')
                return
            target = mentions[0]
        platform_id = event.get_platform_id()
        if not platform_id or not event.get_sender_id():
            yield event.plain_result('无法取得稳定的平台或用户标识，未执行。')
            return
        bot_id = json.dumps([str(platform_id), str(event.get_self_id())])
        avatar = None
        if action in ('farm', 'details', 'plot_ids') and self.runtime.rendering:
            avatar = await self._avatars.get(
                event.get_platform_name(), event.get_sender_id(),
            )
        response = await self.runtime.execute(
            action, arguments, bot_id=bot_id,
            platform=event.get_platform_name(), user_id=event.get_sender_id(),
            message_id=getattr(event.message_obj, 'message_id', None),
            display_name=event.get_sender_name() or '农场玩家',
            target_user_id=target, avatar=avatar,
        )
        if isinstance(response, bytes):
            yield event.chain_result([Image.fromBytes(response)])
        else:
            yield event.plain_result(response)

    async def terminate(self):
        async with self._lifecycle_lock:
            if self._closed:
                return
            self._closed = True
            await self._avatars.close()
            await self.runtime.close()
            logger.info('farm astrbot plugin terminated')
