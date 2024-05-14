import time
import sys

from interfaces.hw_interface.motors_control import move_motor, move_camera, move_arm
from interfaces.hw_interface.sensors import read_sensor_data, get_gps
from interfaces.mqtt_interface.robot_client import RobotMQTTClient
from interfaces.config_interface import config_interface
from state_machine.enums import RobotState, RobotEvent
from interfaces.hw_interface.auto import auto_motion
from interfaces.mqtt_interface.admin_client import *
from state_machine.stack import Stack
from config import env_get, env_update


# run_rtmp(f"{Config.RTMP_URL}/{name}")

motion_queue = []
admin_queue = []
WAIT_TIME = 0.0001


class RobotStateMachine:

    def __init__(self):
        self.states = Stack(3)
        self.transition(RobotEvent.START_INIT)

    def state_setter(self, value):
        self.states.push(value)
        cur = self.states.cur().name if self.states.cur() else None
        prev = self.states.prev().name if self.states.prev() else None
        print(f"<prev: {prev}, cur: {cur}>")

    def transition(self, event, data=None):
        print(f"Event {RobotEvent(event).name} has occurred")
        match event:
            case RobotEvent.START_INIT:
                self.state_setter(RobotState.INITIAL)
                self.init_robot()
                self.transition(RobotEvent.FINISH_INIT)
            case RobotEvent.FINISH_INIT:
                self.state_setter(RobotState.IDLE)
                self.idle_mode()
            case RobotEvent.START_MISN:
                self.state_setter(RobotState.AUTONOMOUS)
                self.auto_mode()
            case RobotEvent.HALT_MISN:
                self.state_setter(RobotState.IDLE)
                self.idle_mode()
            case RobotEvent.AUTO:
                self.state_setter(RobotState.AUTONOMOUS)
                self.auto_mode()
            case RobotEvent.CONTROL:
                self.state_setter(RobotState.CONTROLLED)
                self.control_mode()
            case RobotEvent.UPDATE:
                self.state_setter(RobotState.UPDATING)
                self.update_robot(data)
                self.transition(RobotEvent.BACK)
            case RobotEvent.DELETE:
                self.state_setter(RobotState.INACTIVE)
                self.delete_robot()
            case RobotEvent.BACK:
                prev = self.states.back()
                match prev:
                    case RobotState.IDLE:
                        self.transition(RobotEvent.HALT_MISN)
                    case RobotState.AUTONOMOUS:
                        self.transition(RobotEvent.AUTO)
                    case RobotState.CONTROLLED:
                        self.transition(RobotEvent.CONTROL)
                    case _:
                        print("Invalid state")

    def init_robot(self):
        skipped, data = config_interface()
        broker_addr = data["BROKER_ADDR"]
        print(f"a MQTT broker has detected with IP address {broker_addr}")
        env_update(data)
        if not skipped:
            create_mqtt_user(broker_addr, data["NAME"], data["PASSWORD"])

        self.name = env_get("NAME")
        self.password = env_get("PASSWORD")
        self.broker_name = env_get("BROKER_NAME")
        self.mqtt_client = RobotMQTTClient(
            self.name,
            self.password,
            self.broker_name,
            broker_addr,
            motion_queue,
            admin_queue,
        )

    def update_robot(self, data):
        env_update(data)
        self.mqtt_client.update_creds(data)
        # TO-DO: restart rtmp
        pass

    def delete_robot(self):
        self.mqtt_client.stop()
        env_update(
            {"NAME": None, "PASSWORD": None, "BROKER_ADDR": None, "BROKER_NAME": None}
        )
        print("Robot is deactivating...")
        sys.exit()
        # TO-DO: stop rtmp

    def idle_mode(self):
        global motion_queue
        while True:
            self.check_admin_queue()
            if motion_queue:
                motion_queue = []
            time.sleep(WAIT_TIME)
        # TO-DO: stop rtmp

    def auto_mode(self):
        while True:
            self.check_admin_queue()
            data = read_sensor_data()
            gps = get_gps()
            if data:
                topic = f"cloud/reg/{self.broker_name}/{self.name}/sensor-data"
                self.mqtt_client.publish(topic, data)
            if gps:
                topic = f"cloud/reg/{self.broker_name}/{self.name}/gps"
                self.mqtt_client.publish(topic, data)
            auto_motion()
            time.sleep(WAIT_TIME)
        # TO-DO: rtmp

    def control_mode(self):
        while True:
            self.check_admin_queue()
            self.check_motion_queue()
            data = read_sensor_data()
            gps = get_gps()
            if data:
                topic = f"cloud/reg/{self.broker_name}/{self.name}/sensor-data"
                self.mqtt_client.publish(topic, data)
            if gps:
                topic = f"cloud/reg/{self.broker_name}/{self.name}/gps"
                self.mqtt_client.publish(topic, data)
            time.sleep(WAIT_TIME)
        # TO-DO: rtmp

    def check_admin_queue(self):
        elem = admin_queue.pop(0) if admin_queue else None
        if elem == None:
            return
        _, data = elem
        match data["command"]:
            case "start":
                self.transition(RobotEvent.START_MISN)
            case "pause":
                self.transition(RobotEvent.HALT_MISN)
            case "continue":
                self.transition(RobotEvent.BACK)
            case "end":
                self.transition(RobotEvent.HALT_MISN)
            case "update":
                new_data = {"NAME": data["name"], "PASSWORD": data["password"]}
                self.transition(RobotEvent.UPDATE, new_data)
            case "delete":
                self.transition(RobotEvent.DELETE)
            case "auto":
                if self.states.cur() == RobotState.CONTROLLED:
                    self.transition(RobotEvent.AUTO)
            case "control":
                if self.states.cur() == RobotState.AUTONOMOUS:
                    self.transition(RobotEvent.CONTROL)
            case _:
                print("Invalid admin command")

    def check_motion_queue(self):
        elem = motion_queue.pop(0) if motion_queue else None
        if elem == None:
            return
        _, data = elem
        match data["device"]:
            case "motor":
                move_motor(data["value"])
            case "camera":
                move_camera(data["value"])
            case "arm":
                move_arm(data["command"])
            case _:
                print("Invalid motion command")