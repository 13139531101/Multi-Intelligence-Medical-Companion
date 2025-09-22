#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Date  : 2025/5/6 14:57
# @File  : test_api.py.py
# @Author: johnson
# @Contact : github: johnson7788
# @Desc  : 测试api


import unittest
import requests
import json
import os
import time

class ConversationServerTestCase(unittest.TestCase):
    """
    测试 ConversationServer FastAPI 接口
    """
    host = '127.0.0.1'
    port = 13000
    base_url = f"http://{host}:{port}"

    def test_ping(self):
        """
        测试Ping接口
        :return:
        """
        url = f"http://{self.host}:{self.port}/ping"
        # 读取一条数据，GET模式，参数是一个字典
        start_time = time.time()
        # 提交form格式数据
        r = requests.get(url)
        assert r.json() == "Pong", f"接口是否未启动"
        print(f"花费时间: {time.time() - start_time}秒")

    def test_register_agent(self):
        """
        测试 /agent/register 接口
        """
        url = f"{self.base_url}/agent/register"
        headers = {'Content-Type': 'application/json'}
        agent_url = "127.0.0.1:10005"
        payload = {"params": agent_url}
        start_time = time.time()
        response = requests.post(url, headers=headers, json=payload)
        self.assertEqual(response.status_code, 200, f"/agent/register 接口状态码应为 200，但实际为 {response.status_code}")
        self.assertEqual(response.headers.get('Content-Type'), 'application/json', f"/agent/register 接口 Content-Type 应为 application/json，但实际为 {response.headers.get('Content-Type')}")
        res = response.json()
        print(f"注册Agent的结果: ")
        print(json.dumps(res, indent=2, ensure_ascii=False))
        self.assertIn("result", res, "/agent/register 接口返回值应包含 'result' 字段")
        print(f"/agent/register 测试花费时间: {time.time() - start_time}秒")
    def test_create_conversation(self):
        """
        测试 /conversation/create 接口
        """
        url = f"{self.base_url}/conversation/create"
        start_time = time.time()
        response = requests.post(url)
        self.assertEqual(response.status_code, 200, f"/conversation/create 接口状态码应为 200，但实际为 {response.status_code}")
        self.assertEqual(response.headers.get('Content-Type'), 'application/json', f"/conversation/create 接口 Content-Type 应为 application/json，但实际为 {response.headers.get('Content-Type')}")
        res = response.json()
        self.assertIn("result", res, "/conversation/create 接口返回值应包含 'result' 字段")
        self.assertIn("conversation_id", res["result"], "/conversation/create 接口返回值 'result' 应包含 'conversation_id' 字段")
        print(f"/conversation/create 测试花费时间: {time.time() - start_time}秒")
        conversation_id = res["result"]["conversation_id"]
        print(f"result是: {res['result']}")
        print(f"创建的conversation_id是: {conversation_id}")
        self.created_conversation_id = conversation_id # 保存 conversation_id 供后续测试使用

    def test_list_conversation(self):
        """
        测试 /conversation/list 接口
        """
        url = f"{self.base_url}/conversation/list"
        start_time = time.time()
        response = requests.post(url)
        self.assertEqual(response.status_code, 200, f"/conversation/list 接口状态码应为 200，但实际为 {response.status_code}")
        self.assertEqual(response.headers.get('Content-Type'), 'application/json', f"/conversation/list 接口 Content-Type 应为 application/json，但实际为 {response.headers.get('Content-Type')}")
        res = response.json()
        print(f"list conversation结果是:")
        print(json.dumps(res, indent=2, ensure_ascii=False))
        self.assertIn("result", res, "/conversation/list 接口返回值应包含 'result' 字段")
        self.assertIsInstance(res["result"], list, "/conversation/list 接口返回值 'result' 应为列表")
        print(f"/conversation/list 测试花费时间: {time.time() - start_time}秒")

    def test_send_message(self):
        """
        测试 /message/send 接口
        """
        # 首先确保已经创建了一个 conversation
        if not hasattr(self, 'created_conversation_id'):
            self.test_create_conversation()

        url = f"{self.base_url}/message/send"
        headers = {'Content-Type': 'application/json'}
        # text = "你好"
        text = "什么是LNG?"
        message_payload = {
            "params": {
                "role": "user",
                "parts": [{"type": "text", "text": text}],
                "metadata": {"conversation_id": self.created_conversation_id}
            }
        }
        start_time = time.time()
        response = requests.post(url, headers=headers, json=message_payload)
        self.assertEqual(response.status_code, 200, f"/message/send 接口状态码应为 200，但实际为 {response.status_code}")
        self.assertEqual(response.headers.get('Content-Type'), 'application/json', f"/message/send 接口 Content-Type 应为 application/json，但实际为 {response.headers.get('Content-Type')}")
        res = response.json()
        self.assertIn("result", res, "/message/send 接口返回值应包含 'result' 字段")
        self.assertIn("message_id", res["result"], "/message/send 接口返回值 'result' 应包含 'message_id' 字段")
        self.assertIn("conversation_id", res["result"], "/message/send 接口返回值 'result' 应包含 'conversation_id' 字段")
        print(f"send message结果是:")
        print(json.dumps(res, indent=2, ensure_ascii=False))
        print(f"/message/send 测试花费时间: {time.time() - start_time}秒")
        self.sent_message_id = res["result"]["message_id"]

    def test_list_messages(self):
        """
        测试 /message/list 接口
        """
        # 首先确保已经创建了一个 conversation 并且发送了消息
        self.created_conversation_id = "ed7ee627-227d-4269-ae94-cfe20b9446e4"
        self.sent_message_id = "fc745aaa-4e7b-4756-babf-b98e5da15e6d"

        url = f"{self.base_url}/message/list"
        headers = {'Content-Type': 'application/json'}
        payload = {"params": self.created_conversation_id}
        start_time = time.time()
        response = requests.post(url, headers=headers, json=payload)
        self.assertEqual(response.status_code, 200, f"/message/list 接口状态码应为 200，但实际为 {response.status_code}")
        self.assertEqual(response.headers.get('Content-Type'), 'application/json', f"/message/list 接口 Content-Type 应为 application/json，但实际为 {response.headers.get('Content-Type')}")
        res = response.json()
        print(f"list messages结果是:")
        print(json.dumps(res, indent=2, ensure_ascii=False))
        self.assertIn("result", res, "/message/list 接口返回值应包含 'result' 字段")
        self.assertIsInstance(res["result"], list, "/message/list 接口返回值 'result' 应为列表")
        if res["result"]:
            found = False
            for message in res["result"]:
                if message.get("metadata", {}).get("message_id") == self.sent_message_id:
                    found = True
                    break
            print(f"message_id: {self.sent_message_id} 是否在返回结果中: {found}")
            self.assertTrue(found, f"/message/list 接口返回值应包含已发送的消息，message_id: {self.sent_message_id}")
        else:
            self.assertTrue(res["result"], f"/message/list 测试结果为空")
        print(f"/message/list 测试花费时间: {time.time() - start_time}秒")

    def test_pending_messages(self):
        """
        测试 /message/pending 接口
        返回数据：
        {
          "jsonrpc": "2.0",
          "id": "b9da3c07ff9247c4b8ee4f795a00c215",
          "result": [
            [
              "53554617-9341-4c04-ac82-7eaaf125ff74",
              ""
            ]
          ],
          "error": null
        }
        """
        url = f"{self.base_url}/message/pending"
        start_time = time.time()
        response = requests.post(url)
        self.assertEqual(response.status_code, 200, f"/message/pending 接口状态码应为 200，但实际为 {response.status_code}")
        self.assertEqual(response.headers.get('Content-Type'), 'application/json', f"/message/pending 接口 Content-Type 应为 application/json，但实际为 {response.headers.get('Content-Type')}")
        res = response.json()
        print(f"pending messages结果是,如果result为空，说明没有正在pending的消息，没有正在处理的消息")
        print(json.dumps(res, indent=2, ensure_ascii=False))
        self.assertIn("result", res, "/message/pending 接口返回值应包含 'result' 字段")
        self.assertIsInstance(res["result"], list, "/message/pending 接口返回值 'result' 应为列表")
        print(f"/message/pending 测试花费时间: {time.time() - start_time}秒")

    def test_get_events(self):
        """
        测试 /events/get 接口
        """
        url = f"{self.base_url}/events/get"
        start_time = time.time()
        response = requests.post(url)
        self.assertEqual(response.status_code, 200, f"/events/get 接口状态码应为 200，但实际为 {response.status_code}")
        self.assertEqual(response.headers.get('Content-Type'), 'application/json', f"/events/get 接口 Content-Type 应为 application/json，但实际为 {response.headers.get('Content-Type')}")
        res = response.json()
        print(f"events列表，当上面有进行过提问时，events里面会有内容 ")
        print(json.dumps(res, indent=2, ensure_ascii=False))
        self.assertIn("result", res, "/events/get 接口返回值应包含 'result' 字段")
        self.assertIsInstance(res["result"], list, "/events/get 接口返回值 'result' 应为列表")
        print(f"/events/get 测试花费时间: {time.time() - start_time}秒")

    def test_query_events(self):
        """
        测试查询事件的接口
        """
        # 可以先调用test_send_message创建1个conversation
        conversation_id = "12daaca7-afe0-425d-a2da-032a63407109"
        url = f"{self.base_url}/events/query"
        headers = {'Content-Type': 'application/json'}
        message_payload = {
            "params": {
                "conversation_id": conversation_id,
            }
        }
        start_time = time.time()
        response = requests.post(url, headers=headers, json=message_payload)
        self.assertEqual(response.status_code, 200, f"/message/send 接口状态码应为 200，但实际为 {response.status_code}")
        self.assertEqual(response.headers.get('Content-Type'), 'application/json', f"/message/send 接口 Content-Type 应为 application/json，但实际为 {response.headers.get('Content-Type')}")
        res = response.json()
        print(json.dumps(res, indent=2, ensure_ascii=False))
        assert res.get("error") is None, "错误不为空，请检查"
        assert res.get("result"), "返回的结果为空，请检查数据"
        print(f"/events/query 测试花费时间: {time.time() - start_time}秒")
    def test_list_tasks(self):
        """
        测试 /task/list 接口
        """
        url = f"{self.base_url}/task/list"
        start_time = time.time()
        response = requests.post(url)
        self.assertEqual(response.status_code, 200, f"/task/list 接口状态码应为 200，但实际为 {response.status_code}")
        self.assertEqual(response.headers.get('Content-Type'), 'application/json', f"/task/list 接口 Content-Type 应为 application/json，但实际为 {response.headers.get('Content-Type')}")
        res = response.json()
        print(f"task list: 列出任务")
        print(json.dumps(res, indent=2, ensure_ascii=False))
        self.assertIn("result", res, "/task/list 接口返回值应包含 'result' 字段")
        self.assertIsInstance(res["result"], list, "/task/list 接口返回值 'result' 应为列表")
        print(f"/task/list 测试花费时间: {time.time() - start_time}秒")

    def test_list_agents(self):
        """
        测试 /agent/list 接口
        """
        url = f"{self.base_url}/agent/list"
        start_time = time.time()
        response = requests.post(url)
        self.assertEqual(response.status_code, 200, f"/agent/list 接口状态码应为 200，但实际为 {response.status_code}")
        self.assertEqual(response.headers.get('Content-Type'), 'application/json', f"/agent/list 接口 Content-Type 应为 application/json，但实际为 {response.headers.get('Content-Type')}")
        res = response.json()
        print(f"已经注册Agent有: ")
        print(json.dumps(res, indent=2, ensure_ascii=False))
        self.assertIn("result", res, "/agent/list 接口返回值应包含 'result' 字段")
        self.assertIsInstance(res["result"], list, "/agent/list 接口返回值 'result' 应为列表")
        print(f"/agent/list 测试花费时间: {time.time() - start_time}秒")

    def test_update_api_key(self):
        """
        测试 /api_key/update 接口
        """
        url = f"{self.base_url}/api_key/update"
        headers = {'Content-Type': 'application/json'}
        api_key = "test_api_key"
        payload = {"api_key": api_key}
        start_time = time.time()
        response = requests.post(url, headers=headers, json=payload)
        self.assertEqual(response.status_code, 200, f"/api_key/update 接口状态码应为 200，但实际为 {response.status_code}")
        self.assertEqual(response.headers.get('Content-Type'), 'application/json', f"/api_key/update 接口 Content-Type 应为 application/json，但实际为 {response.headers.get('Content-Type')}")
        res = response.json()
        self.assertIn("status", res, "/api_key/update 接口返回值应包含 'status' 字段")
        self.assertEqual(res["status"], "success", f"/api_key/update 接口返回值 'status' 应为 'success'，但实际为 {res['status']}")
        print(f"/api_key/update 测试花费时间: {time.time() - start_time}秒")

    def test_send_and_poll_pending(self):
        """
        测试发送消息后，轮询 /message/pending 获取正在处理的消息
        想要使用某个Agent回答，务必要注册这个Agent
        """
        # 首先发送一条消息
        if not hasattr(self, 'created_conversation_id'):
            self.test_create_conversation()

        url_send = f"{self.base_url}/message/send"
        headers = {'Content-Type': 'application/json'}
        message_payload = {
            "params": {
                "role": "user",
                "parts": [{"type": "text", "text": "解释下什么是LNG"}],
                "metadata": {"conversation_id": self.created_conversation_id}
            }
        }
        response = requests.post(url_send, headers=headers, json=message_payload)
        self.assertEqual(response.status_code, 200, "/message/send 请求失败")
        res = response.json()
        message_id = res["result"]["message_id"]
        print(f"已发送消息，message_id: {message_id}")

        # 然后轮询 pending 接口
        url_pending = f"{self.base_url}/message/pending"
        timeout = 120  # 最多等待 120 秒
        interval = 0.5
        elapsed = 0

        while elapsed < timeout:
            response = requests.post(url_pending)
            self.assertEqual(response.status_code, 200, "/message/pending 请求失败")
            pending_res = response.json()
            pending_ids = []
            # 获取所有message_id
            for items in pending_res.get("result", []):
                for one_ids in items:
                    if one_ids:
                        pending_ids.append(one_ids)
            print(f"{elapsed:.1f}s: 当前 pending 消息: {pending_ids}")
            self.test_get_events()
            if message_id not in pending_ids:
                print("消息已完成处理，退出轮询")
                break
            time.sleep(interval)
            elapsed += interval
        else:
            self.fail(f"超时：{timeout}秒内消息仍在 pending 中")


if __name__ == '__main__':
    unittest.main()