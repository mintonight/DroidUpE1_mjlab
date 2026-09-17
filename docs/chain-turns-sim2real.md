# Chain Turns 111D 策略 Sim2Real 说明

## 交付文件

- 策略：`sim2sim/policy/mimic/chain_turns_yawfix_50hz.onnx`
- 参考动作：`dataset/e1_21dof/mimic/chain_turns/DAP_Chain_Turns_00001.npz`
- MuJoCo 参考实现：`sim2sim/sim2sim_e1_21dof_mimic.py`

## 观测接口

该策略沿用 Victory 动作的 111 维 No-State actor 接口，没有新增目标角速度观测。

| 切片 | 维数 | 内容 | 单位/坐标系 |
| --- | ---: | --- | --- |
| `obs[0:42]` | 42 | 参考关节位置 + 参考关节速度 | rad、rad/s |
| `obs[42:45]` | 3 | 重力投影 | torso 坐标系，直立时约 `[0,0,-1]` |
| `obs[45:48]` | 3 | 实测 torso 角速度 | torso 坐标系，rad/s |
| `obs[48:69]` | 21 | `joint_pos - default_joint_pos` | rad |
| `obs[69:90]` | 21 | 实测关节速度 | rad/s |
| `obs[90:111]` | 21 | 上一次策略原始输出 | 无量纲 |

## ONNX 接口

```text
输入： obs       float32 [1, 111]
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
3. 按上表构造 111 维观测，并检查所有值均为有限数。
4. 执行 ONNX，按下式生成关节位置目标：

   ```text
   q_des = default_joint_pos + action_scale * actions
   ```

5. 将 `actions` 保存为下一周期的 `previous_action`。
6. 动作共 342 帧。单次播放在第 341 帧保持；循环播放使用 `frame % 342`。

转圈能力来自正确的 50 Hz 动作时序，以及 torso 朝向和角速度跟踪奖励；部署端
不需要额外构造目标角速度输入。

## 上机前检查

- 核对 21 个关节的名称、方向、零点和电机 ID 映射。
- 核对 IMU 四元数顺序、旋转方向及角速度坐标系。
- 保留实机的关节限位、目标变化率限制、力矩限制、急停和失联保护。
- 先悬挂或使用保护架测试，再逐步放开力矩限制。
- MuJoCo 检查命令：

  ```bash
  python sim2sim/sim2sim_e1_21dof_mimic.py \
    --policy sim2sim/policy/mimic/chain_turns_yawfix_50hz.onnx
  ```
