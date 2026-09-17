"""Project a MotionStudio Unitree G1 29-DOF CSV onto E1's 21 DOFs."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

try:
  from .pkl_to_npz import DEFAULT_MODEL, save_motion
except ImportError:  # Direct execution: python tools/mimic/csv_to_npz.py
  from pkl_to_npz import DEFAULT_MODEL, save_motion

G1_JOINT_NAMES = (
  "left_hip_pitch_joint",
  "left_hip_roll_joint",
  "left_hip_yaw_joint",
  "left_knee_joint",
  "left_ankle_pitch_joint",
  "left_ankle_roll_joint",
  "right_hip_pitch_joint",
  "right_hip_roll_joint",
  "right_hip_yaw_joint",
  "right_knee_joint",
  "right_ankle_pitch_joint",
  "right_ankle_roll_joint",
  "waist_yaw_joint",
  "waist_roll_joint",
  "waist_pitch_joint",
  "left_shoulder_pitch_joint",
  "left_shoulder_roll_joint",
  "left_shoulder_yaw_joint",
  "left_elbow_joint",
  "left_wrist_roll_joint",
  "left_wrist_pitch_joint",
  "left_wrist_yaw_joint",
  "right_shoulder_pitch_joint",
  "right_shoulder_roll_joint",
  "right_shoulder_yaw_joint",
  "right_elbow_joint",
  "right_wrist_roll_joint",
  "right_wrist_pitch_joint",
  "right_wrist_yaw_joint",
)
E1_JOINT_NAMES = G1_JOINT_NAMES[:13] + G1_JOINT_NAMES[15:19] + G1_JOINT_NAMES[22:26]
E1_JOINT_INDICES = [G1_JOINT_NAMES.index(name) for name in E1_JOINT_NAMES]


def parse_args() -> argparse.Namespace:
  parser = argparse.ArgumentParser(
    description="Convert a MotionStudio G1 29-DOF CSV to an E1 motion NPZ."
  )
  parser.add_argument("--input", type=Path, required=True)
  parser.add_argument("--output", type=Path, default=None)
  parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
  parser.add_argument(
    "--input-fps", "--fps", dest="input_fps", type=float, default=30.0
  )
  parser.add_argument("--output-fps", type=float, default=50.0)
  parser.add_argument(
    "--root-height-offset",
    type=float,
    default=-0.11,
    help="E1 pelvis-height calibration in meters (default: -0.11).",
  )
  return parser.parse_args()


def convert(
  input_path: Path,
  output_path: Path,
  model_path: Path,
  input_fps: float,
  output_fps: float,
  root_height_offset: float,
) -> None:
  input_path = input_path.expanduser().resolve()
  if not input_path.is_file():
    raise FileNotFoundError(input_path)
  if not np.isfinite(input_fps) or input_fps <= 0.0:
    raise ValueError(f"Input FPS must be positive, got {input_fps}")
  if not np.isfinite(output_fps) or output_fps <= 0.0:
    raise ValueError(f"Output FPS must be positive, got {output_fps}")
  if not np.isfinite(root_height_offset):
    raise ValueError("Root height offset must be finite")

  data = np.loadtxt(input_path, delimiter=",", dtype=np.float32, ndmin=2)
  if data.shape[1] != 36:
    raise ValueError(
      "Expected 36 columns: root_xyz(3), root_quat_xyzw(4), joints(29); "
      f"got {data.shape[1]}"
    )
  if not np.isfinite(data).all():
    raise ValueError("CSV contains NaN or infinity")

  root_pos = data[:, :3].copy()
  root_pos[:, 2] += root_height_offset
  root_pos, root_rot, dof_pos = resample_motion(
    root_pos,
    data[:, 3:7],
    data[:, 7:][:, E1_JOINT_INDICES],
    input_fps,
    output_fps,
  )
  save_motion(
    {
      "root_pos": root_pos,
      "root_rot": root_rot,
      "dof_pos": dof_pos,
      "fps": output_fps,
      "meta": {"root_rot_convention": "xyzw"},
    },
    output_path,
    model_path,
  )


def resample_motion(
  root_pos: np.ndarray,
  root_rot: np.ndarray,
  dof_pos: np.ndarray,
  input_fps: float,
  output_fps: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
  """Resample positions linearly and xyzw quaternions with shortest-path SLERP."""
  if len(root_pos) < 2 or input_fps == output_fps:
    return root_pos, root_rot, dof_pos

  source_t = np.arange(len(root_pos), dtype=np.float64) / input_fps
  target_t = (
    np.arange(int(np.floor(source_t[-1] * output_fps)) + 1, dtype=np.float64)
    / output_fps
  )

  def linear(values: np.ndarray) -> np.ndarray:
    return np.column_stack(
      [np.interp(target_t, source_t, values[:, i]) for i in range(values.shape[1])]
    ).astype(np.float32)

  quats = root_rot.astype(np.float64, copy=True)
  quats /= np.linalg.norm(quats, axis=1, keepdims=True)
  for i in range(1, len(quats)):
    if np.dot(quats[i - 1], quats[i]) < 0.0:
      quats[i] *= -1.0
  lower = np.minimum((target_t * input_fps).astype(int), len(quats) - 2)
  alpha = ((target_t - source_t[lower]) * input_fps)[:, None]
  q0, q1 = quats[lower], quats[lower + 1]
  dot = np.clip(np.sum(q0 * q1, axis=1, keepdims=True), -1.0, 1.0)
  theta = np.arccos(dot)
  sin_theta = np.sin(theta)
  small = np.abs(sin_theta) < 1.0e-8
  weights0 = np.where(small, 1.0 - alpha, np.sin((1.0 - alpha) * theta) / sin_theta)
  weights1 = np.where(small, alpha, np.sin(alpha * theta) / sin_theta)
  resampled_quats = weights0 * q0 + weights1 * q1
  resampled_quats /= np.linalg.norm(resampled_quats, axis=1, keepdims=True)
  return linear(root_pos), resampled_quats.astype(np.float32), linear(dof_pos)


def main() -> None:
  args = parse_args()
  convert(
    args.input,
    args.output or args.input.with_suffix(".npz"),
    args.model,
    args.input_fps,
    args.output_fps,
    args.root_height_offset,
  )


if __name__ == "__main__":
  main()
