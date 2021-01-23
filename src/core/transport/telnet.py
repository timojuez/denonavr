import time, socket, time, selectors
from telnetlib import Telnet
from threading import Lock, Thread, Event
from contextlib import suppress
from ..util.json_service import Service
from .abstract import AbstractProtocol, AbstractClient, AbstractServer


class TelnetClient(AbstractClient):
    """
    This class connects to the server via LAN and executes commands
    @host is the server's hostname or IP.
    """
    _pulse = "" # this is being sent regularly to keep connection
    _telnet = None
    _send_lock = None
    _pulse_stop = None
    
    def __init__(self, *args, **xargs):
        super().__init__(*args, **xargs)
        self._send_lock = Lock()
        self._pulse_stop = Event()

    def send(self, cmd):
        super().send(cmd)
        try:
            with self._send_lock:
                assert(self.connected and self._telnet.sock)
                self._telnet.write(("%s\r"%cmd).encode("ascii"))
                time.sleep(.01)
        except (OSError, EOFError, AssertionError, AttributeError) as e:
            self.on_disconnected()
            raise BrokenPipeError(e)
        
    def read(self, timeout=None):
        try:
            assert(self.connected and self._telnet.sock)
            return self._telnet.read_until(b"\r",timeout=timeout).strip().decode()
        except socket.timeout: return None
        except (OSError, EOFError, AssertionError, AttributeError) as e:
            self.on_disconnected()
            raise BrokenPipeError(e)
    
    def connect(self):
        super().connect()
        if self.connected: return
        try: self._telnet = Telnet(self.host,self.port,timeout=2)
        except (ConnectionError, socket.timeout, socket.gaierror, socket.herror, OSError) as e:
            raise ConnectionError(e)
        else: self.on_connect()

    def disconnect(self):
        super().disconnect()
        with suppress(AttributeError, OSError):
            self._telnet.sock.shutdown(socket.SHUT_WR) # break read()
            self._telnet.close()
    
    def on_connect(self):
        super().on_connect()
        def func():
            while not self._pulse_stop.wait(10): self.send(self._pulse)
        self._pulse_stop.clear()
        if self._pulse is not None: Thread(target=func, daemon=True, name="pulse").start()
        
    def on_disconnected(self):
        super().on_disconnected()
        self._pulse_stop.set()
        
    def mainloop_hook(self):
        super().mainloop_hook()
        if self.connected:
            try: data = self.read(5)
            except ConnectionError: pass
            else:
                if data: self.on_receive_raw_data(data)
        else:
            try: self.connect()
            except ConnectionError: return self._stoploop.wait(3)


class _TelnetServer(Service):
    EVENTS = selectors.EVENT_READ | selectors.EVENT_WRITE
    
    def __init__(self, amp, listen_host, listen_port, linebreak="\r"):
        self._send = {}
        self.amp = amp
        self._break = linebreak
        print("Starting telnet amplifier")
        print(f"Operating on {self.amp.prompt}")
        print()
        self.amp.bind(send = self.on_amp_send)
        super().__init__(host=listen_host, port=listen_port, verbose=1)
        with self.amp:
            Thread(target=self.mainloop, daemon=True, name="mainloop").start()
            while True:
                cmd = input()
                self.on_amp_send(cmd)
    
    def connection(self, conn, mask):
        if conn not in self._send: self._send[conn] = b""
        return super().connection(conn, mask)

    def read(self, data):
        for data in data.strip().decode().replace("\n","\r").split("\r"):
            print("%s $ %s"%(self.amp.prompt,data))
            try: self.amp.on_receive_raw_data(data)
            except Exception as e: print(traceback.format_exc())
        
    def write(self, conn):
        time.sleep(.05)
        if not self._send[conn]: return
        l = len(self._send[conn])
        try: conn.sendall(self._send[conn][:l])
        except OSError: pass
        self._send[conn] = self._send[conn][l:]
    
    def on_amp_send(self, data):
        print(data)
        encoded = ("%s%s"%(data,self._break)).encode("ascii")
        # send to all connected listeners
        for conn in self._send: self._send[conn] += encoded


class TelnetServer(AbstractServer):
    
    def __init__(self, *args, listen_host, listen_port, linebreak="\r", **xargs):
        super().__init__(*args, **xargs)
        _TelnetServer(self, listen_host, listen_port, linebreak)


class TelnetProtocol(AbstractProtocol):
    Server = TelnetServer
    Client = TelnetClient

