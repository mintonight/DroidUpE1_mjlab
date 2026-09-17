import numpy as np

from tools.mimic.csv_to_npz import resample_motion
from tools.mimic.pkl_to_npz import _differentiate_quaternions_xyzw


def test_quaternion_angular_velocity() -> None:
  angles = np.arange(3, dtype=np.float32) * 0.1
  quaternions = np.column_stack(
    (np.zeros((3, 2)), np.sin(angles / 2), np.cos(angles / 2))
  )
  np.testing.assert_allclose(
    _differentiate_quaternions_xyzw(quaternions, fps=10.0),
    np.tile((0.0, 0.0, 1.0), (3, 1)),
    atol=1.0e-6,
  )


def test_resample_motion_preserves_duration_and_rotation() -> None:
  root_pos = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]], dtype=np.float32)
  root_rot = np.array([[0.0, 0.0, 0.0, 1.0], [0.0, 0.0, 1.0, 0.0]], dtype=np.float32)
  dof_pos = np.array([[0.0], [1.0]], dtype=np.float32)

  pos, rot, joints = resample_motion(root_pos, root_rot, dof_pos, 1.0, 2.0)

  np.testing.assert_allclose(pos[:, 0], [0.0, 0.5, 1.0], atol=1.0e-6)
  np.testing.assert_allclose(joints[:, 0], [0.0, 0.5, 1.0], atol=1.0e-6)
  np.testing.assert_allclose(rot[1], [0.0, 0.0, 2**-0.5, 2**-0.5], atol=1.0e-6)
