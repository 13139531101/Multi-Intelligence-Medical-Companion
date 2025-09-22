# How to Use Different Models

## OpenAI Models

### gpt-4o

1.  Create a `.env` file in your project and add the `OPENAI_API_KEY` environment variable with your OpenAI API Key as its value.
2.  Run the command: `python main.py --provider openai --model gpt-4o`

### o3-mini

1.  Create a `.env` file in your project and add the `OPENAI_API_KEY` environment variable with your OpenAI API Key as its value.
2.  Run the command: `python main.py --provider openai --model o3-mini`

## DeepSeek Models

### V3

1.  Create a `.env` file in your project and add the `DEEPSEEK_API_KEY` environment variable with your DeepSeek API Key as its value.
2.  Run the command: `python main.py --provider deepseek --model deepseek-chat`

## Important Notes

* Reasoning models do not currently support the use of tools, so using DeepSeek's R1 model will result in an error.
* If you want to simulate the reasoning process, you can use the SequentialThink model to simulate the reasoning process of R1.

## Bytedance, Doubao Provider
1. Create a .env file in your project and add the BYTEDANCE_API_KEY environment variable, setting its value to your Bytedance API Key.
2. Run the command: python main.py --provider bytedance --model doubao-1-5-pro-32k or python main.py --provider bytedance --model deepseek-v3


## VLLM Model
1. You need to add the following to the .env file in your project:
```
VLLM_API_KEY=xxxxx
VLLM_BASE_URL="http://xxxx:xxx/v1"
```
2. Run the command: python main.py --provider vllm --model xxx, where model is the model you created when setting up VLLM.
3. Pay attention to the vLLM startup example, noting the need to enable tool calling and the format of the tools：--enable-auto-tool-choice --tool-call-parser hermes
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


## Zhipu Model
1. You need to add the following to the .env file in your project:
```
ZHIPU_API_KEY=xxxxx
```
2. Run the command: python main.py --provider zhipu --model xxx, where model is the model you created when setting up Zhipu.


## How to Create Your Own Model Provider
1. Add the provider file in backend/A2AServer/src/A2AServer/mcp_client/providers.
2. Modify the generate_text function in backend/A2AServer/src/A2AServer/mcp_client/client.py.