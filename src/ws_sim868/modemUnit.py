#  Copyright (c) 2023-2024. Matthew Naruzny.

import threading
import time
import serial
import uuid
import logging

import RPi.GPIO as GPIO


class ModemUnit:
    def __init__(self, port='/dev/ttyS0', baudrate=115200, log=True):

        # Logging
        if log:
            logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

        # Serial Config
        self.__serial_port = port
        self.__serial_baudrate = baudrate

        # Serial
        self.__ser = serial.Serial(port, baudrate=baudrate)
        self.__write_lock = False
        self.__command_queue = []
        self.__command_last = ""
        self.__command_last_time = 0

        self.__last_health = 0

        # GPS
        self.__gnss_active = False
        self.__gnss_pwr = False
        self.__gnss_rate = 0 # 0 - Off
        self.__gnss_loc = {'gnss_run_status': 0, 'fix_status': 0}

        # Network
        self.__network_active = False
        self.__apn_config = None

        # HTTP
        self.__http_queue = []
        self.__http_result = {}
        self.__http_in_request = False
        self.__http_current_uuid = ""
        self.__http_current_request = None
        self.__http_request_cache = {}

        # Worker Thread
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
                    data = newline.split(':')[1][1:].split(',')
                    new_data = {'gnss_run_status': data[0], 'fix_status': data[1],
                                'time': data[2], 'lat': data[3], 'lon': data[4], 'alt': data[5], 'speed': data[6],
                                'course': data[7],'sat': data[14], 'sat_used': data[15]}
                    self.__gnss_loc = new_data
                elif newline.startswith("+HTTPACTION"):  # HTTP Response
                    self.__write_lock = False
                    reply = newline.split()[1].split(',')
                    cid = int(reply[0])
                    http_status = int(reply[1])
                    data_size = int(reply[2])
                    self.__http_result[self.__http_current_uuid] = {'cid': cid, 'http_status': http_status,
                                                                    'data_size': data_size, 'data': None}
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
                            http_result = self.__http_result[self.__http_current_uuid]
                            http_result['data'] = dataline
                            self.__http_result[self.__http_current_uuid] = http_result
                            return
                        time.sleep(0.1)

    def __modem_write(self, cmd):
        if not self.__write_lock:
            self.__write_lock = True

            self.__ser.write((cmd + '\n').encode('utf-8'))
            logging.info("Modem: Writing: " + cmd)

            self.__command_last = cmd
            self.__command_last_time = time.time()
            return True
        return False

    def modem_execute(self, cmd):
        self.__command_queue.append(cmd)

    def __health_check(self):
        if time.time() - self.__last_health > 30 and time.time() - self.__command_last_time > 30:
            if self.__write_lock:  # If waiting for reply and waiting over 30 seconds
                self.power_toggle()
            elif not self.__write_lock and len(self.__command_queue) == 0:
                self.modem_execute("AT")

    def __reinit(self):
        if self.__network_active and self.__apn_config is not None: # Network
            self.__network_active = False
            self.network_start()

        if self.__gnss_active and self.__gnss_rate != 0: # GNSS
            self.gnss_start(rate=self.__gnss_rate)


    def power_toggle(self):
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

        # Reset
        self.__write_lock = False
        self.__command_queue.clear()

        if self.__http_in_request:
            self.__http_in_request = False
            self.__http_current_uuid = ""
            self.__http_queue.append(self.__http_current_request)
            self.__http_current_request = None

        # Disconnect and Reconnect Serial
        self.__ser.close()
        time.sleep(5)
        self.__ser = serial.Serial(self.__serial_port, baudrate=self.__serial_baudrate)

        time.sleep(5)
        self.__reinit()

    def __main_thread(self):
        while self.__worker_working:
            self.__health_check()

            # Process any inputs
            self.__process_input()

            # If HTTP not in progress, execute next.
            if not self.__http_in_request and len(self.__http_queue) > 0:
                self.__http_execute_next()

            # Execute command if waiting
            if len(self.__command_queue) > 0 and not self.__write_lock:
                next_cmd = self.__command_queue.pop(0)
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

    def apn_config(self, apn, username, password):
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

    def network_start(self):
        self.__network_init()
        self.__network_active = True


    def network_stop(self):
        self.__network_active = False
        self.modem_execute("AT+SAPBR=0,1")

    def __http_execute_next(self):
        if self.__http_in_request or len(self.__http_queue) == 0:  # Stop if request already in progress or if no requests
            return

        self.__http_in_request = True
        req = self.__http_queue.pop(0)
        self.__http_current_uuid = req['uuid']
        self.__http_current_request = req
        self.__http_request_cache[req['uuid']] = req

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
        if self.__network_active is False and self.__apn_config is not None:
            self.network_start()
        new_uuid = uuid.uuid4()
        self.__http_result[new_uuid] = None
        self.__http_queue.append({'url': url, 'method': method, 'uuid': new_uuid})
        while True:  # Wait for Response
            if self.__http_result[new_uuid] is not None:
                if (self.__http_result[new_uuid]['data_size'] != 0 and self.__http_result[new_uuid]['data'] is not None) or self.__http_result[new_uuid]['data_size'] == 0:
                    res = self.__http_result[new_uuid]

                    # Clear Cache
                    self.__http_result.pop(new_uuid)
                    self.__http_request_cache.pop(new_uuid)

                    return res
            time.sleep(0.1)

    def http_get(self, url):
        """
        HTTP GET request
        :param url: URL to request
        :return: Dict containing response code, data size, and data.
        """
        return self.__http_request(0, url)

    def http_post(self, url):
        """
        HTTP POST request
        :param url: URL to request
        :return: Dict containing response code, data size, and data.
        """
        return self.__http_request(1, url)


    def gnss_start(self, rate=1):
        """
        Start GNSS
        :param rate: Refresh rate from modem. (Hz, Max 1Hz)
        """
        self.__gnss_active = True
        self.__gnss_rate = rate
        self.modem_execute("AT+CGNSPWR=1")
        self.modem_execute("AT+CGNSURC=" + str(rate))

    def gnss_stop(self):
        """
        Stop GNSS
        :return:
        """
        self.__gnss_active = False
        self.__gnss_rate = 0
        self.modem_execute("AT+CGNSPWR=0")

    def get_gnss_loc(self):
        """
        Get current GNSS data:
        {'gnss_run_status', 'fix_status', 'time', 'lat', 'lon', 'alt', 'speed', 'course','sat', 'sat_used'}
        :return: Dictionary containing current GNSS data
        """
        return self.__gnss_loc
