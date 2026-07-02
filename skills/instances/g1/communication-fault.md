---
id: g1-communication-fault
name: G1 通信故障处理
layer: instance
category: communication
severity: medium
version: 2.0.0
author: G1 Maintenance Team
applies_to:
  robot: g1
  firmware: ">=2.0"
extends:
  - universal/communication-fault-principles
  - humanoid/communication
references:
  ontology:
    - robots/g1/ontology.yaml
  objects:
    - g1.hw.network
    - g1.hw.dds
    - g1.if.topic.lowstate
triggers:
  - id: T1
    description: 话题延迟高
    ontology_field: g1.network.topic_latency_ms
    operator: ">"
    value: 50
    severity: notice
  - id: T2
    description: 话题丢失
    ontology_field: g1.network.topic_lost_rate
    operator: ">"
    value: 0.05
    severity: warning
  - id: T3
    description: 心跳超时
    ontology_field: g1.network.heartbeat_missed
    operator: ">"
    value: 3
    severity: critical
  - id: T4
    description: 数据包错误率高
    ontology_field: g1.network.packet_error_rate
    operator: ">"
    value: 0.01
    severity: warning
---

# Skill: G1 通信故障处理

## 引用上层 skill

- `universal/communication-fault-principles`
- `humanoid/communication`

## G1 通信架构

```
主控计算机(MCP / ROS2)
        │ Ethernet 千兆
        ▼
运动控制板(Unitree SDK2)
   │       │       │
   ▼       ▼       ▼
 左腿驱动 右腿驱动 躯干驱动
   (CAN)   (CAN)    (CAN)
```

主控 IP: `192.168.123.2`
运控 IP: `192.168.123.10`

## G1 诊断命令(分三层对应)

### 物理层

```bash
# 网线连通性
ping 192.168.123.10

# 链路检测
ethtool eth0 | grep "Link detected"

# 网卡 IP
ip addr show eth0
```

### 协议层

```bash
# 话题频率
ros2 topic hz {{ ontology.if.topic.lowstate }}

# 话题延迟
ros2 topic delay {{ ontology.if.topic.lowstate }}

# DDS 节点
ros2 daemon status
ros2 node list

# 带宽占用
sudo nethogs

# 丢包统计
netstat -s | grep -i drop
```

### 应用层

```bash
# 话题信息
ros2 topic info {{ ontology.if.topic.lowstate }}

# 单条消息内容
ros2 topic echo {{ ontology.if.topic.lowstate }} --once
```

## G1 调优参数

### DDS 缓冲区

```bash
sudo sysctl -w net.core.rmem_max=134217728
sudo sysctl -w net.core.wmem_max=134217728
```

### 巨帧(可选,提升大数据吞吐)

```bash
sudo ip link set dev eth0 mtu 9000
```

### G1 推荐 QoS 配置

| Topic 类型 | reliability | depth |
|---|---|---|
| 实时控制(/rt/lowstate) | best_effort | 10 |
| 命令(/cmd_vel) | reliable | 10 |
| 状态查询(参数) | reliable | 50 |
| 视觉/点云 | best_effort | 5 |

## G1 案例库

### CASE-2024-006: 高延迟导致控制滞后
- **现象**:关节响应慢,走路不协调
- **诊断**:延迟 > 100ms,WiFi 干扰
- **处置**:换有线 → 5ms

### CASE-2024-017: DDS 发现失败
- **现象**:节点间无法通信但网络通
- **诊断**:多网卡导致 DDS 用错接口
- **处置**:`ROS_LOCALHOST_ONLY=0` + 指定网卡

### CASE-2024-025: 交换机环路
- **现象**:网络时断时续,广播风暴
- **诊断**:网络拓扑环路
- **处置**:移除冗余 + 启用 STP

## G1 完全通信中断应急

1. 确保机器人安全姿态(切到 DAMPING)
2. 检查物理层
3. 重启网络:`sudo systemctl restart NetworkManager`
4. 重启 DDS:`ros2 daemon restart`
5. 最后手段:重启运控板
6. 仍无效:急停按钮人工介入

## 引用资源

- ROS2 DDS 配置指南
- Fast DDS 文档
- 宇树 SDK2 网络说明
