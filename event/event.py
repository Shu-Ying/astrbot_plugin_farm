import inspect
import time

from astrbot.api import logger


class Signal:
    def __set_name__(self, owner, name):
        self.name = name

    def __get__(self, instance, owner):
        if instance is None:
            return self
        bound = instance.__dict__.get(self.name)
        if bound is None:
            bound = _SignalBound()
            instance.__dict__[self.name] = bound
        return bound


class _SignalBound:
    def __init__(self):
        self._slots = []
        self._onceSlots = []

    def connect(self, func=None, *, priority=0):
        if func is None:
            return lambda f: self.connect(f, priority=priority)
        if callable(func) and not any(s[0] == func for s in self._slots):
            self._slots.append((func, priority))
            self._slots.sort(key=lambda x: -x[1])
        return func

    def connect_once(self, func=None, *, priority=0):
        if func is None:
            return lambda f: self.connect_once(f, priority=priority)
        if callable(func) and not any(s[0] == func for s in self._onceSlots):
            self._onceSlots.append((func, priority))
            self._onceSlots.sort(key=lambda x: -x[1])
        return func

    def disconnect(self, func):
        self._slots = [s for s in self._slots if s[0] != func]
        self._onceSlots = [s for s in self._onceSlots if s[0] != func]

    async def emit(self, *args, **kwargs):
        slots = list(self._slots)
        onceSlots = list(self._onceSlots)
        self._onceSlots.clear()
        for slot, _ in slots + onceSlots:
            start = time.time()
            try:
                if inspect.iscoroutinefunction(slot):
                    await slot(*args, **kwargs)
                else:
                    slot(*args, **kwargs)
                logger.debug(
                    f"【真寻农场】事件槽 {slot.__name__} 执行完成，耗时 {(time.time() - start) * 1000:.2f} ms"
                )
            except Exception as e:
                logger.warning(f"事件槽 {slot.__name__} 触发异常: {e}")


class FarmEventManager:
    m_beforePlant = Signal()
    """播种前信号

    Args:
        uid (str): 用户Uid
        name (str): 播种种子名称
        num (int): 播种数量
    """

    m_afterPlant = Signal()
    """播种后信号 每块地播种都会触发该信号

    Args:
        uid (str): 用户Uid
        name (str): 播种种子名称
        soilIndex (int): 播种地块索引 从1开始
    """

    m_beforeHarvest = Signal()
    """收获前信号

    Args:
        uid (str): 用户Uid
    """

    m_afterHarvest = Signal()
    """收获后信号 每块地收获都会触发该信号

    Args:
        uid (str): 用户Uid
        name (str): 收获作物名称
        num (int): 收获数量
        soilIndex (int): 收获地块索引 从1开始
    """

    m_beforeEradicate = Signal()
    """铲除前信号

    Args:
        uid (str): 用户Uid
    """

    m_afterEradicate = Signal()
    """铲除后信号 每块地铲除都会触发该信号

    Args:
        uid (str): 用户Uid
        soilIndex (index): 铲除地块索引 从1开始
    """

    m_beforeExpand = Signal()
    m_afterExpand = Signal()
    m_beforeSteal = Signal()
    m_afterSteal = Signal()

    m_dit = Signal()


g_pEventManager = FarmEventManager()
