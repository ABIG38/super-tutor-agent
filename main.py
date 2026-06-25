import sys
import os

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from backend.config import init_logging
from frontend.desktop_app import main

if __name__ == "__main__":
    # ★ 最早初始化日志（在其他模块 import 前）
    init_logging()
    main()
