#!/usr/bin/env python3
"""
健康档案管理API服务器启动脚本

使用方法:
    python start_health_api.py

或者指定端口:
    python start_health_api.py --port 8001
"""

import argparse
import logging
import sys
from pathlib import Path

# 添加当前目录到Python路径
sys.path.insert(0, str(Path(__file__).parent))


def setup_logging(log_level: str = "INFO"):
    """设置日志配置"""
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('health_api.log')
        ]
    )


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='启动健康档案管理API服务器')
    parser.add_argument('--host', default='0.0.0.0', help='服务器主机地址')
    parser.add_argument('--port', type=int, default=8000, help='服务器端口')
    parser.add_argument(
        '--log-level',
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='日志级别',
    )
    parser.add_argument(
        '--reload',
        action='store_true',
        help='启用自动重载（开发模式）',
    )

    args = parser.parse_args()

    # 设置日志
    setup_logging(args.log_level)
    logger = logging.getLogger(__name__)

    try:
        logger.info("正在启动健康档案管理API服务器...")
        logger.info(f"服务器地址: {args.host}:{args.port}")
        logger.info(f"日志级别: {args.log_level}")

        # 检查必要的目录
        upload_dir = Path("uploads")
        upload_dir.mkdir(exist_ok=True)
        logger.info(f"上传目录: {upload_dir.absolute()}")

        # 导入并启动应用
        import uvicorn
        from api.main import app

        # 启动服务器
        uvicorn.run(
            app,
            host=args.host,
            port=args.port,
            reload=args.reload,
            log_level=args.log_level.lower()
        )

    except KeyboardInterrupt:
        logger.info("收到中断信号，正在关闭服务器...")
    except Exception as e:
        logger.error(f"启动服务器失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
