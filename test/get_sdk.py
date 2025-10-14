import limxsdk.robot.Joystick as Joystick
import limxsdk.robot.Robot as Robot
import limxsdk.robot.RobotType as RobotType

_robot = None
_joy = None


def get_sdk(robot_ip="127.0.0.1"):
    global _robot, _joy
    if _robot is None:
        r = Robot(RobotType.PointFoot)
        if not r.init(robot_ip):
            raise RuntimeError("Robot.init failed")
        _robot = r
    if _joy is None:
        _joy = Joystick()
    return _robot, _joy
