"""AstrBot拥有日志配置和输出，插件不创建或关闭任何日志处理器。"""


def open_logs(data_dir):
    return None, None


def close_logs(file_handler, console_handler):
    pass
