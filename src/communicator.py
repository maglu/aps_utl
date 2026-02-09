from abc import ABC, abstractmethod

class Communicator(ABC):
    """
    Abstract Base Class for APS communications.
    """
    
    @abstractmethod
    def connect(self):
        """Establish the connection."""
        pass

    @abstractmethod
    def disconnect(self):
        """Close the connection."""
        pass

    @abstractmethod
    def send_command(self, cmd: str) -> str:
        """
        Send a command and return the response.
        
        Args:
            cmd (str): The command to send.
            
        Returns:
            str: The output from the command.
        """
        pass

    @abstractmethod
    def send_file(self, local_path: str, remote_path: str):
        """
        Send a file to the remote device.
        
        Args:
            local_path (str): Path to the file on the local machine.
            remote_path (str): Destination path on the remote device.
        """
        pass

    @abstractmethod
    def get_file(self, remote_path: str, local_path: str):
        """
        Retrieve a file from the remote device.
        
        Args:
            remote_path (str): Path to the file on the remote device.
            local_path (str): Destination path on the local machine.
        """
        pass

    @abstractmethod
    def start_interactive_shell(self):
        """Start an interactive shell session."""
        pass
