"""应用用例：一次业务动作对应一次完整存储事务。"""

from dataclasses import asdict, replace
import logging
import time
import secrets

from .catalogue import Catalogue
from .domain import (
    Asset, FarmError, Identity, Plot, boosted, integer, quantity, text,
)
from .ports import Store
from .pests import advance_plot, start_growth
from .yield_rules import season_yield, remaining_yield
from .land import COMPENSATION_ID, SUPPORTED_PLOTS, next_rule, owned_count


LOGGER = logging.getLogger(__name__)


class FarmService:
    def __init__(self, store: Store, catalogue: Catalogue, clock=None):
        self.store = store
        self.catalogue = catalogue
        self.clock = clock if clock is not None else lambda: int(time.time())

    @staticmethod
    def _identity(identity):
        if not isinstance(identity, Identity):
            raise FarmError("invalid_identity")

    async def _execute(
        self, identity, operation_id, action, parameters, operation,
    ):
        self._identity(identity)
        text(operation_id)
        now = integer(self.clock())
        await self.ensure_initial_plots(identity)
        return await self.store.transact(
            identity, operation_id, action, parameters, now,
            lambda repository: operation(repository, now),
        )

    @staticmethod
    def _result(repository, **details):
        account = repository.account()
        return {
            **details, "account": asdict(account), "level": account.level,
        }

    async def snapshot(self, identity: Identity):
        self._identity(identity)
        now = integer(self.clock())
        await self.ensure_initial_plots(identity)
        snapshot = await self.store.snapshot(identity)
        return replace(snapshot, plots=tuple(
            advance_plot(plot, now) for plot in snapshot.plots
        ))

    async def ensure_initial_plots(self, identity: Identity):
        self._identity(identity)

        def operation(repository):
            repository.account()
            initial = repository.registration_plot_count()
            if initial is None:
                raise FarmError('land_origin_unknown')
            count = owned_count(repository.plots())
            if count < initial:
                raise FarmError('land_layout_invalid')
            added = 3 if initial == 3 else 0
            if count + added > SUPPORTED_PLOTS:
                raise FarmError('land_compensation_capacity')
            for slot in range(count + 1, count + added + 1):
                repository.add_plot(slot)
            return self._result(
                repository, added=added, previous_plot_count=count,
                plot_count=count + added, original_plot_count=initial,
            )

        try:
            return await self.store.transact(
                identity, COMPENSATION_ID, 'land_compensation', {'version': 1},
                integer(self.clock()), operation,
            )
        except FarmError as error:
            if error.code != 'not_registered':
                LOGGER.warning('farm initial land preparation failed reason=%s',
                               error.code)
                raise
            return None

    async def reclaim_conditions(self, identity: Identity):
        snapshot = await self.snapshot(identity)
        rule = next_rule(snapshot.plots)
        return {
            'slot': rule.ordinal, 'required_level': rule.required_level,
            'coin_cost': rule.coin_cost, 'level': snapshot.account.level,
            'point': snapshot.account.point,
        }

    async def reclaim(self, identity: Identity, operation_id: str):
        def operation(repository, now):
            account = repository.account()
            rule = next_rule(repository.plots())
            if account.level < rule.required_level:
                raise FarmError('level_required')
            repository.asset(Asset.POINT, -rule.coin_cost)
            repository.add_plot(rule.ordinal)
            return self._result(
                repository, slot=rule.ordinal, quantity=1,
                cost=rule.coin_cost, plot_count=rule.ordinal,
            )

        return await self._execute(identity, operation_id, 'reclaim', {},
                                   operation)

    async def register(
        self, identity: Identity, name: str, operation_id: str,
    ):
        text(name, 64)

        def operation(repository, now):
            created = repository.register(name)
            return self._result(
                repository, created=created,
                plot_count=len(repository.plots()),
            )

        return await self._execute(
            identity, operation_id, "register", {"name": name}, operation,
        )

    async def buy(
        self, identity: Identity, name: str, count: int, operation_id: str,
    ):
        text(name)
        quantity(count)

        def operation(repository, now):
            plant = self.catalogue.get(name)
            if not plant.enabled:
                raise FarmError("plant_disabled")
            if plant.crop_type != 1:
                raise FarmError("unsupported_crop_type")
            if not plant.purchasable:
                raise FarmError("plant_not_purchasable")
            if repository.account().level < plant.level:
                raise FarmError("level_required")
            cost = integer(plant.cost * count)
            repository.asset(plant.asset, -cost)
            repository.stock(plant, seeds=count)
            return self._result(
                repository, name=plant.name, plant_id=plant.plant_id,
                quantity=count, cost=cost,
                asset=plant.asset.value,
                seeds=repository.item(plant).seeds,
            )

        return await self._execute(
            identity, operation_id, "buy",
            {"name": name, "count": count}, operation,
        )

    async def sow(
        self, identity: Identity, name: str, count: int | None,
        operation_id: str,
    ):
        text(name)
        if count is not None:
            quantity(count)

        def operation(repository, now):
            repository.account()
            plant = self.catalogue.get(name)
            if not plant.enabled:
                raise FarmError("plant_disabled")
            if plant.crop_type != 1:
                raise FarmError("unsupported_crop_type")
            available = repository.item(plant).seeds
            empty = [p for p in repository.plots() if p.plant is None]
            amount = min(available, len(empty)) if count is None else count
            if amount == 0 or amount > available:
                raise FarmError("insufficient_stock")
            if amount > len(empty):
                raise FarmError("insufficient_empty_plots")
            mature_at = integer(now + plant.growth_seconds)
            repository.stock(plant, seeds=-amount)
            for plot in empty[:amount]:
                repository.save_plot(start_growth(replace(
                    plot, plant=plant, mature_at=mature_at, harvest_count=0,
                ), now))
            experience = integer(amount * 2)
            repository.asset(Asset.EXPERIENCE, experience)
            return self._result(
                repository, name=plant.name, plant_id=plant.plant_id,
                quantity=amount,
                slots=[p.slot for p in empty[:amount]],
                seeds=repository.item(plant).seeds,
                experience=experience,
            )

        return await self._execute(
            identity, operation_id, "sow",
            {"name": name, "count": count}, operation,
        )

    async def harvest(self, identity: Identity, operation_id: str):
        def operation(repository, now):
            repository.account()
            harvested = []
            total_experience = 0
            for plot in repository.plots():
                plot = advance_plot(plot, now)
                plant = plot.plant
                if (
                    plant is None or plot.withered or plot.mature_at is None
                    or plot.mature_at > now
                ):
                    continue
                amount = remaining_yield(plot)
                experience = boosted(
                    plant.experience, plot.experience_bonus,
                )
                repository.stock(plant, crops=amount)
                total_experience = integer(total_experience + experience)
                count = plot.harvest_count + 1
                mature_at = (
                    integer(now + plant.regrowth_seconds)
                    if count < plant.crop else None
                )
                updated = replace(
                    plot, mature_at=mature_at, harvest_count=count,
                    pest_count=0, pest_spawned=0, growth_remaining=None,
                    growth_updated_at=None, next_pest_at=None,
                    maturity_pests=0,
                    stolen_count=0,
                )
                repository.clear_thefts(plot.slot)
                repository.save_plot(
                    start_growth(updated, now) if count < plant.crop
                    else updated
                )
                harvested.append({
                    "slot": plot.slot, "name": plant.name,
                    "plant_id": plant.plant_id,
                    "quantity": amount, "experience": experience,
                    "pests": plot.maturity_pests,
                    "yield_loss_percent": plot.maturity_pests * 5,
                })
            if not harvested:
                raise FarmError("nothing_to_harvest")
            repository.asset(Asset.EXPERIENCE, total_experience)
            return self._result(
                repository, harvested=harvested,
                experience=total_experience,
                quantity=sum(item["quantity"] for item in harvested),
            )

        return await self._execute(
            identity, operation_id, "harvest", {}, operation,
        )

    async def eradicate(self, identity: Identity, operation_id: str):
        def operation(repository, now):
            repository.account()
            withered = [p for p in repository.plots() if p.withered]
            if not withered:
                raise FarmError("nothing_to_eradicate")
            for plot in withered:
                repository.clear_thefts(plot.slot)
                repository.save_plot(replace(
                    plot, plant=None, mature_at=None, harvest_count=0,
                    pest_count=0, pest_spawned=0, growth_remaining=None,
                    growth_updated_at=None, next_pest_at=None,
                    maturity_pests=0,
                    stolen_count=0,
                ))
            experience = integer(len(withered) * 2)
            repository.asset(Asset.EXPERIENCE, experience)
            return self._result(
                repository, slots=[p.slot for p in withered],
                experience=experience,
            )

        return await self._execute(
            identity, operation_id, "eradicate", {}, operation,
        )

    async def steal(self, identity: Identity, target: Identity,
                    operation_id: str):
        self._identity(identity)
        self._identity(target)
        if identity == target:
            raise FarmError('cannot_steal_self')
        if (identity.deployment, identity.realm, identity.platform) != (
            target.deployment, target.realm, target.platform
        ):
            raise FarmError('different_farm_scope')

        def operation(repository, now):
            repository.account()
            owner = repository.for_identity(target)
            try:
                owner.account()
            except FarmError as error:
                if error.code == 'not_registered':
                    raise FarmError('target_not_registered') from error
                raise
            day_start = ((now+28800)//86400)*86400-28800
            used = repository.successful_thefts(day_start)
            if used >= 5:
                raise FarmError('steal_daily_limit')
            items = []
            skipped = {'not_ripe': 0, 'already_stolen': 0, 'protected': 0}
            for stored in owner.plots():
                plot = advance_plot(stored, now)
                if (plot.plant is None or plot.withered
                        or plot.mature_at is None or plot.mature_at > now):
                    skipped['not_ripe'] += 1
                    continue
                if owner.theft_seen(plot.slot, identity):
                    skipped['already_stolen'] += 1
                    continue
                total = season_yield(plot)
                available = remaining_yield(plot)-(total+1)//2
                if available <= 0:
                    skipped['protected'] += 1
                    continue
                amount = min(secrets.randbelow(3)+1, available)
                repository.stock(plot.plant, crops=amount)
                owner.save_plot(replace(
                    plot, stolen_count=plot.stolen_count+amount,
                ))
                owner.record_theft(plot.slot, identity)
                items.append({'slot': plot.slot, 'name': plot.plant.name,
                              'plant_id': plot.plant.plant_id,
                              'quantity': amount})
            return self._result(
                repository, items=items, skipped=skipped,
                quantity=sum(i['quantity'] for i in items),
                remaining_attempts=5-used-bool(items),
            )

        return await self._execute(identity, operation_id, 'steal',
                                   {'target': target.key}, operation)

    async def clear_pests(self, identity: Identity, operation_id: str):
        def operation(repository, now):
            repository.account()
            cleared = []
            for stored in repository.plots():
                plot = advance_plot(stored, now)
                if plot.pest_count == 0:
                    continue
                cleared.append({"slot": plot.slot, "pests": plot.pest_count})
                updated = replace(plot, pest_count=0)
                repository.save_plot(advance_plot(updated, now))
            if not cleared:
                raise FarmError("nothing_to_clear")
            quantity = integer(sum(item['pests'] for item in cleared))
            repository.asset(Asset.EXPERIENCE, quantity)
            return self._result(
                repository, cleared=cleared,
                quantity=quantity, experience=quantity,
            )

        return await self._execute(
            identity, operation_id, "clear_pests", {}, operation,
        )

    async def lock(
        self, identity: Identity, name: str, locked: bool,
        operation_id: str,
    ):
        text(name)
        if type(locked) is not bool:
            raise FarmError("invalid_lock")

        def operation(repository, now):
            repository.account()
            plant = self.catalogue.get(name)
            repository.lock(plant, locked)
            return self._result(
                repository, name=plant.name, plant_id=plant.plant_id,
                locked=locked,
            )

        return await self._execute(
            identity, operation_id, "lock",
            {"name": name, "locked": locked}, operation,
        )

    async def sell(
        self, identity: Identity, name: str | None, count: int | None,
        operation_id: str,
    ):
        if name is not None:
            text(name)
        if count is not None:
            quantity(count)
            if name is None:
                raise FarmError("name_required_for_quantity")

        def operation(repository, now):
            repository.account()
            if name is not None:
                plant = self.catalogue.get(name)
                item = repository.item(plant)
                if item.locked:
                    raise FarmError("plant_locked")
                amount = item.crops if count is None else count
                if amount <= 0 or amount > item.crops:
                    raise FarmError("insufficient_stock")
                items = [(plant.plant_id, amount)]
            else:
                items = [
                    (item.plant_id, item.crops)
                    for item in repository.items()
                    if not item.locked and item.crops > 0
                ]
                if not items:
                    raise FarmError("nothing_to_sell")
            proceeds = 0
            sold = []
            for plant_id, amount in items:
                plant = self.catalogue.get_by_id(plant_id)
                proceeds = integer(proceeds + plant.price * amount)
                repository.stock(plant, crops=-amount)
                sold.append({
                    "name": plant.name, "plant_id": plant.plant_id,
                    "quantity": amount,
                })
            repository.asset(Asset.POINT, proceeds)
            return self._result(
                repository, sold=sold, proceeds=proceeds,
                quantity=sum(item["quantity"] for item in sold),
            )

        return await self._execute(
            identity, operation_id, "sell",
            {"name": name, "count": count}, operation,
        )
