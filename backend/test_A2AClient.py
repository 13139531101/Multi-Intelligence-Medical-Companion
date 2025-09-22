#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Date  : 2025/5/8 14:58
# @File  : test_A2AClient.py.py
# @Author: johnson
# @Contact : github: johnson7788
# @Desc  : A2A测试用例

import asyncio
import base64
import os
import urllib
import sys
from uuid import uuid4
import json
import unittest
import random
import string
from unittest.mock import patch, AsyncMock  # Import patch and AsyncMock for mocking

# Assuming these modules are available in your environment
from A2AServer.common.client import A2AClient, A2ACardResolver
from A2AServer.common.A2Atypes import TaskState, Task, TextPart, FilePart, FileContent, AgentCard


class A2AClientTestCase(unittest.IsolatedAsyncioTestCase):
    """
    测试 A2A 客户端的功能
    """
    AGENT_URL = "http://localhost:10004"
    if os.environ.get("AGENT_URL"):
        AGENT_URL = os.environ.get("AGENT_URL")
    async def asyncSetUp(self):
        """
        设置测试环境，初始化客户端等。
        使用环境变量或默认值配置 agent_url。
        """
        self.agent_url = self.AGENT_URL
        self.use_push_notifications_in_tests = False
        self.push_notification_receiver_url = os.environ.get("PUSH_RECEIVER_URL", "http://localhost:5000")
        self.client = None
        self.card = None
        self.notification_config = {}
        try:
            client_info = await self._initialize_client(
                agent_url=self.agent_url,
                use_push_notifications=self.use_push_notifications_in_tests,
            )
            self.client, self.card, self.notification_config = client_info
            self.streaming = self.card.capabilities.streaming
            self.use_push_notifications = self.notification_config.get("use_push_notifications", False)
            self.notification_receiver_host = self.notification_config.get("notification_receiver_host")
            self.notification_receiver_port = self.notification_config.get("notification_receiver_port")
        except Exception as e:
            self.fail(f"测试设置失败: 无法初始化客户端。错误信息: {e}")

    async def asyncTearDown(self):
        """
        清理测试环境，例如停止 push notification listener。
        """
        listener_to_stop = self.notification_config.get("push_notification_listener")
        if listener_to_stop and hasattr(listener_to_stop, 'stop'):
            try:
                print("尝试停止 push notification listener...")
                if asyncio.iscoroutinefunction(listener_to_stop.stop):
                    await listener_to_stop.stop()
                else:
                    listener_to_stop.stop()
                print("Push notification listener 已停止。")
            except Exception as e:
                print(f"停止 push notification listener 发生错误: {e}")

    async def _initialize_client(self, agent_url: str, use_push_notifications: bool):
        """
        初始化 A2A 客户端并解析 agent card。
        """
        print("初始化客户端...")
        try:
            card_resolver = A2ACardResolver(agent_url)
            card = card_resolver.get_agent_card()

            print("======= Agent Card ========")
            print(card.model_dump_json(exclude_none=True))
            print("===========================")

            notification_receiver_host = None
            notification_receiver_port = None

            client = A2AClient(agent_card=card)

            return client, card, {
                "use_push_notifications": use_push_notifications,
                "notification_receiver_host": notification_receiver_host,
                "notification_receiver_port": notification_receiver_port,
            }

        except Exception as e:
            print(f"客户端初始化失败: {e}")
            raise

    async def _send_prompt_and_get_result(self, client: A2AClient, agent_card_capabilities, prompt: str, session_id: str, task_id: str = None, file_path: str = "", use_push_notifications: bool = False, notification_receiver_host: str = None, notification_receiver_port: int = None):
        """
        发送单个 prompt 给 agent 并获取结果。
        """
        if task_id is None:
            task_id = uuid4().hex

        print(f"\n========= 发送任务 {task_id}，会话 {session_id} =========")
        print(f"Prompt: {prompt}")
        if file_path:
            print(f"尝试附加文件: {file_path}")

        message_parts = [
            {
                "type": "text",
                "text": prompt,
            }
        ]

        payload = {
            "id": task_id,
            "sessionId": session_id,
            "acceptedOutputModes": ["text"],
            "message": {
                "role": "user",
                "parts": message_parts
            },
        }

        streaming = agent_card_capabilities.streaming
        taskResult = None
        if streaming:
            print("流式响应:")
            response_stream = client.send_task_streaming(payload)
            full_text = ""
            async for result in response_stream:
                if result and result.result:
                    if getattr(result.result, "status", None):
                        if result.result.status.message:
                            for part in result.result.status.message.parts:
                                if isinstance(part, TextPart) and part.text:
                                    print(part.text, end="")
                                    full_text += part.text
                    sys.stdout.flush()
            print("\n流式响应结束。")
        taskResult = await client.get_task({"id": task_id})
        return taskResult

    async def test_send_prompt_and_get_result_rag(self):
        """
        测试发送 prompt 并获取结果的场景。
        遍历测试用例并断言结果不为空。
        """
        self.assertIsNotNone(self.client, "客户端未成功初始化")
        self.assertIsNotNone(self.card, "Agent Card 未成功获取")


        session_id = uuid4().hex
        test_scenarios = [
            # {"prompt": "什么是LNG?", "session_id": session_id},
            {"prompt": "小米最新新闻?", "session_id": session_id},
        ]
        print("\n--- 运行测试场景 ---")
        for i, scenario in enumerate(test_scenarios):
            print(f"\n--- 开始场景 {i+1}/{len(test_scenarios)} ---")
            current_task_id = uuid4().hex
            current_session_id = scenario.get("session_id", uuid4().hex)
            file_path_for_scenario = scenario.get("file_path", "")

            task_result = await self._send_prompt_and_get_result(
                client=self.client,
                agent_card_capabilities=self.card.capabilities,
                prompt=scenario["prompt"],
                session_id=current_session_id,
                task_id=current_task_id,
                file_path=file_path_for_scenario,
                use_push_notifications=self.use_push_notifications,
                notification_receiver_host=self.notification_receiver_host,
                notification_receiver_port=self.notification_receiver_port,
            )
            artifacts = task_result.result.artifacts
            for artifact in artifacts:
                parts = artifact.parts
                for part in parts:
                    print(part.text, end="")
            self.assertIsNotNone(task_result, f"场景 {i+1} 未能获取任务结果")
            self.assertIsNotNone(task_result.result, f"场景 {i+1} 的任务结果为空")
            print(f"\n--- 场景 {i+1} 测试完成 ---")

        print("\n--- 所有测试场景完成 ---")
    async def test_send_prompt_and_get_result_price(self):
        """
        测试发送 prompt 并获取结果的场景。
        遍历测试用例并断言结果不为空。
        """
        self.assertIsNotNone(self.client, "客户端未成功初始化")
        self.assertIsNotNone(self.card, "Agent Card 未成功获取")
        session_id = uuid4().hex
        test_scenarios = [
            {"prompt": "5月19日内蒙古利润时多少？", "session_id": session_id},
        ]
        print("\n--- 运行测试场景 ---")
        for i, scenario in enumerate(test_scenarios):
            print(f"\n--- 开始场景 {i+1}/{len(test_scenarios)} ---")
            current_task_id = uuid4().hex
            current_session_id = scenario.get("session_id", uuid4().hex)
            file_path_for_scenario = scenario.get("file_path", "")

            task_result = await self._send_prompt_and_get_result(
                client=self.client,
                agent_card_capabilities=self.card.capabilities,
                prompt=scenario["prompt"],
                session_id=current_session_id,
                task_id=current_task_id,
                file_path=file_path_for_scenario,
                use_push_notifications=self.use_push_notifications,
                notification_receiver_host=self.notification_receiver_host,
                notification_receiver_port=self.notification_receiver_port,
            )
            artifacts = task_result.result.artifacts
            for artifact in artifacts:
                parts = artifact.parts
                for part in parts:
                    print(part.text, end="")
            self.assertIsNotNone(task_result, f"场景 {i+1} 未能获取任务结果")
            self.assertIsNotNone(task_result.result, f"场景 {i+1} 的任务结果为空")
            print(f"\n--- 场景 {i+1} 测试完成 ---")

        print("\n--- 所有测试场景完成 ---")
    async def test_send_prompt_and_get_result_lng1(self):
        """
        测试发送 prompt 并获取结果的场景。
        遍历测试用例并断言结果不为空。
        """
        self.assertIsNotNone(self.client, "客户端未成功初始化")
        self.assertIsNotNone(self.card, "Agent Card 未成功获取")
        session_id = uuid4().hex
        test_scenarios = [
            {"prompt": "目前浙江地区LNG送到价格是多少？", "session_id": session_id},
        ]
        print("\n--- 运行测试场景 ---")
        for i, scenario in enumerate(test_scenarios):
            print(f"\n--- 开始场景 {i+1}/{len(test_scenarios)} ---")
            current_task_id = uuid4().hex
            current_session_id = scenario.get("session_id", uuid4().hex)
            file_path_for_scenario = scenario.get("file_path", "")

            task_result = await self._send_prompt_and_get_result(
                client=self.client,
                agent_card_capabilities=self.card.capabilities,
                prompt=scenario["prompt"],
                session_id=current_session_id,
                task_id=current_task_id,
                file_path=file_path_for_scenario,
                use_push_notifications=self.use_push_notifications,
                notification_receiver_host=self.notification_receiver_host,
                notification_receiver_port=self.notification_receiver_port,
            )
            artifacts = task_result.result.artifacts
            for artifact in artifacts:
                parts = artifact.parts
                for part in parts:
                    print(part.text, end="")
            self.assertIsNotNone(task_result, f"场景 {i+1} 未能获取任务结果")
            self.assertIsNotNone(task_result.result, f"场景 {i+1} 的任务结果为空")
            print(f"\n--- 场景 {i+1} 测试完成 ---")

        print("\n--- 所有测试场景完成 ---")

if __name__ == "__main__":
    print("开始 A2A 客户端单元测试...")
    # 测试test_send_prompt_and_get_result_rag 和test_send_prompt_and_get_result_price
    unittest.main()
    print("A2A 客户端单元测试完成。")