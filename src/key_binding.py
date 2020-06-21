# -*- coding: utf-8 -*-
import time, sys
from threading import Thread
from .util import json_service
from .amp import AmpEvents
from .config import config

ipc_port = config.getint("Service","ipc_port")


class VolumeChanger(AmpEvents):
    """ 
    Class for managing volume up/down while hot key pressed
    when both hot keys are being pressed, last one counts
    
    Example 1:
        button1=True
        button2=False
        press(button1)
        release(button1) #stops
    Example 2:
        press(button2)
        press(button1)
        release(button2) #skips
        release(button1) #stops
    """
    keys_pressed = 0

    def __init__(self, *args, **xargs):
        super().__init__(*args, **xargs)
        self.interval = config.getfloat("KeyEventHandling","interval")/1000
        self.step = config.getfloat("KeyEventHandling","step")
        self.button = None
        
    def press(self, button):
        """ start sending volume events to amp """
        self.keys_pressed += 1
        if self.keys_pressed <= 0: return
        self.button = button
        self.fire_volume()
    
    def on_connect(self): # amp connect
        super().on_connect()
        try: # preload values
            self.amp.volume
        except ConnectionError as e: print(repr(e), file=sys.stderr)
        
    def on_change(self, attr, value): # amp change
        super().on_change(attr, value)
        if attr != "volume" or self.keys_pressed <= 0: return
        if self.interval: time.sleep(self.interval)
        self.fire_volume()
        
    def fire_volume(self):
        for _ in range(100):
            if self.keys_pressed <= 0: return
            try: self.amp.volume += self.step*(int(self.button)*2-1)
            except ConnectionError: time.sleep(20)
            else: break

    def release(self, button):
        """ button released """
        self.keys_pressed -= 1
        if not (self.keys_pressed <= 0): self.button = not button
        self.fire_volume()
        Thread(target=self._poweron, name="poweron", daemon=False).start()
    
    def _poweron(self):
        try: self.amp.poweron(True)
        except ConnectionError: pass
        

def RemoteControlService(*args,**xargs):
    if ipc_port < 0: return
    secure_mode = config.getboolean("Service","secure_mode")
    if not secure_mode: print("[WARNING] Service not running in secure mode", file=sys.stderr)
    whitelist = ("press","release") if secure_mode else None
    return json_service.RemoteControlService(*args,port=ipc_port,func_whitelist=whitelist,**xargs)
    

send = lambda e: json_service.send(e, port=ipc_port)
    
