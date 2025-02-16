import os
import zipfile
import shutil
import subprocess
import ftplib
import paho.mqtt.client as mqtt
import socket
import ssl
import functools
from ftplib import FTP, error_temp, error_perm, error_proto, error_reply
import time
import threading
import json
import asyncio
import json
import argparse

def parse_arguments():
    """Parses command-line arguments for the input 3MF file."""
    parser = argparse.ArgumentParser(description="Slice and print a 3MF file.")
    parser.add_argument("input_3mf", help="Path to the input 3MF file")
    return parser.parse_args()

# Load configuration from config.json
def load_config(config_file="config.json"):
    """Loads the configuration from a JSON file."""
    try:
        with open(config_file, "r") as file:
            config = json.load(file)
        print("✅ Configuration loaded successfully!")
        return config
    except Exception as e:
        print(f"❌ Error loading config: {e}")
        exit(1)  # Exit the script if config fails


def extract_3mf(archive_path, extract_path):
    with zipfile.ZipFile(archive_path, 'r') as zip_ref:
        zip_ref.extractall(extract_path)

def slice_3mf(input_3mf, output_dir, slicer_path, settings_files):
    settings_cmd = " ".join([f'--load-settings "{s}"' for s in settings_files])
    command = f'"{slicer_path}" {settings_cmd} --outputdir "{output_dir}" --slice 1 "{input_3mf}"'
    subprocess.run(command, shell=True, check=True)

def repackage_3mf(folder_path, output_3mf):
    if os.path.exists(output_3mf):
        os.remove(output_3mf)
    shutil.make_archive(output_3mf.replace('.3mf', ''), 'zip', folder_path)
    os.rename(output_3mf.replace('.3mf', '.zip'), output_3mf)
    return output_3mf

class ImplicitFTP_TLS(ftplib.FTP_TLS):
    """
    FTP_TLS subclass that automatically wraps sockets in SSL to support implicit FTPS.
    see https://stackoverflow.com/a/36049814
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._sock = None

    @property
    def sock(self):
        """Return the socket."""
        return self._sock

    @sock.setter
    def sock(self, value):
        """When modifying the socket, ensure that it is ssl wrapped."""
        if value is not None and not isinstance(value, ssl.SSLSocket):
            value = self.context.wrap_socket(value)
        self._sock = value

    def ntransfercmd(self, cmd, rest=None):
        conn, size = ftplib.FTP.ntransfercmd(self, cmd, rest)
        if self._prot_p:
            session = self.sock.session
            if isinstance(self.sock, ssl.SSLSocket):
                session = self.sock.session
            conn = self.context.wrap_socket(conn,
                                            server_hostname=self.host,
                                            session=session)
        return conn, size


def upload_ftp(file_path, ftp_server, ftp_user, ftp_password, ftp_target_path,retries):
    file_size = os.path.getsize(file_path)  # Get file size
    uploaded = 0  # Track bytes uploaded

    def progress_callback(data):
        nonlocal uploaded
        uploaded += len(data)
        percent = (uploaded / file_size) * 100
        print(f"\rUploaded: {uploaded}/{file_size} bytes ({percent:.2f}%)", end="")

    attempt = 0
    while attempt < retries:
        try:
            with ftp_connection(ftp_server,ftp_user,ftp_password)  as ftp:
                
                ftp.set_pasv(True)  # ✅ Use Passive Mode

                with open(file_path, 'rb') as f:
                    ftp.storbinary(f'STOR {ftp_target_path}', f, 8192, callback=progress_callback)  # ✅ Use larger buffer

                print("\n✅ File uploaded successfully.")
                ftp.close()  # Properly close FTP connection
                return  # Exit function if successful

        except (TimeoutError):
            ftp.close()  # Ensure connection closes properly
            print("\nFile uploaded successfully.")
            return  # Exit function if successful

        except( error_temp, error_proto) as e:
            attempt += 1
            print(f"\nError: {e}\nRetrying {attempt}/{retries}...")
            time.sleep(5)  # Wait before retrying
        except (error_perm, error_reply) as e:
            print(f"\nFatal error: {e}. Upload aborted.")
            return  # Don't retry on permission or reply errors
        finally:
            if 'ftp' in locals():
                try:
                    if ftp.sock:
                        ftp.sock.close()  # Force-close if not already closed
                    ftp.close()
                except:
                    pass

    print("\nUpload failed after multiple attempts.")


def ftp_connection(host,user,password) -> ImplicitFTP_TLS:
    print("creating tls context")
    ftp = ImplicitFTP_TLS(context=create_local_ssl_context())
    print('connecting ftp host ',host)
    ftp.connect(host=host, port=990, timeout=2)
    print('logging in as ',user)
    ftp.login(user=user, passwd=password)
    ftp.prot_p()
    return ftp
    

@functools.lru_cache(maxsize=1)
def create_local_ssl_context():
    """
    This context validates the certificate for TLS connections to local printers.
    """
    script_path = os.path.abspath(__file__)
    directory_path = os.path.dirname(script_path)
    certfile = directory_path + "\\settings\\bambu.cert"
    context = ssl.create_default_context(cafile=certfile)
    # Ignore "CA cert does not include key usage extension" error since python 3.13
    # See note in https://docs.python.org/3/library/ssl.html#ssl.create_default_context
    context.verify_flags &= ~ssl.VERIFY_X509_STRICT
    # Workaround because some users get this error despite SNI: "certificate verify failed: IP address mismatch"
    context.check_hostname = False
    return context

def parse_config(json_config_path, gcode_filename):

    # Load parameters from the JSON file
    with open(json_config_path, "r") as file:
        config = json.load(file)

    # Ensure we have a valid print object
    if "print" not in config:
        print("❌ Error: JSON file must contain a 'print' object.")
        return
    
    # Set the fixed URL, but dynamically insert the correct filename
    fixed_url = f"file:///sdcard/{gcode_filename}"

    # Update the config dictionary with the filename
    config["print"]["url"] = fixed_url  # Update the URL
    config["print"]["subtask_name"] =gcode_filename.removesuffix(".gcode.3mf") 

    # Convert to JSON string for publishing
    return  json.dumps(config)

def setup_tls(client):
    client.tls_set_context(create_local_ssl_context())


def publish_mqtt(json_config_path, gcode_filename, mqtt_broker,access_code,serial_number,retries=3):
    """
    Publishes a print command to the printer's MQTT topic.
    
    :param json_config_path: Path to the JSON file containing print parameters
    :param serial_number: Printer serial number
    :param gcode_filename: The gcode file inside the 3mf archive
    :param mqtt_broker: MQTT broker address (default: "mqtt.example.com")
    :param mqtt_port: MQTT broker port (default: 1883)
    """
    message = parse_config(json_config_path, gcode_filename)
        # Define the MQTT topic
    topic = f"device/{serial_number}/request"

    def on_connect(client, userdata, flags, rc):
        """Callback function for MQTT connection status."""
        if rc == 0:
            print("✅ MQTT Connected Successfully")
            client.connected_flag = True
        else:
            print(f"❌ MQTT Connection Failed with Code {rc}")
            client.connected_flag = False

    # Create MQTT client
    client = mqtt.Client()
    client.connected_flag = False  # Custom attribute for connection status
    client.username_pw_set('bblp',access_code)
    client.on_connect = on_connect  # Attach connection callback
    client.reconnect_delay_set(min_delay=1, max_delay=1)
    setup_tls(client)


    for attempt in range(retries):
        try:
            print(f"🔄 Attempting MQTT connection to {mqtt_broker} (Try {attempt + 1}/{retries})...")
            client.connect(mqtt_broker, 8883, 60)  # Try connecting

            client.loop_start()  # Start the loop to process connection
            time.sleep(2)  # Wait for the connection to establish

            if client.connected_flag:
                print(f"📤 Publishing to topic: {topic}")
                print(f"📤 Publishing message: {message}")
                client.publish(topic, message)  # Send the message
                client.loop_stop()
                client.disconnect()
                print("✅ MQTT Message Published Successfully")
                return  # Exit function if successful
            else:
                print(f"⚠️ MQTT Connection attempt {attempt + 1} failed. Retrying...")
                client.loop_stop()
                client.disconnect()
        except Exception as e:
            print(f"❌ MQTT Error on attempt {attempt + 1}: {e}")

    # If all retries fail
    raise Exception("❌ MQTT Connection Failed After Multiple Attempts")
