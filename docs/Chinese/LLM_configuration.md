# 如何使用不同的模型

## OpenAI 模型

### gpt-4o

1.  在你的项目中创建 `.env` 文件，并添加 `OPENAI_API_KEY` 环境变量，值为你的 OpenAI API Key。
2.  运行命令：`python main.py --provider openai --model gpt-4o`

### o3-mini

1.  在你的项目中创建 `.env` 文件，并添加 `OPENAI_API_KEY` 环境变量，值为你的 OpenAI API Key。
2.  运行命令：`python main.py --provider openai --model o3-mini`

## DeepSeek 模型

### V3

1.  在你的项目中创建 `.env` 文件，并添加 `DEEPSEEK_API_KEY` 环境变量，值为你的 DeepSeek API Key。
2.  运行命令：`python main.py --provider deepseek --model deepseek-chat`

## 注意事项

* 目前 Reasoning 模型不支持工具调用，因此使用 DeepSeek 的 R1 模型会报错。
* 如果需要模拟推理过程，可以使用 SequentialThink 模型来模拟 R1 的推理过程。

## Bytedance，豆包供应商
1.  在你的项目中创建 `.env` 文件，并添加 `BYTEDANCE_API_KEY` 环境变量，值为你的 Bytedance API Key。
2.  运行命令：`python main.py --provider bytedance --model doubao-1-5-pro-32k` 或者 `python main.py --provider bytedance --model deepseek-v3`
3.  或者思考模型: `python main.py --provider bytedance --model deepseek-r1-250120`  或者 `python main.py --provider bytedance --model doubao-1.5-thinking-pro-250415`

## VLLM模型
1.  在你的项目中创建 `.env` 文件中需要添加
```
VLLM_API_KEY=xxxxx
VLLM_BASE_URL="http://xxxx:xxx/v1"
```

2.  运行命令：`python main.py --provider vllm --model xxx`， model是你创建vllm时的模型
3.  注意vllm启动示例,注意需要启动工具的调用还有工具的形式：--enable-auto-tool-choice --tool-call-parser hermes
```
docker run --gpus all \
  -d -p 8000:8000 \
  --privileged \
  -e CUDA_VISIBLE_DEVICES=1 \
  -v /media/model/Qwen3-14B:/models \
  --name tool_container \
  vllm/vllm-openai:v0.6.2 \
  --trust-remote-code \
  --enforce-eager \
  --max-model-len 10240 \
  --tensor-parallel-size 1 \
  --model /models \
  --download-dir /models \
  --enable-auto-tool-choice --tool-call-parser hermes \
  --served-model-name 2-5-7B-Instruct
```

## 智谱模型
1.  在你的项目中创建 `.env` 文件中需要添加
```
ZHIPU_API_KEY=xxxx
```
2.  运行命令：`python main.py --provider zhipu --model xxx`， model是你创建vllm时的模型

## 如何创建自己的模型供应商
在backend/A2AServer/src/A2AServer/mcp_client/providers中添加供应商文件
修改backend/A2AServer/src/A2AServer/mcp_client/client.py的generate_text函数