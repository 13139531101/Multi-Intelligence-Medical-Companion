import _thread as thread
import base64
import datetime
import hashlib
import hmac
import json
import threading
from urllib.parse import urlparse, urlencode, quote
import ssl
from datetime import datetime
from email.utils import formatdate

import websocket  # pip install websocket-client

class SparkClient:
    def __init__(self, appid, api_key, api_secret, spark_url, domain):
        self.appid = appid
        self.api_key = api_key
        self.api_secret = api_secret
        self.spark_url = spark_url
        self.domain = domain
        self.answer = ""
        self._done = threading.Event()
        self._error = None

    # 生成url
    def create_url(self):
        date = formatdate(timeval=None, localtime=False, usegmt=True)

        # 拼接字符串
        parsed_url = urlparse(self.spark_url)
        host = parsed_url.netloc
        path = parsed_url.path

        signature_origin = "host: " + host + "\n"
        signature_origin += "date: " + date + "\n"
        signature_origin += "GET " + path + " HTTP/1.1"

        # 进行hmac-sha256进行加密
        signature_sha = hmac.new(self.api_secret.encode('utf-8'), signature_origin.encode('utf-8'),
                                 digestmod=hashlib.sha256).digest()

        signature_sha_base64 = base64.b64encode(signature_sha).decode(encoding='utf-8')

        authorization_origin = f'api_key="{self.api_key}", algorithm="hmac-sha256", headers="host date request-line", signature="{signature_sha_base64}"'

        authorization = base64.b64encode(authorization_origin.encode('utf-8')).decode(encoding='utf-8')

        # 将请求的鉴权参数组合为字典
        v = {
            "authorization": authorization,
            "date": date,
            "host": host
        }
        # 拼接鉴权参数，生成url
        url = self.spark_url + "?" + urlencode(v, quote_via=quote)
        return url

    def on_error(self, ws, error):
        self._error = error
        self._done.set()
        try:
            ws.close()
        except Exception:
            pass

    def on_close(self, ws, one, two):
        self._done.set()

    def on_open(self, ws):
        thread.start_new_thread(self.run, (ws,))

    def run(self, ws):
        data = json.dumps(self.gen_params(appid=self.appid, domain=self.domain, question=self.question))
        ws.send(data)

    def on_message(self, ws, message):
        data = json.loads(message)
        code = data['header']['code']
        if code != 0:
            self._error = {"code": code, "raw": data}
            self._done.set()
            ws.close()
        else:
            choices = data["payload"]["choices"]
            status = choices["status"]
            content = choices["text"][0]["content"]
            self.answer += content
            if status == 2:
                self._done.set()
                ws.close()

    def gen_params(self, appid, domain, question):
        """
        通过appid和用户的提问来生成请参数
        """
        data = {
            "header": {
                "app_id": appid,
                "uid": "1234"
            },
            "parameter": {
                "chat": {
                    "domain": domain,
                    "temperature": 0.5,
                    "max_tokens": 2048
                }
            },
            "payload": {
                "message": {
                    "text": [
                        {"role": "user", "content": question}
                    ]
                }
            }
        }
        return data

    def chat(self, question, timeout_seconds: float = 20.0):
        self.question = question
        self.answer = ""
        self._error = None
        self._done.clear()
        websocket.enableTrace(False)
        wsUrl = self.create_url()
        ws = websocket.WebSocketApp(
            wsUrl,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
            on_open=self.on_open,
        )
        t = threading.Thread(
            target=lambda: ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE}),
            daemon=True,
        )
        t.start()
        ok = self._done.wait(timeout=max(1.0, float(timeout_seconds or 20.0)))
        if not ok:
            try:
                ws.close()
            except Exception:
                pass
            return f"请求超时({timeout_seconds}s)"
        if self._error is not None:
            return f"请求失败: {self._error}"
        return self.answer

def call_spark(prompt, appid, api_key, api_secret, spark_url, domain, timeout_seconds: float = 20.0):
    client = SparkClient(appid, api_key, api_secret, spark_url, domain)
    return client.chat(prompt, timeout_seconds=timeout_seconds)
