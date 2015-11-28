#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
#  wireless_socket_tx.py
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
from subprocess import Popen, call, DEVNULL
from time import sleep
from os import mkfifo, remove


# Config.
GRC_FILE_NAME   = './wireless_socket_tx_gr'
FIFO_FILE       = './packets-fifo.bin'


def generate_packet(address, identifier, state, repeat=3):
  """
  Generate and encode a packet based on the address, identifiier and state.
  Uses encode_packet() to encode the packet.
  """
  packet = []

  # Generate address part of the packet (bit 0 to 9).
  for c in address:
    if c == '1':
      packet.append('00')
    else:
      packet.append('01')

  # Generate identifier part of the packet (bit 10 to 19).
  identifier = identifier.upper()
  if   identifier == 'A':
    packet.append('0001010101')
  elif identifier == 'B':
    packet.append('0100010101')
  elif identifier == 'C':
    packet.append('0101000101')
  elif identifier == 'D':
    packet.append('0101010001')
  elif identifier == 'E':
    packet.append('0101010100')

  # Generate state of the packet (bit 20 to 24).
  state = state.upper()
  if state == 'ON':
    packet.append('00010')
  else:
    packet.append('01000')

  # Return encoded (and repeated) packet.
  return encode_packet(''.join(packet), repeat)


def encode_packet(packet, repeat=3):
  """
  Encode packet. '0' -> 0x01000000, '1' -> 0x01010100.
  Also, 24 times of 0x00 are appended (as spacing between packets).
  """
  encoded_packet = []
  for c in packet:
    if c == '1':
      encoded_packet.extend([0x01, 0x01, 0x01, 0x00])
    else:
      encoded_packet.extend([0x01, 0x00, 0x00, 0x00])

  encoded_packet.extend([0x00] * 24)
  encoded_packet.extend(encoded_packet * repeat)
  return bytes(encoded_packet)


def packet_to_fifo(packet, file_name=FIFO_FILE):
  """
  Save packet to the FIFO file. The FIFO file will be read by the
  gnuradio script.
  """
  with open(file_name, 'wb') as output:
    output.write(packet)


def make_fifo(file_name=FIFO_FILE):
  """
  Create FIFO file to communicate with gnuradio.
  """
  try:
    mkfifo(FIFO_FILE)
  except FileExistsError:
    pass


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
  """
  Parse arguments, boot everything up, create packages, send them
  and shut down everything.
  """
  parser = argparse.ArgumentParser()
  parser.add_argument("-g", "--grcoutput", action="store_false",
                      help="Show the output of gnuradio/grcc.")
  parser.add_argument("-r", "--repeat", type=int, default=3,
                      help="Repeat every packet REPEAT times. Default is 3.")
  parser.add_argument("-a", "--address", type=str, required=True,
                      help="Address string of sockets, e.g. 00101 or ALL.")
  parser.add_argument("-i", "--identifier", type=str, required=True,
                      help="Socket identifier. A, B, C, D, E or ALL.")
  parser.add_argument("-s", "--state", type=str, required=True,
                      help="Switch the power 'on' or 'off'.")
  args = parser.parse_args()

  # TODO: Check params (e.g. repeat >= 0).

  # Boot up everything.
  print('[+] Create FIFO file to communicate with gnuradio.')
  make_fifo()
  print('[+] Launch gnuradio script to send packages from the FIFO file.')
  sdr = launch_gr(args.grcoutput)
  print('[+] Wait 1 second for gnuradio to boot up.')
  sleep(1)
  print('[+] Every packet will be repeated {} times.'.format(args.repeat))

  # Create the packages.
  packages = []
  # Brute-force the address?
  if args.address.upper() == 'ALL':
    # Loop through all addresses.
    for i in range(0, 32):
      addr = '{:05b}'.format(i)
      # Brute-force also the identifier?
      if args.identifier.upper() == 'ALL':
        # Loop through all identifiers.
        for j in range(0, 5):
          identifier = chr(j + 65) # A, B, ..., E.
          packages.append(generate_packet(addr, identifier, args.state, args.repeat))
      else:
        packages.append(generate_packet(addr, args.identifier, args.state, args.repeat))
  # Brute-force the identifier?
  elif args.identifier.upper() == 'ALL':
    # Loop through all identifiers.
    for j in range(0, 5):
      identifier = chr(j + 65)
      packages.append(generate_packet(args.address, identifier, args.state, args.repeat))
  else:
    packages.append(generate_packet(args.address, args.identifier, args.state, args.repeat))
    print('[+] Added packet to send queue: addr={}, id={}, state={}.'.format(
      args.address, args.identifier, args.state))

  # Send the packages.
  try:
    # Each symbol takes 0.0003s. A packet has 100 syombols and 24 0-symbols of spacing.
    # Each packet will be repeated args.repeat times.
    send_time = round((((25 * 4) + 24) * 0.0003) * (args.repeat + 1) * len(packages), 3)
    print('[+] Sending packets... This will take about {} seconds.'.format(send_time))
    for packet in packages:
      packet_to_fifo(packet)
    sleep(send_time)

  except KeyboardInterrupt:
    print('\n[+] Got keyboard interrupt.')

  finally:
    if sdr:
      print('[+] Wait 1 second before terminating gnuradio.')
      sleep(1)
      print('[+] Terminate gnuradio.')
      sdr.terminate()
    print('[+] Remove FIFO file.')
    remove(FIFO_FILE)

  print('[+] Exit.')
  return 0


if __name__ == '__main__':
  main()

