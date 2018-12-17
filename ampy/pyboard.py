#!/usr/bin/env python

"""
pyboard interface

This module provides the Pyboard class, used to communicate with and
control the pyboard over a serial USB connection.

Example usage:

    import pyboard
    pyb = pyboard.Pyboard('/dev/ttyACM0')

Or:

    pyb = pyboard.Pyboard('192.168.1.1')

Then:

    pyb.enter_raw_repl(
    pyb.exec('pyb.LED(1).on()')
    pyb.exit_raw_repl()

Note: if using Python2 then pyb.exec must be written as pyb.exec_.
To run a script from the local machine on the board and print out the results:

    import pyboard
    pyboard.execfile('test.py', device='/dev/ttyACM0')

This script can also be run directly.  To execute a local script, use:

    ./pyboard.py test.py

Or:

    python pyboard.py test.py

"""

import sys
import time

_rawdelay = None

try:
    stdout = sys.stdout.buffer
except AttributeError:
    # Python2 doesn't have buffer attr
    stdout = sys.stdout

def stdout_write_bytes(b):
    b = b.replace(b"\x04", b"")
    stdout.write(b)
    stdout.flush()

class PyboardError(BaseException):
    pass

class TelnetToSerial:
    def __init__(self, ip, user, password, read_timeout=None):
        import telnetlib
        self.tn = telnetlib.Telnet(ip, timeout=15)
        self.read_timeout = read_timeout
        if b'Login as:' in self.tn.read_until(b'Login as:', timeout=read_timeout):
            self.tn.write(bytes(user, 'ascii') + b"\r\n")

            if b'Password:' in self.tn.read_until(b'Password:', timeout=read_timeout):
                # needed because of internal implementation details of the telnet server
                time.sleep(0.2)
                self.tn.write(bytes(password, 'ascii') + b"\r\n")

                if b'for more information.' in self.tn.read_until(b'Type "help()" for more information.', timeout=read_timeout):
                    # login succesful
                    from collections import deque
                    self.fifo = deque()
                    return

        raise PyboardError('Failed to establish a telnet connection with the board')

    def __del__(self):
        self.close()

    def close(self):
        try:
            self.tn.close()
        except:
            # the telnet object might not exist yet, so ignore this one
            pass

    def read(self, size=1):
        while len(self.fifo) < size:
            timeout_count = 0
            data = self.tn.read_eager()
            if len(data):
                self.fifo.extend(data)
                timeout_count = 0
            else:
                time.sleep(0.25)
                if self.read_timeout is not None and timeout_count > 4 * self.read_timeout:
                    break
                timeout_count += 1

        data = b''
        while len(data) < size and len(self.fifo) > 0:
            data += bytes([self.fifo.popleft()])
        return data

    def write(self, data):
        self.tn.write(data)
        return len(data)

    def inWaiting(self):
        n_waiting = len(self.fifo)
        if not n_waiting:
            data = self.tn.read_eager()
            self.fifo.extend(data)
            return len(data)
        else:
            return n_waiting

class Pyboard:
    def __init__(self, device, baudrate=115200, user='micro', password='python', wait=0, rawdelay=0):
        global _rawdelay
        _rawdelay = rawdelay
        if device and device[0].isdigit() and device[-1].isdigit() and device.count('.') == 3:
            # device looks like an IP address
            self.serial = TelnetToSerial(device, user, password, read_timeout=10)
        else:
            import serial
            try:
                self.serial = serial.serial_for_url(device,do_not_open=True)
                self.serial.baudrate=115200
                self.serial.timeout = 1  #Read timeout
                self.serial.write_timeout = 1
                self.serial.inter_byte_timeout = None
                self.serial.rts=0
                self.serial.dtr=0
                self.serial.inter_byte_timeout=1
                self.open()
            except ValueError:
                print("Serial Parameters out of range")
            except serial.SerialException:
                print("Serial device could not be found or configured")

    def open(self):
        try:
            self.serial.open()
        except self.serial.SerialException:
            print("Serial port could not be opened")

    def close(self):
        self.serial.close()


    def read_until(self, min_num_bytes, ending, timeout=10, data_consumer=None):
        data = self.serial.read_until(ending)
        if data_consumer:
            data_consumer(data)
        return data

    def enter_raw_repl(self):
        # Brief delay before sending RAW MODE char if requests
        if _rawdelay > 0:
            time.sleep(_rawdelay)

        self.serial.write(b'\r\x03\x03') # ctrl-C twice: interrupt any running program

        self.serial.flushInput()

        self.serial.write(b'\r\x01') # ctrl-A: enter raw REPL
        data = self.read_until(1, b'raw REPL; CTRL-B to exit\r\n')
        if not data.endswith(b'raw REPL; CTRL-B to exit\r\n'):
            raise PyboardError('could not enter raw repl')
        if not self.isPrompt:
           raise PyboardError('could not enter raw repl')
        self.serial.flushInput()
        

    def exit_raw_repl(self):
        self.serial.write(b'\r\x02') # ctrl-B: enter friendly REPL

    def follow(self, timeout, data_consumer=None):
        # wait for normal output
        data = self.read_until(1, b'\x04', timeout=timeout, data_consumer=data_consumer)

        if not data.endswith(b'\x04'):
            raise PyboardError('timeout waiting for first EOF reception')
        data = data[:-1]

        # wait for error output
        data_err = self.read_until(1, b'\x04', timeout=timeout)
        if not data_err.endswith(b'\x04'):
            raise PyboardError('timeout waiting for second EOF reception')
        data_err = data_err[:-1]

        self.serial.flushInput()

        # return normal and error output
        return data, data_err

    def exec_raw_no_follow(self, command):
        if isinstance(command, bytes):
            command_bytes = command
        else:
            command_bytes = bytes(command, encoding='utf8')

        # check we have a prompt
       

        # write command
        for i in range(0, len(command_bytes), 256):
            self.serial.write(command_bytes[i:min(i + 256, len(command_bytes))])
            time.sleep(0.01)
        self.serial.write(b'\x04')

        # check if we could exec command
        data = self.serial.read(2)
        if data != b'OK':
            raise PyboardError('could not exec command')

    def exec_raw(self, command, timeout=10, data_consumer=None):
        self.exec_raw_no_follow(command)
        output = self.follow(timeout, data_consumer)
        return output

    def eval(self, expression):
        ret = self.exec_('print({})'.format(expression))
        ret = ret.strip()
        return ret

    def exec_(self, command):
        ret, ret_err = self.exec_raw(command)
        if ret_err:
            raise PyboardError('exception', ret, ret_err)
        return ret

    def execfile(self, filename):
        with open(filename, 'rb') as f:
            pyfile = f.read()
        return self.exec_(pyfile)

    def get_time(self):
        t = str(self.eval('pyb.RTC().datetime()'), encoding='utf8')[1:-1].split(', ')
        return int(t[4]) * 3600 + int(t[5]) * 60 + int(t[6])
    
    def isPrompt(self):
        data = self.serial.read_all()
        if data == b'>':
            return True
        else:
            return False

# in Python2 exec is a keyword so one must use "exec_"
# but for Python3 we want to provide the nicer version "exec"
setattr(Pyboard, "exec", Pyboard.exec_)

def execfile(filename, device='/dev/ttyUSB0', baudrate=115200, user='micro', password='python'):
    pyb = Pyboard(device, baudrate, user, password)
    pyb.enter_raw_repl()
    output = pyb.execfile(filename)
    stdout_write_bytes(output)
    pyb.exit_raw_repl()
    pyb.close()

def main():
    import argparse,time
    cmd_parser = argparse.ArgumentParser(description='Run scripts on the pyboard.')
    cmd_parser.add_argument('--device', default='/dev/ttyACM0', help='the serial device or the IP address of the pyboard')
    cmd_parser.add_argument('-b', '--baudrate', default=115200, help='the baud rate of the serial device')
    cmd_parser.add_argument('-u', '--user', default='micro', help='the telnet login username')
    cmd_parser.add_argument('-p', '--password', default='python', help='the telnet login password')
    cmd_parser.add_argument('-c', '--command', help='program passed in as string')
    cmd_parser.add_argument('-w', '--wait', default=0, type=int, help='seconds to wait for USB connected board to become available')
    cmd_parser.add_argument('--follow', action='store_true', help='follow the output after running the scripts [default if no scripts given]')
    cmd_parser.add_argument('files', nargs='*', help='input files')
    args = cmd_parser.parse_args()

    def execbuffer(buf):
        try:
            pyb = Pyboard(args.device, args.baudrate, args.user, args.password, args.wait)
            time.sleep(1)
            pyb.enter_raw_repl()
            if args.follow:
                data_consumer = stdout_write_bytes
            else:
                data_consumer=None
            ret, ret_err = pyb.exec_raw(buf, timeout=None, data_consumer=data_consumer)
            pyb.exit_raw_repl()
            pyb.close()
        except PyboardError as er:
            print(er)
            sys.exit(1)
        except KeyboardInterrupt:
            sys.exit(1)
        if ret_err:
            stdout_write_bytes(ret_err)
            sys.exit(1)

    if args.command is not None:
        execbuffer(args.command.encode('utf-8'))

    for filename in args.files:
        with open(filename, 'rb') as f:
            pyfile = f.read()
            execbuffer(pyfile)

    #if args.follow or (args.command is None and len(args.files) == 0):
    #    try:
    #        pyb = Pyboard(args.device, args.baudrate, args.user, args.password, args.wait)
    #        ret, ret_err = pyb.follow(timeout=None, data_consumer=stdout_write_bytes)
    #        pyb.close()
    #    except PyboardError as er:
    #        print(er)
    #        sys.exit(1)
    #    except KeyboardInterrupt:
    #        sys.exit(1)
    ##    if ret_err:
    #        stdout_write_bytes(ret_err)
    #        sys.exit(1)

if __name__ == "__main__":
    main()
