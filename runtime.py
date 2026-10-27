"""各平台适配器共用的运行编排；不导入宿主框架。"""

import hashlib
import asyncio
from dataclasses import replace
import json
import logging
from pathlib import Path
import shlex
from urllib.error import HTTPError, URLError
from zipfile import BadZipFile

from ._vendor.farm_core import Catalogue, FarmService, Identity, SQLiteStore
from ._vendor.farm_core.domain import FarmError
from ._vendor.farm_core.commands import (
    command_map, command_specs, help_text,
)
from ._vendor.farm_core.storage import SCHEMA_VERSION
from ._vendor.farm_core.presentation import (
    plot_ids_text, receipt_text, snapshot_text,
)
from ._vendor.farm_render import FarmRenderer, RenderOptions, RenderService
from ._vendor.farm_render.seasons import season_for
from ._vendor.farm_render.bundle import ensure_assets, validate_options
from ._vendor.farm_render.font_bundle import ensure_font
from ._vendor.farm_render.catalogue_bundle import load_catalogue_release
from ._vendor.farm_render.shop import shop_page
from ._vendor.farm_render.details import detail_rows, details_text
from ._vendor.farm_render.warehouse import (
    warehouse_page, warehouse_rows, warehouse_text,
)

logger = logging.getLogger(__name__)
COMMANDS = command_map('zhenxun')
HELP = help_text(command_specs('zhenxun'))


def resource_failure_reason(error):
    """只返回固定分类，不输出可能含 URL 或凭据的异常正文。"""
    if isinstance(error, HTTPError):
        return f'http_{error.code}'
    if isinstance(error, TimeoutError):
        return 'timeout'
    if isinstance(error, URLError):
        return ('timeout' if isinstance(error.reason, TimeoutError)
                else 'network_error')
    if isinstance(error, BadZipFile):
        return 'invalid_archive'
    if isinstance(error, ValueError):
        known = {
            'Resource SHA256 mismatch': 'integrity_mismatch',
            'Resource size mismatch': 'integrity_mismatch',
            'Font archive size or SHA256 mismatch': 'integrity_mismatch',
            'Font member SHA256 mismatch': 'integrity_mismatch',
            'Resource download limit or timeout': 'download_limit_or_timeout',
        }
        return known.get(str(error), 'validation_error')
    if isinstance(error, OSError):
        return 'io_error'
    return 'unexpected_error'


ERRORS = {
    'land_max_level': '该地块已是金土地，当前不支持继续升级。',
    'unknown_plot': '地块不存在，请发送「地块编号」查询已开垦土地。',
    'land_origin_unknown': '农场初始土地来源无法确认，未补地或扣币，'
                           '请联系管理员核查注册或迁移记录。',
    'land_compensation_capacity': '旧用户补3块后将超出当前30个绘图位置，'
                                 '已保留原状，请联系管理员单独处理补偿。',
    'land_layout_invalid': '地块编号或数量异常，未补地或扣币，请联系管理员核查。',
    'land_rules_invalid': '开垦配置异常，未扣币，请联系管理员检查。',
    'land_rule_unavailable': '下一块地的开垦规则尚未配置，未扣币。',
    'cannot_steal_self': '不能偷自己的农场。',
    'different_farm_scope': '只能偷取当前机器人、平台内的农场。',
    'target_not_registered': '目标尚未开通当前农场。',
    'steal_daily_limit': '今日成功偷菜已达5次，北京时间零点恢复。',
    "legacy_identity_bound":"旧农场已绑定其他机器人或平台，请联系管理员。",
    "legacy_account_conflict":"新旧农场账号冲突，未覆盖，请联系管理员。",
    "legacy_schema_unsupported":"旧农场数据库结构不兼容，请联系管理员。",
    "legacy_data_invalid":"旧农场数据异常，迁移已回滚，请联系管理员。",
    "not_registered":"请先发送：开通农场",
    "unknown_plant":"没有这种作物，请查看种子商店。",
    "ambiguous_plant":"存在同名作物，请使用商店或仓库中的 #编号。",
    "plant_not_purchasable":"该种子当前不出售，已有种子仍可播种。",
    "plant_disabled":"该作物已停用，暂不能购买或播种。",
    "unsupported_crop_type":"该条目不支持作为普通作物种植。",
    "invalid_integer":"数量必须为有效的正整数。",
    "insufficient_funds":"余额不足。",
    "insufficient_stock":"库存不足。",
    "insufficient_empty_plots":"空地不足。",
    "level_required":"等级不足。", "plant_locked":"该作物已锁定。",
    "nothing_to_harvest":"当前没有成熟作物。",
    "nothing_to_eradicate":"当前没有枯萎作物。",
    "nothing_to_sell":"当前没有可出售作物。",
    "nothing_to_clear":"当前没有虫子需要清除。",
    "operation_conflict":"该事件已处理但参数不一致，请发送新消息。",
}


def operation_id(bot_id, platform, user_id, message_id, action):
    if message_id is None or str(message_id) == "":
        return None
    return hashlib.sha256(json.dumps(
        [str(bot_id), platform, user_id, str(message_id), action],
        ensure_ascii=False,
    ).encode()).hexdigest()


class Runtime:
    def __init__(self, data_dir, font_path=None, deployment="zhenxun-preview",
                 image_format="AUTO", *, font_dir=None,
                 image_quality=75,
                 image_quality_provider=None, framework='zhenxun',
                 resource_source='Github', service_url='',
                 resource_options_provider=None):
        RenderOptions(quality=image_quality)
        validate_options(resource_source, service_url)
        self.resource_source = resource_source
        self.service_url = service_url
        self.resource_options_provider = resource_options_provider
        self.framework = framework
        self.command_specs = command_specs(framework)
        self.commands = command_map(framework)
        self.image_quality = image_quality
        self.image_quality_provider = image_quality_provider
        self.data_dir = Path(data_dir).resolve()
        self.font_path = font_path
        self.font_dir = Path(font_dir or "resources/font")
        self.deployment = deployment
        self.image_format = image_format
        self.store = SQLiteStore(self.data_dir / "farm.sqlite3")
        self.service = FarmService(self.store, Catalogue.bundled())
        self.rendering = None
        self.started = False
        self.log_handler = None
        self.legacy_source = self.data_dir / 'farm.db'
        self._resource_lock = asyncio.Lock()
        self._closing = False
        self._close_task = None
        self._start_lock = asyncio.Lock()
        self._catalogue_task = None
        self.catalogue_release = None
        self._start_epoch = 0

    async def start(self):
        async with self._start_lock:
            await self._start()

    async def _start(self):
        if self._closing:
            return
        if self.started:
            return
        epoch = self._start_epoch
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.log_handler = logging.FileHandler(
            self.data_dir / "farm-preview.log", encoding="utf-8",
        )
        self.log_handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s",
        ))
        logging.getLogger(__package__).setLevel(logging.INFO)
        logging.getLogger(__package__).addHandler(self.log_handler)
        try:
            if self.resource_options_provider is not None:
                self.resource_source, self.service_url = (
                    self.resource_options_provider()
                )
            validate_options(self.resource_source, self.service_url)
            required_ids = await self.store.catalogue_ids()
            if self._closing or epoch != self._start_epoch:
                return
            self._catalogue_task = asyncio.create_task(asyncio.to_thread(
                load_catalogue_release, self.data_dir, self.resource_source,
                self.service_url, required_ids,
            ))
            self.catalogue_release = await asyncio.shield(self._catalogue_task)
            if self._closing or epoch != self._start_epoch:
                return
            self.service = FarmService(
                self.store, self.catalogue_release.catalogue,
            )
            await self.store.initialize(catalogue=self.service.catalogue)
            if self._closing or epoch != self._start_epoch:
                return
        except BaseException:
            logger.error("farm preview database initialization failed")
            await self.close()
            raise
        await self._prepare_resources()
        if self._closing or epoch != self._start_epoch:
            return
        self.started = True
        logger.info("farm preview initialized schema=%s", SCHEMA_VERSION)

    async def _prepare_resources(self):
        async with self._resource_lock:
            if self._closing or self.rendering is not None:
                return
            resource = 'configuration'
            try:
                if (self.catalogue_release is None
                        and self.resource_options_provider is not None):
                    self.resource_source, self.service_url = (
                        self.resource_options_provider()
                    )
                validate_options(self.resource_source, self.service_url)
                resource = 'assets'
                selected = self.catalogue_release
                bundle_path = selected.bundle_path if selected else None
                if bundle_path is None:
                    bundle_path = await asyncio.to_thread(
                        ensure_assets, self.data_dir, self.resource_source,
                        self.service_url,
                    )
                resource = 'font'
                candidate = (Path(self.font_path) if self.font_path else
                             await asyncio.to_thread(
                                 ensure_font, self.data_dir,
                                 self.resource_source, self.service_url,
                             ))
                resource = 'renderer'
                self.rendering = RenderService(FarmRenderer(
                    candidate, bundle_path=bundle_path,
                    metadata=selected.metadata if selected else None,
                    soils_path=selected.soils_path if selected else None,
                ))
                logger.info('farm resources ready font=%s', candidate.name)
            except Exception as error:
                source = (self.resource_source if self.resource_source in (
                    'Github', 'Gitea', 'farm_service',
                ) else 'invalid')
                logger.warning(
                    'farm resource unavailable resource=%s source=%s '
                    'reason=%s; loading stopped until plugin reload; '
                    'using text',
                    resource, source, resource_failure_reason(error),
                )

    async def close(self):
        if self._close_task is None or self._close_task.done():
            self._closing = True
            self._start_epoch += 1
            self._close_task = asyncio.create_task(self._finish_close())
        task = self._close_task
        try:
            # 调用方取消关闭等待时，清理仍独立运行。
            await asyncio.shield(task)
        finally:
            if task.done():
                self._close_task = None

    async def _finish_close(self):
        try:
            if self._catalogue_task is not None:
                try:
                    await asyncio.shield(self._catalogue_task)
                except Exception:
                    pass
            async with self._resource_lock:
                if self.rendering:
                    await self.rendering.close()
                self.rendering = None
        finally:
            await self.store.close()
            self.started = False
            self._closing = False
            if self.log_handler:
                logging.getLogger(__package__).removeHandler(self.log_handler)
                self.log_handler.close()
                self.log_handler = None

    async def execute(
        self, action, arguments, *, bot_id, platform, user_id, message_id,
        display_name="农场玩家", avatar=None, target_user_id=None,
    ):
        if not self.started:
            return "农场尚未初始化，请检查启动日志。"
        try:
            args = shlex.split(arguments)
            # 帮助无需注册或迁移玩家数据，绘图失败可直接阅读文字。
            if action == 'help':
                return await self.help_menu(args)
            who = Identity(self.deployment, str(bot_id), platform, str(user_id))
            try:
                await self.store.migrate_legacy(
                    self.legacy_source, who, self.service.catalogue,
                    self.service.clock(),
                )
            except (FarmError, KeyError, TypeError) as error:
                logger.exception('farm legacy migration failed')
                code = getattr(error, 'code', '')
                return ERRORS.get(
                    code if code.startswith('legacy_') else '',
                    '旧农场数据无法迁移，请联系管理员检查日志。',
                )
            args = shlex.split(arguments)
            if action == "farm" and args:
                aliases = {
                    "detail":"details", "my-seed":"seeds",
                    "my-plant":"crops", "seed-shop":"shop",
                    "buy-seed":"buy", "sowing":"sow", "harvest":"harvest",
                    "eradicate":"eradicate", "lock-plant":"lock",
                    "unlock-plant":"unlock", "sell-plant":"sell",
                    "farm-help":"help",
                    "clear-pests":"clear_pests",
                }
                if args[0] in aliases:
                    action = aliases[args[0]]
                    args = args[1:]
            op = operation_id(
                bot_id, platform, str(user_id), message_id, action,
            )
            if action == "help":
                return await self.help_menu(args)
            if action == 'reclaim' and args == ['条件']:
                conditions = await self.service.reclaim_conditions(who)
                return (
                    f"下一块：{conditions['slot']}号普通空地\n"
                    f"所需等级：{conditions['required_level']}"
                    f"（当前{conditions['level']}）\n"
                    f"所需农场币：{conditions['coin_cost']}"
                    f"（当前{conditions['point']}）\n"
                    '满足条件后发送：开垦'
                )
            if action == 'upgrade':
                if len(args) not in (1, 2) or (len(args) == 2
                                             and args[1] != '条件'):
                    return '请发送：土地升级 地块编号 或 土地升级 地块编号 条件'
                slot = int(args[0])
                if len(args) == 2:
                    condition = await self.service.upgrade_conditions(who, slot)
                    return (
                        f"地块{slot}：{condition['current_land']}→"
                        f"{condition['land_name']}（第{condition['ordinal']}块）\n"
                        f"所需等级：{condition['required_level']}"
                        f"（当前{condition['level']}）\n"
                        f"所需农场币：{condition['coin_cost']}"
                        f"（当前{condition['point']}）\n"
                        f'升级并使当前季成熟：土地升级 {slot}'
                    )
                if op is None:
                    return '无法取得稳定消息标识，本次写操作未执行。'
                return receipt_text(await self.service.upgrade(who, slot, op))
            image_actions = ('farm', 'plot_ids', 'details', 'shop',
                             'seeds', 'crops')
            if action in image_actions and action != 'farm' and '高清' in args:
                return '仅我的农场支持高清，请移除高清参数后重试。'
            quality = self.image_quality
            if action in ('seeds', 'crops') and '文字' in args:
                raise ValueError()
            if action in image_actions and self.rendering:
                try:
                    if self.image_quality_provider is not None:
                        quality = self.image_quality_provider()
                    RenderOptions(quality=quality)
                except (TypeError, ValueError):
                    logger.warning('farm image quality config invalid')
                    return '农场图片质量配置无效，请设置为1～95的整数。'
            if action == "shop":
                page = int(args[0]) if args else 1
                if len(args) > 1:
                    raise ValueError()
                try:
                    chunk, pages = shop_page(self.service.catalogue, page)
                except ValueError:
                    return '页码无效，请发送：种子商店 1'
                if self.rendering:
                    account = None
                    try:
                        account = (await self.service.snapshot(who)).account
                    except FarmError as error:
                        if error.code != 'not_registered':
                            raise
                    return await self.rendering.seed_shop(
                        chunk, account, page, pages,
                        image_format=self.image_format,
                        quality=quality,
                    )
                return f'种子商店 第{page}/{pages}页\n' + '\n'.join(
                    f'{p.name}（#{p.plant_id}）：'
                    f'{p.cost}{"点券" if p.is_vip else "农场币"}'
                    f' / 等级{p.level}' for p in chunk
                ) + (
                    '\n购买种子 #编号 数量 或 购买种子 种子名 数量'
                    + (f'\n下一页：种子商店 {page+1}' if page < pages else '')
                )
            if action == 'details':
                if len(args) > 1:
                    raise ValueError()
                page = int(args[0]) if args else 1
                snapshot = await self.service.snapshot(who)
                now = self.service.clock()
                try:
                    rows, pages = detail_rows(
                        self.rendering.renderer if self.rendering else None,
                        who, snapshot, now, page,
                    )
                except ValueError:
                    return '页码无效，请发送：农场详述 1'
                if not self.rendering:
                    return details_text(rows, page, pages)
                return await self.rendering.farm_details(
                    who, snapshot, now, page, season_for(now),
                    image_format=self.image_format, avatar=avatar,
                    quality=quality,
                )
            if action in ('crops', 'seeds'):
                title = '我的作物' if action == 'crops' else '我的种子'
                if len(args) > 1:
                    raise ValueError()
                try:
                    page = int(args[0]) if args else 1
                except ValueError:
                    return f'页码无效，请发送：{title} 1'
                snapshot = await self.service.snapshot(who)
                rows = warehouse_rows(snapshot, self.service.catalogue, action)
                try:
                    _, pages = warehouse_page(rows, page)
                except ValueError:
                    return f'页码无效，请发送：{title} 1'
                if not self.rendering:
                    return warehouse_text(rows, snapshot, action, page, pages)
                return await self.rendering.warehouse(
                    rows, snapshot, action, page, pages, self.image_format,
                    quality=quality,
                )
            if action == "inventory":
                if args:
                    raise ValueError()
                return snapshot_text(await self.service.snapshot(who))
            if action in ("farm", "plot_ids"):
                if args not in ([], ["高清"]):
                    raise ValueError()
                if not self.rendering:
                    if action == "plot_ids":
                        return plot_ids_text(await self.service.snapshot(who))
                    return "农场图片资源暂不可用，请检查素材和小赖字体的下载日志。"
                now = self.service.clock()
                theme = season_for(now)
                logger.info("farm preview seasonal theme=%s", theme)
                options = (
                    RenderOptions(width=1536, quality=max(quality, 85),
                                  format=self.image_format, theme=theme)
                    if args else RenderOptions(format=self.image_format,
                                               theme=theme, quality=quality)
                )
                if action == "plot_ids":
                    options = replace(options, show_plot_ids=True)
                picture = await self.rendering.my_farm(
                    self.service, who, options=options, avatar=avatar,
                    supported=("JPEG",),
                    now=now,
                )
                return picture.content
            if op is None:
                return "无法取得稳定消息标识，本次写操作未执行。"
            if action == 'steal':
                if target_user_id is None:
                    return '请发送：偷菜 @目标，不支持直接输入QQ号。'
                if args:
                    return '请只指定一个偷菜目标，不要附加QQ号或其他文字。'
                target = Identity(who.deployment, who.realm, who.platform,
                                  str(target_user_id))
                receipt = await self.service.steal(who, target, op)
            elif action == "register":
                name = " ".join(args) if args else display_name
                name = " ".join(str(name).split())[:64] or "农场玩家"
                receipt = await self.service.register(who, name, op)
            elif action in ("buy", "sow", "sell"):
                if action == "sell" and not args:
                    receipt = await self.service.sell(who, None, None, op)
                else:
                    if len(args) not in (1, 2) or (action == "buy"
                                                 and len(args) != 2):
                        raise ValueError()
                    count = int(args[1]) if len(args) == 2 else None
                    receipt = await getattr(self.service, action)(
                        who, args[0], count, op,
                    )
            elif action in ("lock", "unlock"):
                if len(args) != 1:
                    raise ValueError()
                receipt = await self.service.lock(
                    who, args[0], action == "lock", op,
                )
            elif action in ("harvest", "eradicate", "clear_pests", "reclaim"):
                if args:
                    raise ValueError()
                receipt = await getattr(self.service, action)(who, op)
            else:
                return help_text(self.command_specs)
            text = receipt_text(receipt)
            if action == 'register':
                if receipt.data['created']:
                    count = receipt.data.get('plot_count')
                    granted = (f'已获得{count}块土地' if count is not None
                               else '已获得初始土地')
                    text += f'\n{granted}，发送「地块编号」查看位置。'
                else:
                    text += '\n发送「地块编号」查看土地位置。'
            return text
        except FarmError as error:
            return ERRORS.get(error.code, "操作未完成：" + error.code)
        except ValueError:
            return "参数有误，请发送：农场帮助"

    async def help_menu(self, args):
        if '高清' in args:
            return '仅我的农场支持高清，请移除高清参数后重试。'
        if args:
            return '参数有误，请发送：农场帮助'
        fallback = help_text(self.command_specs)
        if self.rendering is None:
            return fallback
        quality = self.image_quality
        if self.image_quality_provider is not None:
            quality = self.image_quality_provider()
        try:
            RenderOptions(quality=quality)
        except (ValueError, TypeError):
            logger.warning('farm help image quality config invalid')
            return '农场图片质量配置无效，请设置为1～95的整数。'
        try:
            return await self.rendering.help_menu(
                self.command_specs, self.framework, self.image_format, quality,
            )
        except (OSError, ValueError, RuntimeError):
            logger.exception('farm help rendering failed; using text')
            return fallback
