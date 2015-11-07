#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
#  wireless_socket_rx.py
#
#  Copyright 2015 IKARUS
#
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA 02110-1301, USA.
#
#


import argparse
from socket import socket, AF_INET, SOCK_DGRAM
from subprocess import Popen, call, DEVNULL
from time import sleep


# Config.
GRC_FILE_NAME   = './wireless_socket_rx_gr'
PACKET_SPACE    = 350 # Number of 0-samples between packages.
ONE_TIME        = 30  # Number of 1-samples to encode a logical 1-symbol.
ZERO_TIME       = 8   # Number of 1-samples to encode a logical 0-symbol.
ZERO_ERROR      = 4   # There must be at least X 0-symbols to decode
                      # them as such (to rule out error).
ONE_ERROR       = 4   # There must be at least X 1-symbols to decode
                      # them as such (to rule out error).

# Global vars.
zero_time = 0
one_time = 0
is_last_zero = True
packet = []


def decode_data(data, ignore_length=False, ignore_errors=False ):
  """
  Decode the data from the SDR and call print_packet() once a packet is fully
  received and decoded.
  """
  global zero_time, one_time, is_last_zero, packet
  for b in data:
    if b == 0:
      # Count the 0-samples.
      zero_time += 1
      # If the last samples were some 1-samples (and if there were enogh 0-samples to rule out
      # a mistake), check how many 1-samples there have been. If there were more than
      # ONE_TIME it is a 1. If there were only some 1-samples (more than ZERO_TIME) it must be a 0.
      if not is_last_zero and zero_time > ZERO_ERROR:
        # print('DEBUG: One time: {}'.format(one_time))
        if one_time >= ONE_TIME:
          packet.append('1')
        elif one_time >= ZERO_TIME:
          packet.append('0')
        else:
          packet.append('u')
        one_time = 0
        is_last_zero = True
    if b == 1:
      # Count 1-samples.
      one_time += 1
      # If the last samples were some 0-samples (and if there were enogh 1-samples to rule out
      # a mistake), check how many 0-samples there have been. If there were more than PACKET_SPACE
      # this must be the beginning of a new packet. Therefore, print the call print_packet()
      # on the peviousely decoded packet.
      if is_last_zero and one_time > ONE_ERROR:
        # print('DEBUG: Zero time: {}'.format(zero_time))
        if zero_time >= PACKET_SPACE:
          print_packet(''.join(packet), ignore_length, ignore_errors)
          packet = []
        zero_time = 0
        is_last_zero = False


def print_packet(packet, ignore_length=False, ignore_errors=False):
  """
  Decode the bits from a packet into human readable format and print it.
  """
  # Check the packet length.
  if len(packet) != 25:
    if ignore_length:
      print('[+] New Packet:')
      print('  Length: {}'.format(len(packet)))
      print('  Data: {}'.format(''.join(packet)))
      return
    else:
      # Length error. Packet not decodable.
      return

  output = []
  output.append('[+] New Packet:\n')

  # Decode address.
  output.append('  Address: ')
  for i in range(0, 10, 2):
    if packet[i] == '0' and packet[i+1] == '0':
      output.append('1')
    elif packet[i] == '0' and packet[i+1] == '1':
      output.append('0')
    else:
      if ignore_errors:
        output.append('e')
      else:
        return
  output.append('\n')

  # Decode identifier.
  identifier = packet[10:20]
  output.append('  Identifier: ')
  if identifier   == '0001010101':
    output.append('A\n')
  elif identifier == '0100010101':
    output.append('B\n')
  elif identifier == '0101000101':
    output.append('C\n')
  elif identifier == '0101010001':
    output.append('D\n')
  elif identifier == '0101010100':
    output.append('E\n')
  else:
    if ignore_errors:
      output.append('Error\n')
    else:
      return

  # Decode state.
  state = packet[20:24]
  output.append('  State: ')
  if state == '0100':
    output.append('OFF')
  elif state == '0001':
    output.append('ON')
  else:
    if ignore_errors:
      output.append('Error')
    else:
      return

  # Print the decoded packet (if no error occured).
  print(''.join(output))


def create_socket(ip='127.0.0.1', port=8000):
  """
  Create, bind and return a UDP socket.
  """
  s = socket(AF_INET, SOCK_DGRAM)
  s.bind((ip, port))
  return s


def launch_gr(ignore_output=True):
  """
  Launch the python script created from the GRC flowgraph.
  If the script does not exist, create it from the .grc file.
  """
  try:
    if ignore_output:
      sdr = Popen(GRC_FILE_NAME + '.py', stdout=DEVNULL, stderr=DEVNULL)
    else:
      sdr = Popen(GRC_FILE_NAME + '.py')
  except FileNotFoundError:
    # Create script from .grc file.
    print('[-] gnuradio script not found. Creating script from .grc file.')
    if ignore_output:
      call(['grcc', '-d', '.', GRC_FILE_NAME + '.grc'], stdout=DEVNULL, stderr=DEVNULL)
      sdr = Popen(GRC_FILE_NAME + '.py', stdout=DEVNULL, stderr=DEVNULL)
    else:
      call(['grcc', '-d', '.', GRC_FILE_NAME + '.grc'])
      sdr = Popen(GRC_FILE_NAME + '.py')
  return sdr


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument("-g", "--grcoutput", action="store_false",
                      help="Show the output of gnuradio/grcc.")
  parser.add_argument("-l", "--ignore-length", action="store_true",
                      help="Show packets even if the length is not 25 bits.")
  parser.add_argument("-e", "--ignore-errors", action="store_true",
                      help="Decode packets even if some bits make no sense.")
  args = parser.parse_args()

  # Boot up everything.
  print('[+] Create UDP server to receive gnuradio output (samples).')
  sock = create_socket()
  print('[+] Launch gnuradio script to feed the UDP server.')
  sdr = launch_gr(args.grcoutput)
  print('[+] Wait 1 second for gnuradio to boot up.')
  sleep(1)

  # Receive and decode the packets
  print('[+] Start decoding.')
  try:
    while True:
      data, addr = sock.recvfrom(1024)
      decode_data(data, args.ignore_length, args.ignore_errors)

  except KeyboardInterrupt:
    print('\n[+] Got keyboard interrupt.')

  finally:
    if sdr:
      print('[+] Terminate gnuradio.')
      sdr.terminate()
    print('[+] Close UDP server.')
    sock.close()

  print('[+] Exit.')
  return 0


if __name__ == '__main__':
  main()

