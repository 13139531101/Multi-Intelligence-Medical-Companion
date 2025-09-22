#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Date  : 2025/5/25 06:55
# @File  : debug_utils.py
# @Author: johnson
# @Contact : github: johnson7788
# @Desc  : 记录MCP交互时的协议信息，方便进行Debug

#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Date  : 2025/5/25 06:55
# @File  : debug_utils.py
# @Author: johnson
# @Contact : github: johnson7788
# @Desc  : 记录MCP交互协议信息，便于调试

import sys
import subprocess
import threading
import argparse
import os

# --- 配置 ---
LOG_FILE = os.path.join(os.path.dirname(os.path.realpath(__file__)), "mcp.log")
# --- 配置结束 ---

# --- 命令行参数解析 ---
parser = argparse.ArgumentParser(
    description="包装命令，透传STDIN/STDOUT并记录日志。",
    usage="%(prog)s <command> [args...]"
)
parser.add_argument('command', nargs=argparse.REMAINDER, help='要执行的命令及其参数')

# 清空日志文件
open(LOG_FILE, 'w', encoding='utf-8')

if len(sys.argv) == 1:
    parser.print_help(sys.stderr)
    sys.exit(1)

args = parser.parse_args()

if not args.command:
    print("错误：未提供命令。", file=sys.stderr)
    parser.print_help(sys.stderr)
    sys.exit(1)

target_command = args.command
# --- 参数解析结束 ---

# --- 输入/输出转发函数 ---
# 这些函数将在单独线程中运行

def forward_and_log_stdin(proxy_stdin, target_stdin, log_file):
    """从代理的stdin读取，记录日志并写入目标stdin"""
    try:
        while True:
            line_bytes = proxy_stdin.readline()
            if not line_bytes:  # 到达EOF
                break

            # 解码用于日志记录（假设为UTF-8）
            try:
                line_str = line_bytes.decode('utf-8')
            except UnicodeDecodeError:
                line_str = f"[非UTF-8数据，{len(line_bytes)}字节]\n"

            # 记录带前缀的日志
            log_file.write(f"输入: {line_str}")
            log_file.flush()  # 确保日志及时写入

            # 将原始字节写入目标进程的stdin
            target_stdin.write(line_bytes)
            target_stdin.flush()  # 确保目标进程及时接收

    except Exception as e:
        # 记录转发过程中的错误
        try:
            log_file.write(f"!!! STDIN转发错误: {e}\n")
            log_file.flush()
        except:
            pass  # 忽略日志记录错误

    finally:
        # 关闭目标stdin，通知目标进程EOF
        try:
            target_stdin.close()
            log_file.write("--- STDIN流关闭 ---\n")
            log_file.flush()
        except Exception as e:
            try:
                log_file.write(f"!!! 关闭目标STDIN错误: {e}\n")
                log_file.flush()
            except:
                pass

def forward_and_log_stdout(target_stdout, proxy_stdout, log_file):
    """从目标stdout读取，记录日志并写入代理stdout"""
    try:
        while True:
            line_bytes = target_stdout.readline()
            if not line_bytes:  # 到达EOF
                break

            # 解码用于日志记录
            try:
                line_str = line_bytes.decode('utf-8')
            except UnicodeDecodeError:
                line_str = f"[非UTF-8数据，{len(line_bytes)}字节]\n"

            # 记录带前缀的日志
            log_file.write(f"输出: {line_str}")
            log_file.flush()

            # 将原始字节写入代理stdout
            proxy_stdout.write(line_bytes)
            proxy_stdout.flush()  # 确保输出及时显示

    except Exception as e:
        try:
            log_file.write(f"!!! STDOUT转发错误: {e}\n")
            log_file.flush()
        except:
            pass
    finally:
        try:
            log_file.flush()
        except:
            pass

def forward_and_log_stderr(target_stderr, proxy_stderr, log_file):
    """从目标stderr读取，记录日志并写入代理stderr"""
    try:
        while True:
            line_bytes = target_stderr.readline()
            if not line_bytes:
                break
            try:
                line_str = line_bytes.decode('utf-8')
            except UnicodeDecodeError:
                line_str = f"[非UTF-8数据，{len(line_bytes)}字节]\n"
            log_file.write(f"STDERR: {line_str}")
            log_file.flush()
            proxy_stderr.write(line_bytes)
            proxy_stderr.flush()
    except Exception as e:
        try:
            log_file.write(f"!!! STDERR转发错误: {e}\n")
            log_file.flush()
        except:
            pass
    finally:
        try:
            log_file.flush()
        except:
            pass

# --- 主执行逻辑 ---
process = None
log_f = None
exit_code = 1  # 默认退出码，处理早期失败

try:
    # 以追加模式打开日志文件
    log_f = open(LOG_FILE, 'a', encoding='utf-8')

    # 启动目标进程
    process = subprocess.Popen(
        target_command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,  # 捕获stderr
        bufsize=0  # 无缓冲二进制I/O
    )

    # 创建并启动转发线程
    stdin_thread = threading.Thread(
        target=forward_and_log_stdin,
        args=(sys.stdin.buffer, process.stdin, log_f),
        daemon=True  # 主线程退出时终止
    )

    stdout_thread = threading.Thread(
        target=forward_and_log_stdout,
        args=(process.stdout, sys.stdout.buffer, log_f),
        daemon=True
    )

    stderr_thread = threading.Thread(
        target=forward_and_log_stderr,
        args=(process.stderr, sys.stderr.buffer, log_f),
        daemon=True
    )

    # 启动线程
    stdin_thread.start()
    stdout_thread.start()
    stderr_thread.start()

    # 等待目标进程完成
    process.wait()
    exit_code = process.returncode

    # 等待I/O线程完成最后消息的刷新
    stdin_thread.join(timeout=1.0)
    stdout_thread.join(timeout=1.0)
    stderr_thread.join(timeout=1.0)

except Exception as e:
    print(f"MCP日志记录错误: {e}", file=sys.stderr)
    if log_f and not log_f.closed:
        try:
            log_f.write(f"!!! MCP日志主错误: {e}\n")
            log_f.flush()
        except:
            pass
    exit_code = 1

finally:
    # 确保目标进程终止
    if process and process.poll() is None:
        try:
            process.terminate()
            process.wait(timeout=1.0)
        except:
            pass
        if process.poll() is None:
            try:
                process.kill()  # 强制终止
            except:
                pass

    # 关闭日志文件
    if log_f and not log_f.closed:
        try:
            log_f.close()
        except:
            pass

    # 使用目标进程的退出码退出
    sys.exit(exit_code)