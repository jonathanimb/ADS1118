# ADS1118
A python interface to bit bang the ADS1118 chip from a Raspberry Pi. Single shot mode only for now. Optimized for my use: reading a temperature from a type K thermocouple.

The [ADS118](http://www.ti.com/lit/ds/symlink/ads1118.pdf) uses the SPI protocol. Since the SPI pins on my Raspberry Pi were occupied by the touch screen, this library uses normal GPIO pins instead (ie "bit bang"). 

Although the ADS1118 claims it can handle up to 5.5 V, when I tried it the output was mangled. Using 3.3 V power from the Pi fixed that. I assume it has to do with the 5 V TTL logic, so a voltage divider on DOUT may fix that.

You can use multiple ADS118 chips on the same CLK, DIN, and DOUT lines by using a CS line for each chip. If you only have one chip, ground the CS line.

Example use: read and print the temperature from a type K thermocouple connected to A2 and A3, once per second:

```python
import time
import ADS1118

# create the config registers
int_temp = ADS1118.encode(single_shot=True, temp_sensor=True, data_rate=5) # internal temperature
tc = ADS1118.encode(single_shot=True, multiplex=3, gain=7, data_rate=5) # thermocouple connected to A2/A3

ads = ADS1118.ADS1118(CLK = 17, MOSI = 18, MISO = 27)

while True:
    ref_temp, tc_voltage = ads.read(int_temp, tc) # read data
    temp = ADS1118.TC_linearize(ref_temp, tc_voltage) # convert to temperature
    print("temp is {:.2f}°C".format(temp)
    time.sleep(1)
```

Note the datasheet has config variables in binary. i.e. a data rate of 250 SPS is listed as "101", which is 5 in decimal. So you need to use `5` or specify binary with `0b101`. 

TODO: (help appreciated)
* add continuous mode
* add support for the built in SPI pins
