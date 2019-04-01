import os
import sys
from socket import *
import argparse
import hashlib


parser = argparse.ArgumentParser()
parser.add_argument("host", type = str)
parser.add_argument("port", type = int)
parser.add_argument("file", nargs = "?", type = str)
args = parser.parse_args()

TIMEOUT = 3       # seconds before timeout
MAX_CONNECTIONS = 1


class Packet:

    def __init__(self, seq_num, data_size, last, payload):
        self.seq_num = seq_num
        self.data_size = str(data_size).zfill(3)
        self.is_last = int(last)
        self.payload = self.build_payload(payload)
        self.checksum = self.create_checksum()

    def create_checksum(self):
        checksum = str(self.seq_num) + str(self.data_size) + str(self.is_last) + self.payload
        return hashlib.sha1(checksum.encode()).hexdigest()

    def get_checksum(self):
        return self.checksum

    def compare_checksum(self, checksum_val):
        return checksum_val == self.checksum

    def get_data(self):
        return self.payload

    def get_is_last(self):
        return self.is_last

    def build_stream(self):
        return self.checksum + str(self.seq_num) + self.data_size + str(self.is_last) + self.payload

    def build_payload(self,payload):
        padded_payload = "{payload:{char}<{cap}}".format(
            payload=payload,
            char="X",
            cap=467,
        )
        return padded_payload

    def get_seq_num(self):
        return self.seq_num

    def data_length(self):
        return int(self.data_size)


def server(host, port):

    try:
        server = socket(AF_INET, SOCK_STREAM)
    except Exception as msg:
        print('woops in server create')
        print(msg)
        sys.exit(1)

    try:
        #bind socket to host command line arg
        server.bind((host, port))
        #Listen on the given socket maximum number of connections queued is MAX_CONNECTIONS
        server.listen(MAX_CONNECTIONS)
    except Exception as msg:
        # Handle exception
        print(msg)
        sys.exit(1)

    print("Server is ready")

    connection_socket, addr = server.accept()
    (output_file, seq_num) = receive_basename(connection_socket)
    with open(output_file, 'w') as file:
        while 1:
            client_data = connection_socket.recv(512).decode()
            try:
                packet = Packet(int(client_data[40]), int(client_data[41:44]), bool(int(client_data[44])), client_data[45:])
            except:
                continue

            if packet.compare_checksum(client_data[:40]):  # not mangled
                if packet.get_seq_num() is seq_num:        # correct sequence number
                    file.write(packet.get_data()[:packet.data_length()])
                    file.flush()
                    response = Packet(packet.get_seq_num(), 0, packet.is_last, 'ACK')
                    connection_socket.sendall(response.build_stream().encode())
                    seq_num = (seq_num + 1) % 10
                else:                                      # already received packet
                    response = Packet(packet.get_seq_num(), 0, packet.is_last, 'ACK')
                    connection_socket.sendall(response.build_stream().encode())
            else:                                          # mangled packet received
                response = Packet(0, 0, True, 'NAK')
                connection_socket.sendall(response.build_stream().encode())
            if packet.get_is_last():
                break
    return


def receive_basename(connection_socket):
    seq_num = None
    received = False

    while not received:
        client_data = connection_socket.recv(512).decode()
        try:
            packet = Packet(int(client_data[40]), int(client_data[41:44]), bool(int(client_data[44])), client_data[45:])
        except:
            continue

        if packet.compare_checksum(client_data[:40]):  # not mangled
            if seq_num is None:
                seq_num = packet.get_seq_num()
            output_file = os.path.basename(packet.get_data()[:packet.data_length()])
            response = Packet(packet.get_seq_num(), 0, packet.is_last, 'ACK')
            connection_socket.sendall(response.build_stream().encode())
            seq_num = (seq_num + 1) % 10

            return output_file, seq_num


def client(host, inputfile, port):

    if inputfile is '':
        sys.exit("Expecting file pathname")

    try:
        cSock = socket(AF_INET, SOCK_STREAM)
    except error as msg:
        cSock = None  # Handle exception

    try:
        cSock.connect((host, port))
    except error as msg:
        cSock = None  # Handle exception

    if cSock is None:
        print("oops in client")
        print("Error: cannot open socket")
        return  # If the socket cannot be opened, quit the program.

    cSock.settimeout(TIMEOUT)

    with open(inputfile, 'r') as infile:
        send_basename(cSock)
        seq_num = 1
        is_last = False

        for piece in read_in_chunks(infile, 467):
            if is_last is True:
                break
            size = len(piece)
            if size is 0 or size < 467:
                is_last = True
            packet = Packet(seq_num, size, is_last, piece)
            sent = False
            while not sent:
                cSock.sendall(packet.build_stream().encode())
                try:
                    response = cSock.recv(512).decode()
                except timeout as msg:
                    print("lost packet")
                    continue
                try:
                    response_packet = Packet(int(response[40]), int(response[41:44]), response[44], response[45:])
                except:
                    continue
                if response_packet.compare_checksum(response[:40]):  # not mangled
                    if response_packet.get_seq_num() is seq_num:     # correct sequence number
                        if response_packet.get_data()[:3] == 'ACK':  # correct response
                            sent = True                              # update sent
                            seq_num = (seq_num + 1) % 10             # update seq number 0-9
        cSock.close()
        return


def read_in_chunks(file_object, chunk_size=1024):
    """function from stack overflow"""
    while True:
        data = file_object.read(chunk_size)
        if not data:
            break
        yield data


# send_first_packet sends the first packet that contains the file name.
# it also sends it and waits for a proper response
def send_basename(server_socket):
    size = len(args.file)
    packet = Packet(0, size, False, args.file)

    sent = False
    while not sent:
        server_socket.sendall(packet.build_stream().encode())
        try:
            response = server_socket.recv(512).decode()
        except timeout as msg:
            print("lost packet")
            continue

        try:
            response_packet = Packet(int(response[40]), int(response[41:44]), response[44], response[45:])
        except:
            continue
        if response_packet.compare_checksum(response[:40]):  # not mangled
            if response_packet.get_seq_num() is 0:               # correct sequence number
                if response_packet.get_data()[:3] == 'ACK':  # correct response
                    return


if __name__ == "__main__":
    if len(sys.argv) is 4:
        print('in client')
        client(args.host, args.file, args.port)
    elif len(sys.argv) is 3:
        print('in server')
        server(args.host, args.port)
    else:
        print("incorrect command line args")