import json
import time

import paho.mqtt.client as paho
from paho import mqtt


def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print(f"Connected to {client._port}")
    else:
        print(rc)


def on_disconnect(client, userdata, rc, properties=None):
    print("Disconnected from MQTT broker")


def on_message(client, userdata, msg):
    data_str = msg.payload.decode("utf-8")
    data = json.loads(data_str)
    print(msg.topic, data)


cloud_client = paho.Client(client_id="cloud-test", userdata=None, protocol=paho.MQTTv5)
# cloud_client = paho.Client(client_id="cloud-test", userdata=None)
cloud_client.on_connect = on_connect
cloud_client.on_message = on_message
cloud_client.on_disconnect = on_disconnect
cloud_client.tls_set(tls_version=mqtt.client.ssl.PROTOCOL_TLS)
cloud_client.username_pw_set("cloud-test", "Cloud-Test12")
# cloud_client.username_pw_set("admin-ugv", "UgvAdmin@1984")
cloud_client.loop_start()
cloud_client.connect("27c434d04ed54e43a4c65102e26353b8.s1.eu.hivemq.cloud", 8883)
# cloud_client.connect("192.168.68.127", 1883)

topic = "cloud/admin/test-broker/all/mission"

data = {"command": "start", "username": "test-ugv", "password": "test"}
# data = {"username": "test-a", "password": "test"}
cloud_client.publish(topic, payload=json.dumps(data), qos=1)

time.sleep(3)

cloud_client.disconnect()
cloud_client.loop_stop()
