import requests
import paho.mqtt.client as mqtt
from requests.auth import HTTPDigestAuth
import re
from bs4 import BeautifulSoup
import logging
import json
import time
import os
import datetime

from const import IS_CONTAINER, VERSION, SLEEP_INTERVAL, ENTITIES

# Suppress only the single InsecureRequestWarning from urllib3 needed
requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)

def replace_periods(sensor_name):
    return re.sub(r'\W', '_', sensor_name.lower())

if (IS_CONTAINER):
    IODATA_URL = os.getenv("IODATA_URL","http://192.168.8.1/gui/status_embedded.cgi")
    IODATA_PASSWORD=os.getenv("IODATA_PASSWORD","")
    IODATA_USERNAME=os.getenv("IODATA_USERNAME","admin")
    MQTT_HOST = os.getenv("MQTT_HOST","192.168.230.236")
    MQTT_PASSWORD=os.getenv("MQTT_PASSWORD","")
    MQTT_USERNAME=os.getenv("MQTT_USERNAME","frigate")   

def get_signal_values():
    print("In get_signal_values...")

    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "en-US,en;q=0.9,ja-JP;q=0.8,ja;q=0.7",
        "Cache-Control": "max-age=0",
        "Connection": "keep-alive",
        "Referer": IODATA_URL,
        "Upgrade-Insecure-Requests": "1",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
    }
    
    response = requests.get(IODATA_URL, headers=headers, auth=HTTPDigestAuth(IODATA_USERNAME, IODATA_PASSWORD), verify=False)
    
    if response.status_code != 200:
        raise Exception(f"Failed to retrieve data, status code: {response.status_code}")
    
    soup = BeautifulSoup(response.text, "html.parser")
    
    keys_to_extract = {"share.rsrp": None, "share.sinr": None}
    
    for div in soup.find_all("div", class_="setting"):
        label_script = div.find("div", class_="label")
        value_text = div.text.strip().split("\n")[-1].strip()
        if label_script:
            match = re.search(r'Capture\((.*?)\)', str(label_script))
            if match and match.group(1) in keys_to_extract:
                keys_to_extract[match.group(1)] = value_text
    
    return keys_to_extract

class IODataSensor:
    def __init__(self, name_constant):
        name_replace=name_constant
        name_object=ENTITIES[name_constant]
        self.name = f"iodata_{name_replace}"
        self.device_class = name_object['type'],
        self.unit_of_measurement = name_object['unit'],
        test = name_object.get('attribute')
        if (test != None):
           self.state_class = name_object['attribute']
        else:
            self.state_class = "measurement"
        self.state_topic = f"homeassistant/sensor/iodata_{name_replace}/state"
        self.unique_id = f"iodata_{name_replace}"
        self.device = {
            "identifiers": [f"iodata_{name_replace}"][0],
            "name": f"iodata {name_replace}",
        }

    def to_json(self):
        return {
            "name": self.name,
            "device_class": self.device_class[0],
            "unit_of_measurement": self.unit_of_measurement[0],
            "state_class": self.state_class,
            "state_topic": self.state_topic,
            "unique_id": self.unique_id,
            "device": self.device
        }


def initialize():
    logger = logging.getLogger(__name__)
    logger.info(f"Initialization starting...")
    print("Initialization starting...")
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set(MQTT_USERNAME,MQTT_PASSWORD)
    try:
      client.connect(MQTT_HOST, 1883)
    except Exception as e:
        print("Error connecting to MQTT Broker: " + str(e))

    client.loop_start()

    for entity in ENTITIES:
        iodata_sensor=IODataSensor(entity)
        # Convert dictionary to JSON string
        serialized_message = json.dumps(iodata_sensor.to_json())
        print(f"Sending sensor -> {serialized_message}")
        logger.info(f"Sending sensor -> {serialized_message}")
        print(f"entity: homeassistant/sensor/iodata_{entity}/config")

        try:
            ret = client.publish(f"homeassistant/sensor/iodata_{entity}/config", payload=serialized_message, qos=2, retain=True)
            ret.wait_for_publish()
            if ret.rc == mqtt.MQTT_ERR_SUCCESS:
                pass
            else:
                print("Failed to queue message with error code " + str(ret))
        except Exception as e:
            print("Error publishing message: " + str(e))   

    client.loop_stop()        
    try:
        client.disconnect()
    except Exception as e:
        print("Error disconnecting from MQTT Broker: " + str(e))
    logger.info(f"Initialization complete...")
    print("Initialization complete...")

def request_and_publish():

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set(MQTT_USERNAME,MQTT_PASSWORD)

    logger = logging.getLogger(__name__)

    sensors = get_signal_values()

    try:
        client.connect(MQTT_HOST, 1883)
    except Exception as e:
        print("Error connecting to MQTT Broker: " + str(e))

    client.loop_start()

    for entity, value in sensors.items():

        print(f"{entity} -> {value}")
        try:
            ret = client.publish(f"homeassistant/sensor/iodata_{replace_periods(entity)}/state", payload=value, qos=2, retain=False)  
            ret.wait_for_publish()
            if ret.rc == mqtt.MQTT_ERR_SUCCESS:
                pass
            else:
                print("Failed to queue message with error code " + str(ret))
        except Exception as e:
            print("Error publishing message: " + str(e))

    client.loop_stop()
    try:
        client.disconnect()
    except Exception as e:
        print("Error disconnecting from MQTT Broker: " + str(e))


if __name__ == '__main__':
    logger = logging.getLogger(__name__)
    logger.info(f"I am iodata_status_fetcher running version {VERSION}")
    print(f"I am iodata_status_fetcher running version {VERSION}")
    initialize()

    while True:
        request_and_publish()
        logger.info(f"It is {datetime.datetime.now()} .. I am sleeping for {SLEEP_INTERVAL}")
        print(f"It is {datetime.datetime.now()} ... I am sleeping for {SLEEP_INTERVAL}")
        time.sleep(SLEEP_INTERVAL)