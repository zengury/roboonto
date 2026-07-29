# 数据来源与溯源

`robots/` 中的旧 Pack 包含从公开厂商资料提取的事实性工程规格，例如关节限位、
扭矩、Topic、API ID 和故障码。原始文档与 SDK 的版权属于各自厂商。

RoboOnto 0.9 迁移器把旧 `source` 转换为 PackModule `Provenance`。每条事实仍可追溯
到 kind、locator 和 extractor。标准词表映射只是与 IEEE 1872.1、IEEE 1872.2 和
RoSO 的参考性术语对齐，不构成合规或认证声明。

## AgiBot X2

| 来源 | 类型 | 用途 |
|---|---|---|
| AimDK 文档（`aimdk.docx` locator） | 公开厂商文档 | 动作、接口、PMU/电源、故障码 |
| X2 URDF | 厂商发布 | 运动学、关节和 Link 参数 |
| 真机验证 | 第一方测量 | Capability 边界与 probe 结果 |

## Unitree G1 EDU

| 来源 | 类型 | 用途 |
|---|---|---|
| [`unitree_sdk2`](https://github.com/unitreerobotics/unitree_sdk2) | 公开 GitHub，BSD-3-Clause | 运动、机械臂、音频 API 和 DDS IDL |
| [`unitree_ros`](https://github.com/unitreerobotics/unitree_ros) | 公开 GitHub | URDF、关节限位和 STL Mesh |
| Unitree 公开文档 | 厂商文档 | 模式机和 FSM ID |

## MuJoCo HalfCheetah

| 来源 | 类型 | 用途 |
|---|---|---|
| [Gymnasium / MuJoCo](https://github.com/Farama-Foundation/Gymnasium) | 开源项目 | 仿真机器人模型，不代表物理硬件 |

## 更正与删除

如果权利人认为某项提取超出事实规格的合理使用，或发现事实错误，请提交 Issue。
Provenance locator 使更正可以精确定位并接受审计。
