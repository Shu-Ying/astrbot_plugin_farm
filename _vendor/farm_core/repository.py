"""单个 SQLite 事务内的仓储；不自行提交或开启事务。"""

from dataclasses import asdict
import json
import sqlite3

from .domain import (
    Account, Asset, FarmError, InventoryItem, Plot, Plant, StorageError,
    integer,
)


class SQLiteRepository:
    def __init__(
        self, connection: sqlite3.Connection, identity: str,
        operation_id: str, action: str, now: int,
    ):
        self._db = connection
        self._identity = identity
        self._operation_id = operation_id
        self._action = action
        self._now = now

    def account(self) -> Account:
        row = self._db.execute(
            "SELECT name, point, vip_point, experience "
            "FROM accounts WHERE identity=?", (self._identity,),
        ).fetchone()
        if row is None:
            raise FarmError("not_registered")
        return Account(**dict(row))

    def register(self, name: str) -> bool:
        exists = self._db.execute(
            "SELECT 1 FROM accounts WHERE identity=?", (self._identity,),
        ).fetchone()
        if exists:
            return False
        self._db.execute(
            "INSERT INTO accounts(identity, name) VALUES (?, ?)",
            (self._identity, name),
        )
        self._db.executemany(
            "INSERT INTO plots(identity, slot) VALUES (?, ?)",
            [(self._identity, slot) for slot in range(1, 7)],
        )
        self.asset(Asset.POINT, 500)
        return True

    def asset(self, asset: Asset, delta: int) -> None:
        if not isinstance(asset, Asset):
            raise FarmError("invalid_asset")
        integer(delta, -(2**63 - 1))
        previous = getattr(self.account(), asset.value)
        updated = previous + delta
        if updated < 0:
            raise FarmError("insufficient_funds")
        integer(updated)
        if delta == 0:
            return
        column = asset.value
        cursor = self._db.execute(
            f"UPDATE accounts SET {column}=? "
            f"WHERE identity=? AND {column}=?",
            (updated, self._identity, previous),
        )
        if cursor.rowcount != 1:
            raise FarmError("state_conflict")
        self._db.execute(
            "INSERT INTO ledger("
            "identity, operation_id, asset, delta, reason, created_at"
            ") VALUES (?, ?, ?, ?, ?, ?)",
            (
                self._identity, self._operation_id, asset.value, delta,
                self._action, self._now,
            ),
        )

    def registration_plot_count(self) -> int | None:
        rows = self._db.execute(
            "SELECT action, result FROM operations WHERE identity=? "
            "AND action IN ('legacy_import', 'register') "
            "ORDER BY created_at, rowid", (self._identity,),
        ).fetchall()
        try:
            for row in rows:
                data = json.loads(row['result'])
                if row['action'] == 'legacy_import':
                    if (type(data.get('migration_version')) is int
                            and data['migration_version'] == 1
                            and data.get('legacy_rows', {}).get('user')):
                        return 3
                elif data.get('created') is True:
                    count = data.get('plot_count', 3)
                    if type(count) is int and count in (3, 6):
                        return count
                    return None
        except (ValueError, TypeError, AttributeError):
            return None
        return None

    def add_plot(self, slot: int) -> None:
        from .land import SUPPORTED_PLOTS

        integer(slot, 1, SUPPORTED_PLOTS)
        self._db.execute(
            'INSERT INTO plots(identity, slot) VALUES (?, ?)',
            (self._identity, slot),
        )

    def item(self, plant: Plant) -> InventoryItem:
        row = self._db.execute(
            "SELECT name, seeds, crops, locked FROM inventory "
            "WHERE identity=? AND plant_id=?",
            (self._identity, plant.plant_id),
        ).fetchone()
        if row is None:
            return InventoryItem(plant.name, plant_id=plant.plant_id)
        return InventoryItem(
            plant.name, row["seeds"], row["crops"], bool(row["locked"]),
            plant.plant_id,
        )

    def items(self) -> tuple[InventoryItem, ...]:
        rows = self._db.execute(
            "SELECT plant_id, name, seeds, crops, locked FROM inventory "
            "WHERE identity=? ORDER BY name, plant_id", (self._identity,),
        ).fetchall()
        return tuple(
            InventoryItem(
                r["name"], r["seeds"], r["crops"], bool(r["locked"]),
                r["plant_id"],
            )
            for r in rows
        )

    def stock(self, plant: Plant, seeds: int = 0, crops: int = 0) -> None:
        previous = self.item(plant)
        new_seeds, new_crops = previous.seeds + seeds, previous.crops + crops
        if min(new_seeds, new_crops) < 0:
            raise FarmError("insufficient_stock")
        integer(new_seeds)
        integer(new_crops)
        self._db.execute(
            "INSERT INTO inventory(identity, plant_id, name, seeds, crops) "
            "VALUES (?, ?, ?, ?, ?) ON CONFLICT(identity, plant_id) "
            "DO UPDATE SET name=excluded.name, seeds=excluded.seeds, "
            "crops=excluded.crops",
            (self._identity, plant.plant_id, plant.name, new_seeds, new_crops),
        )

    def lock(self, plant: Plant, locked: bool) -> None:
        self.stock(plant)
        self._db.execute(
            "UPDATE inventory SET locked=? WHERE identity=? AND plant_id=?",
            (int(locked), self._identity, plant.plant_id),
        )

    def plots(self) -> tuple[Plot, ...]:
        rows = self._db.execute(
            "SELECT * FROM plots WHERE identity=? ORDER BY slot",
            (self._identity,),
        ).fetchall()
        try:
            return tuple(
                Plot(
                    r["slot"],
                    Plant(**json.loads(r["plant"])) if r["plant"] else None,
                    r["mature_at"], r["harvest_count"],
                    r["yield_bonus"], r["experience_bonus"],
                    r["pest_count"], r["pest_spawned"], r["growth_remaining"],
                    r["growth_updated_at"], r["next_pest_at"],
                    r["maturity_pests"], r['stolen_count'], r['land_level'],
                )
                for r in rows
            )
        except (TypeError, ValueError) as exc:
            raise StorageError("invalid_plot_snapshot") from exc

    def save_plot(self, plot: Plot) -> None:
        data = (
            json.dumps(asdict(plot.plant), ensure_ascii=False)
            if plot.plant else None
        )
        cursor = self._db.execute(
            "UPDATE plots SET plant=?, mature_at=?, harvest_count=?, "
            "yield_bonus=?, experience_bonus=?, pest_count=?, pest_spawned=?, "
            "growth_remaining=?, growth_updated_at=?, next_pest_at=?, "
            "maturity_pests=?, stolen_count=?, land_level=? "
            "WHERE identity=? AND slot=?",
            (
                data, plot.mature_at, plot.harvest_count, plot.yield_bonus,
                plot.experience_bonus, plot.pest_count, plot.pest_spawned,
                plot.growth_remaining, plot.growth_updated_at,
                plot.next_pest_at, plot.maturity_pests, plot.stolen_count,
                plot.land_level, self._identity, plot.slot,
            ),
        )
        if cursor.rowcount != 1:
            raise FarmError("unknown_plot")

    def for_identity(self, identity):
        """同一事务内访问目标账户，禁止独立提交。"""
        return SQLiteRepository(self._db, identity.key, self._operation_id,
                                self._action, self._now)

    def theft_seen(self, slot, thief):
        return self._db.execute(
            'SELECT 1 FROM thefts WHERE owner=? AND slot=? AND thief=?',
            (self._identity, slot, thief.key),
        ).fetchone() is not None

    def record_theft(self, slot, thief):
        self._db.execute('INSERT INTO thefts VALUES (?, ?, ?)',
                         (self._identity, slot, thief.key))

    def clear_thefts(self, slot):
        self._db.execute('DELETE FROM thefts WHERE owner=? AND slot=?',
                         (self._identity, slot))

    def successful_thefts(self, day_start):
        return self._db.execute(
            "SELECT COUNT(*) FROM operations WHERE identity=? "
            "AND action='steal' AND created_at>=? AND created_at<? "
            "AND json_extract(result, '$.quantity')>0",
            (self._identity, day_start, day_start+86400),
        ).fetchone()[0]
