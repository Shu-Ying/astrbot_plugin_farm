"""只读旧玩家库并在调用方事务内转换单个用户。"""

from contextlib import closing
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sqlite3

from .domain import Asset, FarmError, Plot, integer, text
from .repository import SQLiteRepository


def migration_id(user_id):
    return 'legacy-v1:' + hashlib.sha256(user_id.encode()).hexdigest()


def read_user(path, user_id):
    path = Path(path).resolve()
    if not path.is_file():
        return None
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        db.execute('BEGIN')
        tables = {row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        required = {'user', 'userSeed', 'userPlant', 'userSoil'}
        if not required <= tables:
            raise FarmError('legacy_schema_unsupported')
        users = db.execute(
            'SELECT * FROM user WHERE uid=?', (user_id,),
        ).fetchall()
        if not users:
            return None
        if len(users) != 1:
            raise FarmError('legacy_data_invalid')
        archive = {}
        for table in sorted(tables):
            quoted = '"' + table.replace('"', '""') + '"'
            columns = {row[1] for row in db.execute(
                f'PRAGMA table_info({quoted})'
            )}
            if 'uid' in columns:
                archive[table] = [dict(row) for row in db.execute(
                    f'SELECT * FROM {quoted} WHERE uid=?', (user_id,),
                )]
        return archive


def legacy_plot(row, catalogue):
    slot = integer(row['soilIndex'], 1, 10_000)
    level = integer(row['soilLevel'], 0, 3)
    bonuses = dict(yield_bonus=(10, 10, 20, 28)[level],
                   experience_bonus=28 if level == 3 else 0)
    planted = row['isSoilPlanted']
    if planted not in (None, 0, 1):
        raise FarmError('legacy_data_invalid')
    if not row['plantName']:
        if planted == 1:
            raise FarmError('legacy_data_invalid')
        return Plot(slot, **bonuses)
    plant = catalogue.get(row['plantName'])
    count = integer(row['harvestCount'])
    wilted = integer(row['wiltStatus'], 0, 1)
    pests = integer(row['bugStatus'], 0, 1)
    mature = integer(row['matureTime'])
    return Plot(
        slot, plant, mature, max(count, plant.crop) if wilted else count,
        **bonuses, pest_count=pests, pest_spawned=pests,
        maturity_pests=pests,
    )


def import_user(db, identity, archive, catalogue, now):
    operation = migration_id(identity.user_id)
    if db.execute('SELECT 1 FROM accounts WHERE identity=?',
                  (identity.key,)).fetchone():
        raise FarmError('legacy_account_conflict')
    user = archive['user'][0]
    text(user['name'], 64)
    slots = integer(user['soil'], 1, 10_000)
    balances = {
        Asset.POINT: integer(user['point']),
        Asset.VIP_POINT: integer(user['vipPoint']),
        Asset.EXPERIENCE: integer(user['exp']),
    }
    db.execute('INSERT INTO accounts(identity, name) VALUES (?, ?)',
               (identity.key, user['name']))
    repo = SQLiteRepository(db, identity.key, operation, 'legacy_import', now)
    for asset, balance in balances.items():
        repo.asset(asset, balance)
    inventory = set()
    for table, name, quantity in (
        ('userSeed', 'seed', 'seeds'), ('userPlant', 'plant', 'crops'),
    ):
        for row in archive[table]:
            plant = catalogue.get(row[name])
            key = (plant.plant_id, quantity)
            if key in inventory:
                raise FarmError('legacy_data_invalid')
            inventory.add(key)
            repo.stock(plant, **{quantity: integer(row['count'])})
            if table == 'userPlant':
                repo.lock(plant, integer(row['isLock']) != 0)
    plots = {}
    for row in archive['userSoil']:
        plot = legacy_plot(row, catalogue)
        if plot.slot in plots or plot.slot > slots:
            raise FarmError('legacy_data_invalid')
        plots[plot.slot] = plot
    db.executemany('INSERT INTO plots(identity, slot) VALUES (?, ?)',
                   [(identity.key, slot) for slot in range(1, slots + 1)])
    for plot in plots.values():
        repo.save_plot(plot)
    result = {
        'migration_version': 1, 'account': asdict(repo.account()),
        'legacy_rows': archive,
        'unsupported_tables': sorted(set(archive) - {
            'user', 'userSeed', 'userPlant', 'userSoil',
        }),
    }
    db.execute(
        'INSERT INTO operations VALUES (?, ?, ?, ?, ?, ?)',
        (identity.key, operation, 'legacy_import', operation,
         json.dumps(result, ensure_ascii=False), now),
    )
    return True
