#!/usr/bin/env python3
r"""
一次性运行 OCR 并将结果写入记忆系统，用于快速复测。

用法:
  python scripts\run_ocr_once.py <image_path> [--user USER_ID] [--doc DOCUMENT_TYPE]

示例:
  python scripts\run_ocr_once.py i:\A2A\3\A2AServer\backend\uploads\1a30df8c-d86e-45f4-8260-748192d41fa2.jpg --user 111 --doc 检验单
"""

import os
import sys
import base64
import argparse
import asyncio

# 保证可以导入 backend 包
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.HealthRecordsManager.mcpserver.ocr_tool import (
    call_local_ocr, call_aliyun_ocr, call_aliyun_ocr_v2021
)
from backend.HealthRecordsManager.memory_service import HealthRecordsMemoryService


def read_image_base64(path: str) -> str:
    with open(path, 'rb') as f:
        return base64.b64encode(f.read()).decode('utf-8')


async def main():
    parser = argparse.ArgumentParser(description='Run OCR once and store memory')
    parser.add_argument('image_path', help='图片文件路径')
    parser.add_argument('--user', dest='user_id', default='111', help='用户ID，默认111')
    parser.add_argument('--doc', dest='document_type', default='检验单', help='文档类型，默认检验单')
    args = parser.parse_args()

    image_path = args.image_path
    user_id = args.user_id
    document_type = args.document_type

    if not os.path.exists(image_path):
        print(f'[ERROR] 文件不存在: {image_path}')
        sys.exit(1)

    print(f'[INFO] 读取图片并进行 OCR: {image_path}')
    image_b64 = read_image_base64(image_path)

    provider = os.getenv('OCR_PROVIDER', 'local').lower()
    version = os.getenv('ALIYUN_OCR_VERSION', '2021-07-07')
    print(f'[INFO] OCR_PROVIDER={provider}, ALIYUN_OCR_VERSION={version}')

    if provider.startswith('aliyun'):
        if version == '2021-07-07':
            ocr_text = call_aliyun_ocr_v2021(image_b64)
        else:
            ocr_text = call_aliyun_ocr(image_b64)
    else:
        ocr_text = call_local_ocr(image_b64)

    # 简单提取置信度（如果是错误消息，设置较低置信度）
    confidence = 0.85
    if isinstance(ocr_text, str) and ('失败' in ocr_text or '不可用' in ocr_text or '未安装' in ocr_text):
        confidence = 0.4

    print('[INFO] OCR 识别结果预览（前300字符）：')
    preview = (ocr_text or '')
    print(preview[:300])

    print('[INFO] 初始化记忆服务并存储 OCR 结果...')
    service = HealthRecordsMemoryService()
    ok = await service.initialize()
    if not ok:
        print('[ERROR] 记忆系统初始化失败')
        sys.exit(2)

    memory_id = await service.store_ocr_result(
        user_id=user_id,
        document_type=document_type,
        ocr_text=ocr_text,
        extracted_info={},
        confidence=confidence,
        file_path=image_path,
    )

    if not memory_id:
        print('[ERROR] 记忆存储失败')
        sys.exit(3)

    print(f'[OK] 记忆写入成功，memory_id={memory_id}')


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print('Interrupted')