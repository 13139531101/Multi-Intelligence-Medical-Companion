# Documentation

📘 [中文Readme](./README_ZH.md)

This repository contains documentation regarding the User Interface (UI) and different Large Language Model (LLM) configurations.

## UI Interface

- [Chinese UI Guide](./Chinese/UI.md)
- [English UI Guide](./English/UI.md)

These documents provide a detailed overview of the application's user interface, including usage examples for both Single Agent and Multi-Agent modes, as well as interface demonstrations of conversations and thought processes. Images are used for illustration and are located in the `images` directory.

## Different LLM Configurations

- [Chinese LLM Configuration Guide](./Chinese/LLM_configuration.md)
- [English LLM Configuration Guide](./English/LLM_configuration.md)

These documents offer detailed information about different Large Language Model configurations, including configuration parameters, usage instructions, and related considerations.

## Issue Summary
1. The official Deepseek-R1 model does not support function calling, so using it will result in errors. However, the Deepseek-R1 model provided by Volcano Engine supports both function calling and reasoning, and is recommended.
2. It is essential to ensure the uniqueness of the `session_id` for each session passed to the Agent.

Please refer to the respective documents for more detailed information.