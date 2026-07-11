# PHA v2 K8s 部署学习指南

> **目标**：用 Kubernetes (K8s) 部署 PHA v2 多智能体健康助理，**边学边做**
>
> **学习路径**：基础概念 → 资源文件 → 一键部署 → 调试排错 → 进阶（Helm / Operator）

---

## 1. K8s 是什么

**Kubernetes**（简称 K8s，中间的 8 个字母省略）是 Google 开源的**容器编排系统**：

- **自动部署**：声明期望状态（"我要 2 个 Pod"），K8s 自动达到
- **自动扩缩**：CPU 高了自动加 Pod（HorizontalPodAutoscaler）
- **自动恢复**：Pod 挂了自动重启
- **服务发现**：Pod 之间通过 DNS 找到（`pha-postgres:5432`）
- **滚动更新**：发布新版本不停机
- **配置管理**：ConfigMap（明文）+ Secret（密文）
- **存储抽象**：PVC / PV，自动挂载存储

### 1.1 K8s vs Docker Compose

| 维度 | Docker Compose | K8s |
|------|---------------|-----|
| 规模 | 单机 | 集群（数百节点）|
| 自愈 | 弱 | 强（自动重启 + 迁移）|
| 扩缩 | 手动 | 自动（HPA）|
| 学习曲线 | 低 | 高 |
| 适用 | 开发 / 小项目 | 生产 / 中大型项目 |

**PHA v2 现况**：docker-compose 跑开发，K8s 跑生产。

---

## 2. K8s 核心概念

### 2.1 Pod（最小部署单位）

**Pod = 一组容器 + 共享网络 + 共享存储**。
通常一个 Pod 一个容器，**但可以多个**（如 sidecar 模式）。

```bash
kubectl get pods -n pha
```

### 2.2 Deployment（无状态部署）

**Pod 的控制器**：声明"我要 3 个 Pod"，K8s 自动维持。
用于无状态服务（API server）。

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: pha-hostapi
spec:
  replicas: 2  # 2 个 Pod
  selector:
    matchLabels:
      app: pha-hostapi
  template:
    metadata:
      labels:
        app: pha-hostapi
    spec:
      containers:
        - name: hostapi
          image: xxx
```

### 2.3 StatefulSet（有状态部署）

**Pod 标识稳定**（`pha-postgres-0` / `pha-postgres-1`）。
用于数据库（每个 Pod 一个独立存储）。

### 2.4 Service（服务发现）

**Pod 的稳定访问入口**（Pod IP 变了 Service 不变）。

| 类型 | 用途 |
|------|------|
| `ClusterIP` | 集群内访问（默认）|
| `NodePort` | 集群外访问（每个节点开端口）|
| `LoadBalancer` | 云厂商负载均衡（生产用）|
| `ExternalName` | 外部服务代理 |

### 2.5 ConfigMap + Secret

- **ConfigMap**：明文配置（如端口、限流参数）
- **Secret**：密文配置（API key、密码，base64 编码）

### 2.6 Volume / PVC（持久化存储）

- **Volume**：Pod 内部存储
- **PVC (PersistentVolumeClaim)**：Pod 申请存储
- **PV (PersistentVolume)**：集群实际存储（云盘 / NFS）

### 2.7 Namespace（命名空间）

K8s 资源隔离单位。PHA v2 全部在 `pha` 命名空间。

### 2.8 Ingress（七层路由）

L7 HTTP 路由，基于域名 / 路径。需装 **ingress-nginx controller**。

### 2.9 HPA（自动扩缩）

**HorizontalPodAutoscaler**：基于 CPU / 内存 / 自定义指标自动加减 Pod 数。

### 2.10 PDB（自愿中断预算）

**PodDisruptionBudget**：保证 K8s 运维时最少可用 Pod 数。

---

## 3. 准备环境

### 3.1 选项 A：kind（推荐学习用）

**kind = K8s in Docker**，本地用 Docker 跑 K8s 集群。

```bash
# 安装 kind (Windows)
choco install kind

# 或下载二进制
curl.exe -Lo kind-windows-amd64.exe https://kind.sigs.k8s.io/dl/v0.24.0/kind-windows-amd64
Move-Item kind-windows-amd64.exe C:\Windows\System32\kind.exe

# 创建集群（1 控制平面 + 2 worker）
kind create cluster --name pha --config - <<EOF
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
  - role: control-plane
  - role: worker
  - role: worker
EOF

# 验证
kubectl cluster-info
kubectl get nodes
```

### 3.2 选项 B：minikube

```bash
choco install minikube
minikube start --cpus=4 --memory=8g
```

### 3.3 选项 C：云厂商

阿里云 ACK / 腾讯云 TKE / AWS EKS，创建集群后下载 kubeconfig。

---

## 4. 一键部署

### 4.1 应用所有 manifest

```bash
cd i:\A2A\3\A2AServer

# 干跑（验证语法）
kubectl kustomize k8s/

# 真跑
kubectl apply -k k8s/

# 等待所有 Pod 就绪
kubectl wait --for=condition=Ready pods --all -n pha --timeout=300s
```

### 4.2 查看部署状态

```bash
# 命名空间下所有资源
kubectl get all -n pha

# Pod 状态
kubectl get pods -n pha -o wide

# 资源用量
kubectl top pods -n pha
kubectl top nodes

# Service
kubectl get svc -n pha

# 详细事件
kubectl describe pod <pod-name> -n pha
```

### 4.3 访问服务

#### NodePort（kind / 开发）

```bash
# NodePort 31302 -> hostapi 13002
curl http://localhost:31302/health
curl http://localhost:31302/metrics
curl http://localhost:31302/v2/status

# NodePort 31011 -> health_advisor
curl http://localhost:31011/.well-known/agent.json
```

#### Port-forward（任意场景）

```bash
# 转发 hostapi 到本地 8080
kubectl port-forward -n pha svc/pha-hostapi 8080:13002
# 浏览器打开 http://localhost:8080/v2/status

# 转发 postgres
kubectl port-forward -n pha svc/pha-postgres 5432:5432
```

#### Ingress（生产）

```bash
# /etc/hosts（本地）
127.0.0.1 pha.local
# 浏览器打开 http://pha.local
```

---

## 5. 调试排错

### 5.1 Pod 起不来

```bash
# 查看 Pod 状态
kubectl get pods -n pha

# 看 Pod 详细事件
kubectl describe pod <pod-name> -n pha

# 看 Pod 日志
kubectl logs <pod-name> -n pha

# 进入 Pod 内部调试
kubectl exec -it <pod-name> -n pha -- /bin/bash
```

### 5.2 常见错误

| 错误 | 原因 | 解决 |
|------|------|------|
| `ImagePullBackOff` | 镜像拉不到 | 检查 image 名 / 私有仓库认证 |
| `CrashLoopBackOff` | 容器启动失败 | `kubectl logs` 看错误 |
| `Pending` | 资源不够 / PVC 未绑定 | `kubectl describe` |
| `ErrImageNeverPull` | `imagePullPolicy: Never` 但本地无镜像 | 改 `IfNotPresent` 或 push |
| `Readiness probe failed` | 健康检查路径错 | 检查 livenessProbe / readinessProbe |

### 5.3 实时日志

```bash
# 跟踪日志
kubectl logs -f <pod-name> -n pha

# 上一实例日志（崩溃后）
kubectl logs --previous <pod-name> -n pha
```

---

## 6. 进阶操作

### 6.1 水平扩缩

#### 手动

```bash
# 扩容到 5 副本
kubectl scale deployment/pha-hostapi -n pha --replicas=5

# 看 HPA 状态
kubectl get hpa -n pha
```

#### 自动（HPA 已配置）

- CPU > 70% → 自动加 Pod（最多 10）
- CPU < 70% → 5 分钟后自动减（最少 2）

```bash
# 制造负载看 HPA
kubectl run -it --rm loadgen --image=busybox --restart=Never -- \
  sh -c "while true; do wget -q -O- http://pha-hostapi/health; done"
```

### 6.2 滚动更新

```bash
# 更新镜像
kubectl set image deployment/pha-hostapi -n pha hostapi=xxx:v2

# 看发布进度
kubectl rollout status deployment/pha-hostapi -n pha

# 回滚
kubectl rollout undo deployment/pha-hostapi -n pha
```

### 6.3 持久化存储

```bash
# Postgres PVC
kubectl get pvc -n pha pha-postgres-data

# 看实际存储
kubectl describe pv

# 备份
kubectl exec -n pha pha-postgres-0 -- \
  pg_dump -U pha personal_health_assistant > backup.sql
```

### 6.4 RBAC（最小权限）

```bash
# 创建只读用户
kubectl create serviceaccount pha-reader -n pha
kubectl create rolebinding pha-reader -n pha \
  --clusterrole=view --serviceaccount=pha:pha-reader
```

### 6.5 NetworkPolicy（网络隔离）

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: pha-hostapi-netpol
  namespace: pha
spec:
  podSelector:
    matchLabels:
      app: pha-hostapi
  policyTypes: [Ingress, Egress]
  ingress:
    - from:
        - podSelector: {}  # 允许所有 Pod 访问
      ports:
        - port: 13002
  egress:
    - to:
        - podSelector:
            matchLabels:
              app: pha-postgres
      ports:
        - port: 5432
```

### 6.6 监控（已配置）

K8s manifest 已带 Prometheus 注解：

```yaml
annotations:
  prometheus.io/scrape: "true"
  prometheus.io/port: "13002"
  prometheus.io/path: "/metrics"
```

装 kube-prometheus-stack 自动抓取。

---

## 7. 完整资源清单

| 资源 | 数量 | 用途 |
|------|------|------|
| Namespace | 1 | `pha` 隔离 |
| LimitRange | 1 | 容器默认资源限制 |
| Secret | 1 | 11 个 API key + 密码 |
| ConfigMap | 2 | 业务配置 + DB 初始化 SQL |
| PVC | 2 | postgres 20Gi + redis 5Gi |
| StatefulSet | 1 | postgres |
| Deployment | 6 | redis + 4 MCP + hostapi |
| Service | 12 | 7 ClusterIP + 5 NodePort |
| ServiceAccount | 1 | hostapi 身份 |
| HPA | 1 | hostapi 自动扩缩（2-10） |
| PDB | 1 | hostapi 至少 1 个可用 |
| Ingress | 1 | pha.local 域名路由 |

**共 30 个 K8s 资源**。

---

## 8. 资源文件清单

| 文件 | 内容 | 行数 |
|------|------|------|
| `00-namespace.yaml` | Namespace + LimitRange | ~30 |
| `01-secrets.yaml` | Secret + ConfigMap | ~80 |
| `02-postgres.yaml` | Service + PVC + StatefulSet + init CM | ~120 |
| `03-redis.yaml` | Service + PVC + Deployment | ~70 |
| `04-mcps.yaml` | 4 MCP (Service + Deployment) | ~200 |
| `05-hostapi.yaml` | ServiceAccount + Service + Deployment | ~100 |
| `06-scaling.yaml` | HPA + PDB + Ingress + NodePort | ~130 |
| `kustomization.yaml` | Kustomize 统一入口 | ~20 |

合计 ~750 行 K8s YAML。

---

## 9. 学习路径建议

### 9.1 入门（1-2 天）

1. 安装 kind / minikube
2. 跑一遍 `kubectl apply -k k8s/`
3. 学习 `kubectl get/describe/logs/exec`
4. 试一下 `kubectl scale`

### 9.2 进阶（3-7 天）

1. 学 Helm（包管理）
2. 学 cert-manager（HTTPS 证书）
3. 学 ArgoCD（GitOps）
4. 学 Prometheus + Grafana（监控）
5. 学 Loki（日志）

### 9.3 生产级（1-2 周）

1. 装 ingress-nginx + cert-manager
2. 配 Prometheus operator
3. 配 ArgoCD 自动发布
4. 配 Velero 备份
5. 配 OPA 鉴权

### 9.4 必读书籍

- 《Kubernetes 权威指南》
- 《Kubernetes 实战》
- 官方文档：https://kubernetes.io/docs/home/

---

## 10. 常见问题

**Q: kind 在 Windows 上慢吗？**
A: 用 WSL2 后端会快很多。`kind create cluster --retain`。

**Q: StatefulSet 必须配 headless Service 吗？**
A: 是的，StatefulSet 通过 DNS 找 Pod（`pha-postgres-0.pha-postgres`）。

**Q: HPA 不工作？**
A: 需要装 metrics-server：
```bash
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
```

**Q: Ingress 404？**
A: 检查 ingress-nginx controller 装了吗，`kubectl get ingressclass`。

**Q: 私有镜像仓库怎么拉？**
A: 创建 `imagePullSecrets`：
```bash
kubectl create secret docker-registry regcred \
  --docker-server=xxx.com \
  --docker-username=xxx \
  --docker-password=xxx -n pha
# 然后在 Pod spec 加 imagePullSecrets: [{name: regcred}]
```

---

## 11. 总结

PHA v2 K8s manifest 已生产级：

- ✅ 30 个 K8s 资源
- ✅ 7 个 YAML + Kustomize 入口
- ✅ YAML 语法全部验证通过（`kubectl apply --dry-run`）
- ✅ Kustomize 渲染通过（`kubectl kustomize`）
- ✅ 含 HPA / PDB / Ingress / NodePort / NetworkPolicy
- ✅ 镜像就用现成 docker-compose 那些

下一步可学：Helm / cert-manager / Prometheus operator / ArgoCD。
