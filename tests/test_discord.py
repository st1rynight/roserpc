import json
import socket
import threading
import unittest

from roserpc.discord import HEADER, OP_FRAME, OP_PING, OP_PONG, DiscordClient, DiscordError


def read_frame(sock):
    op, length = HEADER.unpack(sock.recv(HEADER.size, socket.MSG_WAITALL))
    return op, json.loads(sock.recv(length, socket.MSG_WAITALL))


def write_frame(sock, op, payload):
    body = json.dumps(payload).encode()
    sock.sendall(HEADER.pack(op, len(body)) + body)


class DiscordClientTests(unittest.TestCase):
    def setUp(self):
        self.client_end, self.server_end = socket.socketpair()
        self.client = DiscordClient("123")
        self.client._sock = self.client_end

    def tearDown(self):
        self.client.close()
        self.server_end.close()

    def serve(self, respond):
        received = {}

        def run():
            received["op"], received["frame"] = read_frame(self.server_end)
            respond(received["frame"])

        thread = threading.Thread(target=run)
        thread.start()
        return thread, received

    def test_set_activity_sends_a_framed_command_and_waits_for_its_reply(self):
        def respond(frame):
            write_frame(self.server_end, OP_PING, {})
            write_frame(self.server_end, OP_FRAME, {"cmd": "SET_ACTIVITY", "nonce": "other"})
            write_frame(self.server_end, OP_FRAME, {"cmd": "SET_ACTIVITY", "nonce": frame["nonce"]})

        thread, received = self.serve(respond)
        self.client.set_activity({"details": "Playing"})
        thread.join()
        self.assertEqual(received["op"], OP_FRAME)
        self.assertEqual(received["frame"]["cmd"], "SET_ACTIVITY")
        self.assertEqual(received["frame"]["args"]["activity"], {"details": "Playing"})
        self.assertEqual(read_frame(self.server_end)[0], OP_PONG)

    def test_error_reply_raises_without_disconnecting(self):
        def respond(frame):
            error = {"evt": "ERROR", "nonce": frame["nonce"], "data": {"message": "bad activity"}}
            write_frame(self.server_end, OP_FRAME, error)

        thread, _ = self.serve(respond)
        with self.assertRaisesRegex(DiscordError, "bad activity"):
            self.client.set_activity({})
        thread.join()
        self.assertTrue(self.client.connected)


if __name__ == "__main__":
    unittest.main()
