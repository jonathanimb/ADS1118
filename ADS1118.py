#!/usr/bin/env python
# -*- coding: utf-8 -*-
#

"""
A class to read data from the ADS1118 16-bit ADC chip.
Single shot mode only (for now)
Bit bang only (for now)
"""

import time

import RPi.GPIO as GPIO

class ConnectionError(Exception):
    pass

def int_to_list(data, bits=8):
    """converts an integer to a big-endian list of booleans
        >>> int_to_list(187)
        [1, 0, 1, 1, 1, 0, 1, 1]
    """
    return [data >> i & 1 for i in range(bits-1, -1, -1)]

def list_to_int(data):
    """converts a big-endian list of booleans to an integer
        >>> list_to_int([1, 0, 1, 1, 1, 0, 1, 1])
        187
    """
    return sum(val << i for i, val in enumerate(reversed(data)))

# the bytearray functions are not needed, but may be useful if anyone has commands
# in the more traditional 2-byte form.
def list_to_bytearray(data):
    return bytearray(list_to_int(data[i:i+8]) for i in range(0, len(data), 8))

def bytearray_to_list(data):
    data = bytearray(data)
    return sum(map(int_to_list, data), [])

def bytearray_to_int(data):
    return list_to_int(bytearray_to_list(data))

def int_to_bytearray(data):
    return list_to_bytearray(int_to_list(data))

gains = { # calculate the value of the least significant bit (LSB) by dividing the full range by the number of available bits
    0: 6.144 * 2 / 2**16, # 187.5 microvolts per bit at +- 6.144 volts full range
    1: 4.096 * 2 / 2**16, # 125.0
    2: 2.048 * 2 / 2**16, # 62.50 (default)
    3: 1.024 * 2 / 2**16, # 31.25
    4: 0.512 * 2 / 2**16, # 15.62
    5: 0.256 * 2 / 2**16, # 7.812
    6: 0.256 * 2 / 2**16, # 7.812
    7: 0.256 * 2 / 2**16  # 7.812
    }

sleep_times = { # calculate the time in seconds it takes for a single data point at each data rate
    0: 1. / 8,   # 125.0 ms per measurement = 8 measurements per second
    1: 1. / 16,  # 62.5
    2: 1. / 32,  # 31.3
    3: 1. / 64,  # 15.6
    4: 1. / 128, # 7.81 (default)
    5: 1. / 250, # 4.00
    6: 1. / 475, # 2.11
    7: 1. / 860  # 1.12
    }

def encode(
    single_shot = False, # If ADS is powered down, start a single measurement.
    multiplex = 0, # [0/1, 0/3, 1/3, 2/3, 0/gnd, 1/gnd, 2/gnd, 3/gnd]
    gain = 2, #[+/-6.144, 4.096, 2.048, 1.024, 0.512, .256] volts full range
    single_shot_mode = True, # power down after measurement
    data_rate = 4, # [8, 16, 32, 64, 128, 250, 475, 860] samples per second
    temp_sensor = False, # read the internal temperature
    pullup = True, # enable the DIN pullup resistor
    operation = True): # when false, config is not written to config register
    data = []
    data.append(int(single_shot))
    data.extend(int_to_list(multiplex, 3))
    data.extend(int_to_list(gain, 3))
    data.append(int(single_shot_mode))
    data.extend(int_to_list(data_rate, 3))
    data.append(int(temp_sensor))
    data.append(int(pullup))
    data.append(0) # reserved
    data.append(int(operation))
    data.append(1) # reserved
    return data

def decode(data):
    '''input a list of 16 bits'''
    return dict(
        single_shot = bool(data[0]),
        multiplex = list_to_int(data[1:4]),
        gain = list_to_int(data[4:7]),
        single_shot_mode = bool(data[7]),
        data_rate = list_to_int(data[8:11]),
        temp_sensor = bool(data[11]),
        pullup = bool(data[12]),
        operation = bool(data[13]))

def convert(data, lsb_size):
    '''convert a data block into a number
    :data: a list of bits
    :lsb_size: the value of the least significant bit'''
    if data[0]: #negative value, use binarys two's complement
        data = [not x for x in data]
        return -(lsb_size * (list_to_int(data) + 1))
    else:
        return lsb_size * list_to_int(data)

def interpret(config, data):
    '''convert the data block to a meaningful value.

    :config:
      the config that was sent or that was echoed (should be the same)
      this is used to determine how the data should be interpreted
    :data:
      the data block from the ADS1118 as a length 16 list of booleans
    '''
    if config[11]: # temp measurement
        # convert a data block into a temperature, returns degrees C
        return convert(data[:14], 0.03125)
    else: # voltage measurement
        # convert a data block into a voltage
        gain = list_to_int(config[4:7])
        return convert(data, gains[gain])

def verify(command, config):
    '''
    compares the command sent to the echoed config returned from the ADS1118.
    If they don't match then there was a communications problem.

    if the sum of bits is zero than the ADS1118 is likely not connected
    if the sum is non-zero then you probably have more than one instance running
    '''
    if config[1:15] != command[1:15]:
        raise ConnectionError('sum of bits: {}'.format(sum(config)))

def pause(command):
    '''wait for the amount of time the command takes to execute'''
    time.sleep(sleep_times[list_to_int(command[8:11])])

INT_TEMP = encode(single_shot=True, temp_sensor=True, data_rate=5) # read internal temperature
class ADS1118(object):
    '''although the 1118 says it can handle a 5V input voltage, it's a lie.
    At least when running from a Pi, the 1118 must be powered from the 3.3 V line
    Perhaps you can use more power if you add a voltage divider to the DOUT line'''
    def __init__(self, SCLK=None, DIN=None, DOUT=None, CS=None, pause_mode=True):
        '''
        :SCLK:, :DIN:, :DOUT:, :CS:
          the GPIO pin numbers that connect to the pins of the same name on the ADS1118 chip
        :pause_mode:
          After sending a command, the computer must wait for the command to be processed
          and the data to be ready to read. How long this takes is set by the data_rate argument.
          When the data is ready, the ADS1118 sets the DOUT pin low.

          the pause_mode argument sets how the computer waits for the data to be ready

          if pause_mode is True, the computer calculates the time it should take and sleeps that long
          this does not take into account the time needed to communicate, so it will always sleep
          slightly longer than needed, generally about 0.25 ms longer

          if pause_mode is False, the computer will continuously poll the DOUT pin
          and collect the data as soon as it's ready. This locks up a CPU and can
          slow down other tasks the computer has running.
        '''
        self.SCLK = SCLK
        self.DIN = DIN
        self.DOUT = DOUT
        self.CS = CS
        self.pause_mode = pause_mode

        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.SCLK, GPIO.OUT)
        GPIO.setup(self.DIN, GPIO.OUT)
        GPIO.setup(self.DOUT, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
        if self.CS is not None:
            GPIO.setup(self.CS, GPIO.OUT)
            GPIO.output(self.CS, GPIO.HIGH)
        GPIO.output(self.SCLK, GPIO.LOW)
        GPIO.output(self.DIN, GPIO.LOW)

        time.sleep(.030) # something sets high, and the ADS1118 needs to have the clock held low for 28 ms to reset (datasheet page 22, section 9.5.3)
        config, data = self._read(INT_TEMP) # clear the cobwebs
        verify(INT_TEMP, config)
        pause(INT_TEMP) # using wait here will sometimes hang

    def wait(self):
        '''wait until DOUT is low, signaling that the next data is ready'''
        while GPIO.input(self.DOUT):
            pass

        # another method to accomplish the same
        # this method is slower than above, and slower than the pause function
        # in addition it has the tendancy to corrupt data
        # I left this in here to prove I've tested it
        #~ if GPIO.input(self.DOUT):
            #~ GPIO.wait_for_edge(self.DOUT, GPIO.FALLING, timeout=40)

    def _read(self, command):
        '''
        read / write a single 32-bit cycle

        :command: a list of 16 booleans
        :wait: wait for DOUT to be low (ADS signal data is ready)
         waiting is the 'proper' way to minimize the time, but it ties up a CPU
         pausing does not use the CPU and is generally about 1 ms slower

        returns
          :config: the current command echoed back from the ADS1118
          :data: the result from the _PREVIOUS_ call'''

        #~ assert isinstance(command, (tuple, list)), "command must be a list"
        #~ assert len(command) >= 16 and len(command) % 16 == 0, "command must have a multiple of 16 elements"
        #~ assert all(x in (0,1) for x in command), "command must be a list of booleans"

        if self.CS:
            GPIO.output(self.CS, GPIO.LOW)

        data_out = []
        for bit in command*2:
            GPIO.output(self.SCLK, GPIO.HIGH)
            GPIO.output(self.DIN, int(bit))
            data_out.append(GPIO.input(self.DOUT))
            GPIO.output(self.SCLK, GPIO.LOW)

        if self.CS:
            GPIO.output(self.CS, GPIO.HIGH)

        # the data should be 32 bits long, split in half to output data, config
        # index from the back to allow commands longer than 16 bits.
        data = data_out[-32:-16]
        config = data_out[-16:]
        return config, data

    def read(self, *commands):
        '''
        make some single shot measurements

        this method makes the vital assumption that you allow enough time
        between calls that the ADS is powered down (7 ms in default mode).
        if that might not be, add
          pause(INT_TEMP)
        to your routine.'''
        responses = []
        for command in commands:
            responses.append(self._read(command))
            if self.pause_mode:
                pause(command)
            else:
                self.wait()
        responses.append(self._read(INT_TEMP)) # dummy command to get the last data value

        configs, datas = zip(*responses)
        results = []
        for command, config, data in zip(commands, configs, datas[1:]): # skip the first data since it's residual
            results.append(interpret(config, data))
            verify(command, config)
        return results
