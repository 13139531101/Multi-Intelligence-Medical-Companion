# A2A 多 Agent 对话前端

本应用提供了一个用户界面，用于与 A2A（Agent-to-Agent）多 Agent 系统进行对话。

## 快速开始

按照以下步骤在本地运行此前端应用：

### 前置条件

确保你已经安装了 Node.js 和 npm（或 yarn）。

### 安装依赖

在项目根目录下执行以下命令来安装所需的依赖：

```bash
npm install
```

### 配置环境变量
检查项目根目录下的 .env 文件，确保.env文件存在。
确认 REACT_APP_HOSTAGENT_API 环境变量的值与你的 HostAgentAPI 服务的端口一致。例如：
```
REACT_APP_HOSTAGENT_API=http://127.0.0.1:13000
```
如果你的 HostAgentAPI 服务运行在不同的地址或端口，请相应地修改 .env 文件。

### 启动应用
执行以下命令来启动开发服务器：
```bash
npm run dev
```
启动成功后，通常你的浏览器会自动打开应用。如果未自动打开，请访问控制台中显示的地址（通常是 http://localhost:5173 或其他地址）。