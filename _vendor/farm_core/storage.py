"""显式初始化的 SQLite 存储；每个用例独占一条事务连接。"""

import asyncio
from contextlib import closing, contextmanager
import hashlib
import json
import logging
from pathlib import Path
import sqlite3

from .domain import (
    FarmError, Identity, Receipt, SchemaError, Snapshot, StorageError,
)
from .repository import SQLiteRepository
from .catalogue import Catalogue

LOGGER = logging.getLogger(__name__)
APPLICATION_ID = 0x4641524D
SCHEMA_VERSION = 5

PEST_COLUMNS = {
    "pest_count": (
        "INTEGER NOT NULL DEFAULT 0 CHECK(pest_count BETWEEN 0 AND 3)"
    ),
    "pest_spawned": (
        "INTEGER NOT NULL DEFAULT 0 CHECK(pest_spawned BETWEEN 0 AND 3)"
    ),
    "growth_remaining": "INTEGER CHECK(growth_remaining>=0)",
    "growth_updated_at": "INTEGER",
    "next_pest_at": "INTEGER",
    "maturity_pests": (
        "INTEGER NOT NULL DEFAULT 0 CHECK(maturity_pests BETWEEN 0 AND 3)"
    ),
}

SCHEMA = (
    """CREATE TABLE accounts(
        identity TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        point INTEGER NOT NULL DEFAULT 0
            CHECK(typeof(point)='integer' AND point>=0),
        vip_point INTEGER NOT NULL DEFAULT 0
            CHECK(typeof(vip_point)='integer' AND vip_point>=0),
        experience INTEGER NOT NULL DEFAULT 0
            CHECK(typeof(experience)='integer' AND experience>=0)
    )""",
    """CREATE TABLE operations(
        identity TEXT NOT NULL REFERENCES accounts(identity),
        operation_id TEXT NOT NULL,
        action TEXT NOT NULL,
        fingerprint TEXT NOT NULL,
        result TEXT NOT NULL,
        created_at INTEGER NOT NULL,
        PRIMARY KEY(identity, operation_id)
    )""",
    """CREATE TABLE inventory(
        identity TEXT NOT NULL REFERENCES accounts(identity),
        plant_id INTEGER NOT NULL CHECK(plant_id>0),
        name TEXT NOT NULL,
        seeds INTEGER NOT NULL DEFAULT 0
            CHECK(typeof(seeds)='integer' AND seeds>=0),
        crops INTEGER NOT NULL DEFAULT 0
            CHECK(typeof(crops)='integer' AND crops>=0),
        locked INTEGER NOT NULL DEFAULT 0 CHECK(locked IN (0,1)),
        PRIMARY KEY(identity, plant_id)
    )""",
    """CREATE TABLE plots(
        identity TEXT NOT NULL REFERENCES accounts(identity),
        slot INTEGER NOT NULL CHECK(slot>0),
        plant TEXT,
        mature_at INTEGER,
        harvest_count INTEGER NOT NULL DEFAULT 0 CHECK(harvest_count>=0),
        yield_bonus INTEGER NOT NULL DEFAULT 0,
        experience_bonus INTEGER NOT NULL DEFAULT 0,
        stolen_count INTEGER NOT NULL DEFAULT 0 CHECK(stolen_count>=0),
        land_level INTEGER NOT NULL DEFAULT 0 CHECK(land_level BETWEEN 0 AND 3),
        """ + ",\n        ".join(
            f"{name} {definition}" for name, definition in PEST_COLUMNS.items()
        ) + """,
        PRIMARY KEY(identity, slot)
    )""",
    """CREATE TABLE thefts(
        owner TEXT NOT NULL,
        slot INTEGER NOT NULL,
        thief TEXT NOT NULL REFERENCES accounts(identity),
        PRIMARY KEY(owner, slot, thief),
        FOREIGN KEY(owner, slot) REFERENCES plots(identity, slot)
    )""",
    """CREATE TABLE ledger(
        id INTEGER PRIMARY KEY,
        identity TEXT NOT NULL,
        operation_id TEXT NOT NULL,
        asset TEXT NOT NULL
            CHECK(asset IN ('point','vip_point','experience')),
        delta INTEGER NOT NULL CHECK(typeof(delta)='integer' AND delta!=0),
        reason TEXT NOT NULL,
        created_at INTEGER NOT NULL,
        FOREIGN KEY(identity, operation_id)
            REFERENCES operations(identity, operation_id)
            DEFERRABLE INITIALLY DEFERRED
    )""",
)


class SQLiteStore:
    async def catalogue_ids(self):
        """初始化前只读检查库存与地块ID；不创建文件或迁移数据库。"""
        task = asyncio.create_task(asyncio.to_thread(self._catalogue_ids))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            try:
                await task
            except Exception:
                pass
            raise

    def _catalogue_ids(self):
        if not self.path.is_file():
            return set()
        with closing(sqlite3.connect(
                self.path.as_uri() + '?mode=ro', uri=True)) as connection:
            connection.execute('BEGIN')
            app = connection.execute('PRAGMA application_id').fetchone()[0]
            version = connection.execute('PRAGMA user_version').fetchone()[0]
            tables = {row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'",
            )}
            if app == 0 and version == 0 and not tables:
                return set()
            if app != APPLICATION_ID or not 1 <= version <= SCHEMA_VERSION:
                raise SchemaError('Unsupported farm database')
            result = set()
            if version >= 2:
                result.update(row[0] for row in connection.execute(
                    'SELECT DISTINCT plant_id FROM inventory '
                    'WHERE seeds>0 OR crops>0',
                ))
            for row in connection.execute(
                    'SELECT plant FROM plots WHERE plant IS NOT NULL'):
                try:
                    result.add(json.loads(row[0])['plant_id'])
                except (KeyError, TypeError, ValueError) as error:
                    raise SchemaError('Invalid saved crop definition') \
                        from error
            if any(type(value) is not int or value <= 0 for value in result):
                raise SchemaError('Invalid saved crop ID')
            return result

    def __init__(self, path: str | Path, timeout: float = 10):
        if str(path) == ":memory:":
            raise ValueError("Use a dedicated file for transaction connections")
        self.path = Path(path).resolve()
        self._timeout = timeout
        self._ready = False
        self._pending = set()
        self._lifecycle = asyncio.Lock()

    async def _offload(self, function):
        task = asyncio.create_task(asyncio.to_thread(function))
        self._pending.add(task)

        def finished(completed):
            self._pending.discard(completed)
            if not completed.cancelled():
                completed.exception()

        task.add_done_callback(finished)
        return await asyncio.shield(task)

    @contextmanager
    def _connection(self):
        try:
            with closing(sqlite3.connect(
                self.path, timeout=self._timeout, isolation_level=None,
            )) as connection:
                connection.row_factory = sqlite3.Row
                connection.execute("PRAGMA foreign_keys=ON")
                yield connection
        except sqlite3.Error as exc:
            raise StorageError("sqlite_failure") from exc

    @staticmethod
    def _validate(connection, expected_version=SCHEMA_VERSION):
        app_id = connection.execute("PRAGMA application_id").fetchone()[0]
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        tables = {
            r[0] for r in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        expected = {"accounts", "operations", "inventory", "plots", "ledger"}
        if expected_version >= 4:
            expected.add('thefts')
        if (
            app_id != APPLICATION_ID or version != expected_version
            or tables != expected
        ):
            raise SchemaError("unsupported_database_schema")

    async def initialize(self, catalogue: Catalogue | None = None) -> None:
        async with self._lifecycle:
            await self._offload(lambda: self._initialize(catalogue))
            self._ready = True

    @staticmethod
    def _migrate_inventory(connection, catalogue):
        names = {}
        for plant in catalogue:
            names.setdefault(plant.name, set()).add(plant.plant_id)
        for row in connection.execute(
            "SELECT plant FROM plots WHERE plant IS NOT NULL"
        ):
            try:
                plant = json.loads(row[0])
                name, plant_id = plant["name"], plant["plant_id"]
                if (not isinstance(name, str) or type(plant_id) is not int
                        or plant_id < 1):
                    raise ValueError()
                names.setdefault(name, set()).add(plant_id)
            except (KeyError, TypeError, ValueError) as exc:
                raise SchemaError("invalid_plot_snapshot") from exc
        rows = connection.execute("SELECT * FROM inventory").fetchall()
        migrated = []
        for row in rows:
            ids = names.get(row["name"], set())
            if len(ids) != 1:
                raise SchemaError("inventory_identity_unresolved")
            migrated.append((
                row["identity"], next(iter(ids)), row["name"],
                row["seeds"], row["crops"], row["locked"],
            ))
        statement = next(
            sql for sql in SCHEMA if sql.startswith("CREATE TABLE inventory(")
        )
        connection.execute(statement.replace("inventory(", "inventory_v2(", 1))
        connection.executemany(
            "INSERT INTO inventory_v2 VALUES (?, ?, ?, ?, ?, ?)", migrated,
        )
        connection.execute("DROP TABLE inventory")
        connection.execute("ALTER TABLE inventory_v2 RENAME TO inventory")
        connection.execute("PRAGMA user_version=2")
        return len(rows)

    def _initialize(self, catalogue=None):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            migrated_rows = None
            migrated_pests = False
            try:
                app = connection.execute("PRAGMA application_id").fetchone()[0]
                version = connection.execute(
                    "PRAGMA user_version"
                ).fetchone()[0]
                tables = connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
                if app == 0 and version == 0 and not tables:
                    for statement in SCHEMA:
                        connection.execute(statement)
                    connection.execute(
                        f"PRAGMA application_id={APPLICATION_ID}"
                    )
                    connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
                elif app == APPLICATION_ID and version == 1:
                    self._validate(connection, expected_version=1)
                    migration_catalogue = (
                        catalogue if catalogue is not None
                        else Catalogue.bundled()
                    )
                    migrated_rows = self._migrate_inventory(
                        connection,
                        migration_catalogue,
                    )
                    version = 2
                if app == APPLICATION_ID and version == 2:
                    self._validate(connection, expected_version=2)
                    for name, definition in PEST_COLUMNS.items():
                        connection.execute(
                            f"ALTER TABLE plots ADD COLUMN {name} {definition}"
                        )
                    connection.execute("PRAGMA user_version=3")
                    migrated_pests = True
                    version = 3
                if app == APPLICATION_ID and version == 3:
                    self._validate(connection, expected_version=3)
                    connection.execute(
                        'ALTER TABLE plots ADD COLUMN stolen_count '
                        'INTEGER NOT NULL DEFAULT 0 CHECK(stolen_count>=0)'
                    )
                    connection.execute(next(
                        sql for sql in SCHEMA
                        if sql.startswith('CREATE TABLE thefts(')
                    ))
                    connection.execute('PRAGMA user_version=4')
                    LOGGER.info('farm schema migrated version=4 theft=enabled')
                    version = 4
                if app == APPLICATION_ID and version == 4:
                    self._validate(connection, expected_version=4)
                    connection.execute(
                        'ALTER TABLE plots ADD COLUMN land_level '
                        'INTEGER NOT NULL DEFAULT 0 '
                        'CHECK(land_level BETWEEN 0 AND 3)'
                    )
                    # 从已保留的迁移原始记录恢复等级，不按收益加成猜测。
                    for row in connection.execute(
                        "SELECT identity, result FROM operations "
                        "WHERE action='legacy_import'"
                    ).fetchall():
                        try:
                            archive = json.loads(row['result'])
                            soils = archive['legacy_rows'].get('userSoil', [])
                            for soil in soils:
                                level = soil['soilLevel']
                                slot = soil['soilIndex']
                                if (type(level) is not int
                                        or not 0 <= level <= 3
                                        or type(slot) is not int or slot < 1):
                                    raise ValueError('Invalid legacy soil')
                                connection.execute(
                                    'UPDATE plots SET land_level=? '
                                    'WHERE identity=? AND slot=?',
                                    (level, row['identity'], slot),
                                )
                        except (KeyError, TypeError, ValueError) as error:
                            raise SchemaError('legacy_land_invalid') from error
                    connection.execute('PRAGMA user_version=5')
                    LOGGER.info('farm schema migrated version=5 land=enabled')
                self._validate(connection)
                connection.commit()
                if migrated_rows is not None:
                    LOGGER.info(
                        "farm schema migrated version=4 inventory_rows=%s",
                        migrated_rows,
                    )
                elif migrated_pests:
                    LOGGER.info("farm schema migrated version=4 pests=enabled")
            except BaseException:
                connection.rollback()
                LOGGER.warning("farm schema initialization rolled back")
                raise

    async def close(self) -> None:
        async with self._lifecycle:
            self._ready = False
            pending = tuple(self._pending)
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)

    def _ensure_ready(self):
        if not self._ready:
            raise StorageError("store_not_initialized_or_closed")

    async def migrate_legacy(self, source, identity, catalogue, now):
        from .legacy import import_user, migration_id, read_user

        self._ensure_ready()

        def execute():
            with self._connection() as connection:
                self._validate(connection)
                connection.execute('BEGIN IMMEDIATE')
                try:
                    bound = connection.execute(
                        "SELECT identity FROM operations "
                        "WHERE operation_id=? AND action='legacy_import'",
                        (migration_id(identity.user_id),),
                    ).fetchall()
                    if bound:
                        if any(row[0] != identity.key for row in bound):
                            raise FarmError('legacy_identity_bound')
                        connection.commit()
                        return False
                    archive = read_user(source, identity.user_id)
                    migrated = bool(archive) and import_user(
                        connection, identity, archive, catalogue, now,
                    )
                    connection.commit()
                    if migrated:
                        LOGGER.info(
                            'farm legacy migration committed operation=%s '
                            'tables=%s', migration_id(identity.user_id),
                            {name: len(rows) for name, rows in archive.items()},
                        )
                    return migrated
                except BaseException:
                    connection.rollback()
                    LOGGER.exception(
                        'farm legacy migration rolled back operation=%s',
                        migration_id(identity.user_id),
                    )
                    raise

        return await self._offload(execute)

    async def transact(
        self, identity: Identity, operation_id: str, action: str,
        parameters: dict, now: int, operation,
    ) -> Receipt:
        self._ensure_ready()
        request = json.dumps(
            {"action": action, "parameters": parameters},
            ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        )
        fingerprint = hashlib.sha256(request.encode("utf-8")).hexdigest()

        def execute():
            with self._connection() as connection:
                self._validate(connection)
                connection.execute("BEGIN IMMEDIATE")
                try:
                    existing = connection.execute(
                        "SELECT fingerprint, result FROM operations "
                        "WHERE identity=? AND operation_id=?",
                        (identity.key, operation_id),
                    ).fetchone()
                    if existing:
                        if existing["fingerprint"] != fingerprint:
                            raise FarmError("operation_conflict")
                        result = json.loads(existing["result"])
                    else:
                        repository = SQLiteRepository(
                            connection, identity.key, operation_id, action, now,
                        )
                        result = operation(repository)
                        connection.execute(
                            "INSERT INTO operations VALUES (?, ?, ?, ?, ?, ?)",
                            (
                                identity.key, operation_id, action, fingerprint,
                                json.dumps(result, ensure_ascii=False), now,
                            ),
                        )
                    connection.commit()
                except BaseException as exc:
                    connection.rollback()
                    LOGGER.log(
                        logging.INFO if isinstance(exc, FarmError)
                        else logging.WARNING,
                        "farm rollback action=%s operation=%s error=%s",
                        action, operation_id, type(exc).__name__,
                    )
                    raise
            LOGGER.info(
                "farm committed action=%s operation=%s", action, operation_id,
            )
            return Receipt(operation_id, action, result)

        return await self._offload(execute)

    async def snapshot(self, identity: Identity) -> Snapshot:
        self._ensure_ready()

        def query():
            with self._connection() as connection:
                self._validate(connection)
                connection.execute("BEGIN")
                repository = SQLiteRepository(
                    connection, identity.key, "", "query", 0,
                )
                result = Snapshot(
                    repository.account(), repository.items(),
                    repository.plots(),
                )
                connection.commit()
                return result

        return await self._offload(query)

    async def ledger(self, identity: Identity) -> tuple[dict, ...]:
        self._ensure_ready()

        def query():
            with self._connection() as connection:
                self._validate(connection)
                rows = connection.execute(
                    "SELECT operation_id, asset, delta, reason, created_at "
                    "FROM ledger WHERE identity=? ORDER BY id",
                    (identity.key,),
                ).fetchall()
                return tuple(dict(row) for row in rows)

        return await self._offload(query)
