import asyncio
import time

from astrbot.api import logger


class Signal:
    def __init__(self):
        self._slots = []  # 绑定的槽函数列表
        self._onceSlots = []  # 只触发一次的槽函数列表

    def connect(self, slot, priority=0):
        if callable(slot) and not any(s[0] == slot for s in self._slots):
            self._slots.append((slot, priority))
            self._slots.sort(key=lambda x: -x[1])

    def connectOnce(self, slot, priority=0):
        if callable(slot) and not any(s[0] == slot for s in self._onceSlots):
            self._onceSlots.append((slot, priority))
            self._onceSlots.sort(key=lambda x: -x[1])

    def disconnect(self, slot):
        self._slots = [s for s in self._slots if s[0] != slot]
        self._onceSlots = [s for s in self._onceSlots if s[0] != slot]

    async def emit(self, *args, **kwargs):
        slots = list(self._slots)
        onceSlots = list(self._onceSlots)
        self._onceSlots.clear()

        for slot, _ in slots + onceSlots:
            startTime = time.time()
            try:
                if asyncio.iscoroutinefunction(slot):
                    await slot(*args, **kwargs)
                else:
                    slot(*args, **kwargs)
                duration = (time.time() - startTime) * 1000
                logger.debug(f"事件槽 {slot.__name__} 执行完成，耗时 {duration:.2f} ms")
            except Exception as e:
                logger.warning(f"事件槽 {slot.__name__} 触发异常: {e}")


class FarmEventManager:
    def __init__(self):
        self.m_beforePlant = Signal()
        """播种前信号

        Args:
            uid (str): 用户Uid
            name (str): 播种种子名称
            num (int): 播种数量
        """

        self.m_afterPlant = Signal()
        """播种后信号 每块地播种都会触发该信号

        Args:
            uid (str): 用户Uid
            name (str): 播种种子名称
            soilIndex (int): 播种地块索引 从1开始
        """

        self.m_beforeHarvest = Signal()
        """收获前信号

        Args:
            uid (str): 用户Uid
        """

        self.m_afterHarvest = Signal()
        """收获后信号 每块地收获都会触发该信号

        Args:
            uid (str): 用户Uid
            name (str): 收获作物名称
            num (int): 收获数量
            soilIndex (int): 收获地块索引 从1开始
        """

        self.m_beforeEradicate = Signal()
        """铲除前信号

        Args:
            uid (str): 用户Uid
        """

        self.m_afterEradicate = Signal()
        """铲除后信号 每块地铲除都会触发该信号

        Args:
            uid (str): 用户Uid
            soilIndex (index): 铲除地块索引 从1开始
        """

        self.m_beforeExpand = Signal()
        self.m_afterExpand = Signal()
        self.m_beforeSteal = Signal()
        self.m_afterSteal = Signal()


g_pEventManager = FarmEventManager()
