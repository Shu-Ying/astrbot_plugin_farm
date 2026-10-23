"""离线演示；只有显式调用才创建指定数据库。"""

import argparse
import asyncio
import logging
from pathlib import Path

from . import Catalogue, FarmService, Identity, SQLiteStore
from .presentation import receipt_text, snapshot_text


async def demo(database):
    clock = [0]
    catalogue = Catalogue.bundled()
    plant = min(
        (p for p in catalogue if p.level == 0 and not p.is_vip),
        key=lambda p: p.cost,
    )
    store = SQLiteStore(database)
    await store.initialize()
    service = FarmService(store, catalogue, lambda: clock[0])
    identity = Identity("demo", "local", "local", "farmer")
    try:
        for receipt in (
            await service.register(identity, "演示农场", "demo-register"),
            await service.buy(identity, plant.name, 1, "demo-buy"),
            await service.sow(identity, plant.name, 1, "demo-sow"),
        ):
            print(receipt_text(receipt))
        clock[0] = plant.growth_seconds
        print(receipt_text(await service.harvest(identity, "demo-harvest")))
        print(receipt_text(await service.sell(
            identity, None, None, "demo-sell",
        )))
        print(snapshot_text(await service.snapshot(identity)))
    finally:
        await store.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True)
    args = parser.parse_args()
    database = Path(args.database).resolve()
    database.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=database.with_suffix(".log"), encoding="utf-8",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    asyncio.run(demo(database))


if __name__ == "__main__":
    main()
