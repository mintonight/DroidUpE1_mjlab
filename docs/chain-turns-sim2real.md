# Chain Turns 114D 策略 Sim2Real 说明

## 交付文件

- 策略：`sim2sim/policy/mimic/chain_turns_yawfix_50hz.onnx`
- 参考动作：`dataset/e1_21dof/mimic/chain_turns/DAP_Chain_Turns_00001.npz`
- MuJoCo 参考实现：`sim2sim/sim2sim_e1_21dof_mimic.py`


## 观测修改

旧 Victory 策略的 actor 输入为 111 维。本策略在 `command` 后新增 3 维
`motion_anchor_ang_vel_b`，输入变为 114 维。

| 切片 | 维数 | 内容 | 单位/坐标系 |
| --- | ---: | --- | --- |
| `obs[0:42]` | 42 | 参考关节位置 + 参考关节速度 | rad、rad/s |
| `obs[42:45]` | 3 | 参考 torso 角速度 | torso 坐标系，rad/s |
| `obs[45:48]` | 3 | 重力投影 | torso 坐标系，直立时约 `[0,0,-1]` |
| `obs[48:51]` | 3 | 实测 torso 角速度 | torso 坐标系，rad/s |
| `obs[51:72]` | 21 | `joint_pos - default_joint_pos` | rad |
| `obs[72:93]` | 21 | 实测关节速度 | rad/s |
| `obs[93:114]` | 21 | 上一次策略原始输出 | 无量纲 |

参考 torso 角速度的计算方式为：

```text
motion_anchor_ang_vel_b = R(robot_torso_quat_w)^-1 * reference_torso_ang_vel_w
```

使用 ONNX 参考输出时，`body_ang_vel_w` 的 torso 当前位于索引 7；使用 NPZ
时应通过 `body_names` 查找 `torso_link`，不要硬编码索引。实机 IMU 四元数必须先
统一为“torso 到世界”的旋转约定，再执行逆旋转。

## ONNX 接口

```text
输入： obs       float32 [1, 114]
       time_step float32 [1, 1]

输出： actions        float32 [1, 21]
       joint_pos      float32 [1, 21]
       joint_vel      float32 [1, 21]
       body_pos_w     float32 [1, 14, 3]
       body_quat_w    float32 [1, 14, 4]
       body_lin_vel_w float32 [1, 14, 3]
       body_ang_vel_w float32 [1, 14, 3]
```

关节顺序、默认关节角、action scale、Kp 和 Kd 均保存在 ONNX metadata 中。
实机 SDK 的电机编号不能直接当作策略顺序，必须按 `joint_names` 建立映射。

## 控制循环

1. 先用限速插值移动到参考动作第 0 帧，`previous_action` 清零。
2. 策略以 50 Hz 运行，即每 20 ms 更新一次。
3. 按上表构造 114 维观测并检查所有值均为有限数。
4. 执行 ONNX，按下式生成关节位置目标：

   ```text
   q_des = default_joint_pos + action_scale * actions
   ```

5. 将 `actions` 保存为下一周期的 `previous_action`。
6. 动作共 342 帧。单次播放在第 341 帧保持；循环播放使用 `frame % 342`。

`sim2sim_e1_21dof_mimic.py` 为接口的可运行参考：它与训练一致，从第 1 帧开始
首次推理，并兼容旧 111D 与新 114D 策略。

## 上机前检查

- 核对 21 个关节的名称、方向、零点和电机 ID 映射。
- 核对 IMU 四元数顺序、旋转方向及角速度坐标系。
- 使用 ONNX metadata 中的参数，并保留实机的关节限位、目标变化率限制、力矩
  限制、急停和失联保护。
- 先悬挂或保护架测试，再以较低力矩限制测试站立过渡和完整动作。
- MuJoCo 检查命令：

  ```bash
  python sim2sim/sim2sim_e1_21dof_mimic.py \
    --policy sim2sim/policy/mimic/chain_turns_yawfix_50hz.onnx
  ```

文件 SHA-256：

```text
ONNX 89a4bfdde7c17f868ce130e7e1176c21555ff7d483b8e142a6c15c62d2a33010
NPZ  1795face793fd4f7896a806bd9fd76fcbe3a2392f3d2f845106e5067c77641a2
```
