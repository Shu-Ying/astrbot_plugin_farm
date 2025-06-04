from pathlib import Path


class Config:
    # 绘制农场清晰度
    sFarmDrawQuality: str

    # 服务器地址
    sFarmServerUrl: str

    # 指令前綴
    sFarmPrefix: str

    # 签到状态
    bSignStatus = True

    # 是否处于Debug模式
    bIsDebug = True

    # 数据库文件目录
    sDBPath = (
        Path(__file__).resolve().parent.parent.parent / "astrbot_plugin_farm/farm_db"
    )
    # 数据库文件路径
    sDBFilePath = sDBPath / "farm.db"

    # 农场资源文件目录
    sResourcePath = Path(__file__).resolve().parent / "resource"

    # 农场作物数据库
    sPlantPath = sResourcePath / "db/plant.db"

    # 农场配置文件目录
    sConfigPath = Path(__file__).resolve().parent / "config"

    # 农场签到文件路径
    sSignInPath = sConfigPath / "sign_in.json"


g_pConfigManager = Config()
