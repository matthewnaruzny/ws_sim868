#  Copyright (c) 2023-2024. Matthew Naruzny.

import threading
import time
import serial
import uuid
import logging
import traceback
import queue

import RPi.GPIO as GPIO

class GPSData:
    def __init__(self, cgnsinf=None):
        self.cgnsinf = ""
        self.run_status = 0
        self.fix_status = 0
        self.timestamp = ""
        self.latitude = 0
        self.longitude = 0
        self.altitude = 0
        self.speed = 0
        self.course = 0
        self.fix_mode = 0
        self.hdop = 0
        self.pdop = 0
        self.vdop = 0
        self.satellite_visible = 0
        self.satellite_used = 0
        self.glonass_visible = 0
        self.cn0_max = 0
        self.hpa = 0
        self.vpa = 0

        if cgnsinf is not None:
            try:
                self.cgnsinf = cgnsinf
                data = cgnsinf.split(',')
                self.run_status = int(data[0])
                self.fix_status = int(data[1])
                if data[2] != '':
                    self.timestamp = round(float(data[2]))
                if data[3] != '':
                    self.latitude = float(data[3])
                if data[4] != '':
                    self.longitude = float(data[4])
                if data[5] != '':
                    self.altitude = float(data[5])
                if data[6] != '':
                    self.speed = float(data[6])
                if data[7] != '':
                    self.course = float(data[7])
                if data[8] != '':
                    self.fix_mode = int(data[8])
                if data[10] != '':
                    self.hdop = float(data[10])
                if data[11] != '':
                    self.pdop = float(data[11])
                if data[12] != '':
                    self.vdop = float(data[12])
                if data[14] != '':
                    self.satellite_visible = int(data[14])
                if data[15] != '':
                    self.satellite_used = int(data[15])
                if data[16] != '':
                    self.glonass_visible = int(data[16])
                if data[17] != '':
                    self.cn0_max = float(data[17])
                if data[18] != '':
                    self.hpa = float(data[18])
                if data[19] != '':
                    self.vpa = float(data[19])
            except (IndexError, ValueError):
                logging.error("Malformed GPS Data")
                logging.error(traceback.format_exc())
    def __str__(self):
        return self.cgnsinf




class ModemUnit:
    def __init__(self, port='/dev/ttyS0', baudrate=115200, log=True, http_reinit=3):

        # Logging
        if log:
            logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

        # Serial Config
        self.__serial_port = port
        self.__serial_baudrate = baudrate
        self.connect()

        # Serial
        self.__ser = serial.Serial(port, baudrate=baudrate)
        self.__write_lock = False
        self.__command_queue = queue.Queue()
        self.__command_last = ""
        self.__command_last_time = 0

        self.__last_health = 0

        self.__imei = None

        # GPS
        self.__gnss_active = False
        self.__gnss_pwr = False
        self.__gnss_rate = 0 # 0 - Off
        self.__gnss_loc = GPSData()

        # Network
        self.__network_active = False
        self.__apn_config = None

        # HTTP
        self.__http_queue = queue.Queue()
        self.__http_in_request = False
        self.__http_current_rqueue = None
        self.__http_current_request = None
        self.__http_fail_count = 0
        self.__http_fail_max = http_reinit

        # Init Commands
        self.modem_execute("AT+GSN")

        # Worker Thread
        self.__worker_working = True
        self.__mthread = None
        self.__start_worker()

    # Modem Base Functionality
    def __process_input(self):
        if self.__ser.in_waiting > 0:
            while self.__ser.in_waiting:
                newline = self.__ser.readline().decode('utf-8')
                logging.info("Modem: Received: " + newline)
                newline = newline.rstrip('\r').rstrip('\n').rstrip('\r')

                if "OK" in newline:
                    self.__write_lock = False
                    self.__last_health = time.time()
                elif "ERROR" in newline:
                    self.__write_lock = False
                elif "+CGNSPWR" in newline and "AT" not in newline:  # GNSS Power Notification
                    pwr = newline.split(':')[1]
                    self.__gnss_pwr = ('1' in pwr)
                    self.__write_lock = False
                    if self.__gnss_pwr:
                        logging.info("Modem: GNSS Active")
                    else:
                        logging.info("Modem: GNSS Inactive")
                elif newline.startswith("+UGNSINF"):  # GPS Update
                    data = newline.split(':')[1][1:]
                    self.__gnss_loc = GPSData(data)
                elif newline.startswith("+HTTPACTION"):  # HTTP Response
                    self.__write_lock = False
                    reply = newline.split()[1].split(',')
                    cid = int(reply[0])
                    http_status = int(reply[1])
                    data_size = int(reply[2])
                    assert isinstance(self.__http_current_rqueue, queue.Queue)
                    self.__http_current_rqueue.put({'cid': cid, 'http_status': http_status,
                                                    'data_size': data_size})
                    if data_size > 0 and http_status == 200:  # Fetch Data
                        logging.info("Modem: Loading HTTP Data")
                        self.__http_fetch_data()
                    else:
                        self.__http_in_request = False
                        self.__http_current_uuid = None
                        return
                elif newline.startswith("+HTTPREAD"): # HTTP Response Data
                    while True:
                        if self.__ser.in_waiting > 0:
                            dataline = self.__ser.readline().decode('utf-8')
                            logging.info("Modem: HTTP DATA: " + dataline)
                            self.__write_lock = False
                            self.__http_current_rqueue.put(dataline)
                            self.__http_in_request = False
                            return
                        time.sleep(0.1)
                elif self.__command_last == 'AT+GSN' and newline != 'AT+GSN' and self.__imei is None:
                    self.__imei = newline
                    self.__write_lock = False
                    return

    def __modem_write(self, cmd):
        if not self.__write_lock:
            self.__write_lock = True

            self.__ser.write((cmd + '\n').encode('utf-8'))
            logging.info("Modem: Writing: " + cmd)

            self.__command_last = cmd
            self.__command_last_time = time.time()
            return True
        return False

    def modem_execute(self, cmd) -> None:
        """
        Add command to queue to write to modem.
        :param cmd: AT (or other) command.
        """
        self.__command_queue.put(cmd)

    def __health_check(self):
        if time.time() - self.__last_health > 30 and time.time() - self.__command_last_time > 30:
            if self.__write_lock:  # If waiting for reply and waiting over 30 seconds
                self.power_toggle()
            elif not self.__write_lock and not self.__command_queue.empty():
                self.modem_execute("AT")

    def __reinit(self):
        self.__write_lock = False
        with self.__command_queue.mutex: # Clear Command Queue
            self.__command_queue.queue.clear()

        if self.__http_in_request: # Re-queue in-progress HTTP request
            self.__http_in_request = False
            self.__http_current_uuid = ""
            self.__http_queue.put(self.__http_current_request)
            self.__http_current_request = None

        # Disconnect and Reconnect Serial
        self.__ser.close()
        time.sleep(5)
        self.__ser = serial.Serial(self.__serial_port, baudrate=self.__serial_baudrate)

        time.sleep(5)

        if self.__network_active and self.__apn_config is not None: # Network
            self.__network_active = False
            self.network_start()

        if self.__gnss_active and self.__gnss_rate != 0: # GNSS
            self.gnss_start(rate=self.__gnss_rate)

        if self.__imei is None:
            self.modem_execute("AT+GSN")

    def connect(self):
        self.__ser = serial.Serial(self.__serial_port, baudrate=self.__serial_baudrate)
        self.__write_lock = False

    def disconnect(self):
        """
        Close serial connection to Modem.
        """
        self.__write_lock = True
        self.__ser.close()

    def power_toggle(self) -> None:
        """
        Toggle power of Modem
        """
        logging.critical("Sys: Toggling Modem Power")
        self.__last_health = time.time()
        self.__command_last_time = time.time()

        # Toggle Power
        GPIO.setmode(GPIO.BOARD)
        GPIO.setup(7, GPIO.OUT)
        while True:
            GPIO.output(7, GPIO.LOW)
            time.sleep(4)
            GPIO.output(7, GPIO.HIGH)
            break
        GPIO.cleanup()

        time.sleep(5)
        self.__reinit()

    def __main_thread(self):
        while self.__worker_working:
            self.__health_check()

            # Process any inputs
            self.__process_input()

            # If HTTP not in progress, execute next.
            if not self.__http_in_request and not self.__http_queue.empty():
                self.__http_execute_next()

            # Execute command if waiting
            if not self.__command_queue.empty() and not self.__write_lock:
                next_cmd = self.__command_queue.get()
                self.__modem_write(next_cmd)

            time.sleep(0.1)

    def __start_worker(self):
        self.__mthread = threading.Thread(target=self.__main_thread, daemon=True)
        self.__worker_working = True
        self.__mthread.start()

    def __stop_worker(self):
        self.__worker_working = False
        self.__mthread.join(20)

    # Networking
    def __bearer_setval(self, cid, param, val):
        self.modem_execute('AT+SAPBR=3,' + str(cid) + ',"' + param + '","' + val + '"')

    def __bearer_config(self, apn_config):
        self.__bearer_setval(1, "APN", apn_config['apn'])  # Set APN
        self.__bearer_setval(1, "USER", apn_config['username'])  # Set Username
        self.__bearer_setval(1, "PWD", apn_config['password'])  # Set Password

    def apn_config(self, apn, username, password) -> None:
        """
        Set modem APN, Username, and Password
        :param apn: Network APN
        :param username: Network Username
        :param password: Network Password
        """
        self.__apn_config = {'apn': apn, 'username': username, 'password': password}

    def __bearer_open(self):
        self.modem_execute("AT+SAPBR=1,1")

    def __data_open(self):
        self.modem_execute("AT+CMEE=1")
        self.modem_execute("AT+CGATT=1")
        self.modem_execute("AT+CGACT=1,1")
        self.modem_execute("AT+CGPADDR=1")

    def __network_init(self):
        self.__data_open()
        self.__bearer_config(self.__apn_config)
        self.__bearer_open()

    def network_start(self) -> None:
        """
        Start Network
        """
        self.__network_init()
        self.__network_active = True


    def network_stop(self) -> None:
        """
        Stop Network
        """
        self.__network_active = False
        self.modem_execute("AT+SAPBR=0,1")

    def __http_execute_next(self):
        if self.__http_in_request or self.__http_queue.empty():  # Stop if request already in progress or if no requests
            return

        self.__http_in_request = True
        req = self.__http_queue.get()
        self.__http_current_rqueue = req['rqueue']
        self.__http_current_request = req

        self.modem_execute("AT+HTTPTERM")
        self.modem_execute("AT+HTTPINIT")
        self.modem_execute('AT+HTTPPARA="URL","' + str(req['url']) + '"')
        self.modem_execute('AT+HTTPPARA="CID",1')
        self.modem_execute('AT+HTTPACTION=' + str(req['method']))

    def __http_fetch_data(self):
        """
        Fetches the data from the previous http request from the modem.
        :return: Dict containing response code, data size, and data.
        """
        self.modem_execute("AT+HTTPREAD")

    def __http_request(self, method, url):
        """
        Method to perform a http request.
        :param method: Integer representing HTTP request method. 0 - GET.
        :param url: URL to request.
        :return: Dict containing response code, data size, and data.
        """
        if self.__network_active is False and self.__apn_config is not None: # Start if not active
            self.network_start()

        if self.__http_fail_count >= self.__http_fail_max != 0: # Retry if too many fails
            logging.warning("Too many failed attempts. Restarting Network.")
            self.network_stop()
            self.network_start()

        rqueue = queue.Queue()
        self.__http_queue.put({'url': url, 'method': method, 'rqueue': rqueue})

        res = rqueue.get() # Wait for result

        # Check Result Code
        if res['http_status'] >= 600:
            self.__http_fail_count += 1

        if res['data_size'] > 0:
            data = rqueue.get() # Wait for data
            res['data'] = data

        return res


    def http_get(self, url) -> dict:
        """
        HTTP GET request
        :param url: URL to request
        :return: Dict containing response code, data size, and data.
        """
        return self.__http_request(0, url)

    def http_post(self, url) -> dict:
        """
        HTTP POST request
        :param url: URL to request
        :return: Dict containing response code, data size, and data.
        """
        return self.__http_request(1, url)


    def gnss_start(self, rate=1) -> None:
        """
        Start GNSS
        :param rate: Refresh rate from modem. (Hz, Max 1Hz)
        """
        self.__gnss_active = True
        self.__gnss_rate = rate
        self.modem_execute("AT+CGNSPWR=1")
        self.modem_execute("AT+CGNSURC=" + str(rate))

    def gnss_stop(self) -> None:
        """
        Stop GNSS
        """
        self.__gnss_active = False
        self.__gnss_rate = 0
        self.modem_execute("AT+CGNSPWR=0")

    def get_gnss_loc(self) -> GPSData:
        """
        Get GPSData from modem.
        :return: GPSData object containing gps data from modem.
        """
        return self.__gnss_loc

    def get_imei(self) -> str:
        """
        :return: Modem's IMEI
        """
        if self.__imei is None:
            self.__refresh_imei()
            while self.__imei is None:
                time.sleep(1)
        return self.__imei

    def __refresh_imei(self):
        self.__imei = None
        self.modem_execute("AT+GSN")
