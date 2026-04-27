import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Add parent dir to path to import src
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock paramiko BEFORE importing src modules
if 'paramiko' not in sys.modules:
    sys.modules['paramiko'] = MagicMock()

from src.ssh_comm import SSHCommunicator
from src.bbb_uart_comm import BBBConnection

class TestSSH(unittest.TestCase):
    @patch("paramiko.SSHClient")
    def test_connect_command(self, mock_client_cls):
        mock_client = mock_client_cls.return_value
        comm = SSHCommunicator("host", 22, "user", "pass")
        comm.connect()
        
        mock_client.connect.assert_called_with(hostname="host", port=22, username="user", password="pass", timeout=10)
        
        # Setup mock execution
        mock_stdout = MagicMock()
        mock_stdout.read.return_value = b"OK\n"
        mock_stderr = MagicMock()
        mock_stderr.read.return_value = b""
        
        mock_client.exec_command.return_value = (None, mock_stdout, mock_stderr)
        
        resp = comm.send_command("ls")
        self.assertEqual(resp, "OK")
        mock_client.exec_command.assert_called_with("ls")

class TestBBB(unittest.TestCase):
    @patch("paramiko.SSHClient")
    def test_connect_uart_setup(self, mock_client_cls):
        mock_client = mock_client_cls.return_value
        comm = BBBConnection("host", "user", "pass", "/dev/ttySn", 115200)
        
        # Mock setup command output
        mock_stdout_setup = MagicMock()
        mock_stdout_setup.channel.recv_exit_status.return_value = 0
        mock_client.exec_command.return_value = (None, mock_stdout_setup, MagicMock())
        
        comm.connect()
        # Verify stty command was called
        # The first call is stty
        args, _ = mock_client.exec_command.call_args_list[0]
        self.assertIn("stty", args[0])

    @patch("paramiko.SSHClient")
    def test_send_command_uart(self, mock_client_cls):
        mock_client = mock_client_cls.return_value
        comm = BBBConnection("host", "user", "pass", "/dev/ttySn", 9600)
        
        # Skip connect logic or mock it
        comm.client = mock_client
        
        # Mock read response
        mock_stdout = MagicMock()
        mock_stdout.read.return_value = b"UART_RESP\n"
        mock_client.exec_command.side_effect = [
            (None, MagicMock(), MagicMock()), # echo write
            (None, mock_stdout, MagicMock())  # read command
        ]
        
        resp = comm.send_command("HELLO")
        self.assertEqual(resp, "UART_RESP")

if __name__ == '__main__':
    unittest.main()
