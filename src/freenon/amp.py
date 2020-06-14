import sys, time, socket
from threading import Lock, Thread, Timer
from telnetlib import Telnet
from .util.system_events import SystemEvents
from .config import config
from .config import FILE as CONFFILE
from .amp_features import Feature


def call_sequence(*functions):
    return lambda *args,**xargs: [f(*args,**xargs) for f in functions]

def log_call(func):
    """ object function decorator """
    def call(self,*args,**xargs):
        print("[%s] %s"%(self.__class__.__name__, func.__name__), file=sys.stderr)
        return func(self,*args,**xargs)
    return call


class BasicAmp(object):
    """
    This class connects to the amp via LAN and executes commands
    @host is the amp's hostname or IP.
    """
    protocol = "Undefined"

    def __init__(self, host=None, connect=True, verbose=False, **callbacks):
        super().__init__()
        self.verbose = verbose
        self.bind(**callbacks)
        self.host = host or config["Amp"].get("Host")
        if not self.host: raise RuntimeError("Host is not set! Install autosetup or set AVR "
            "IP or hostname in %s."%CONFFILE)
        self._received = []
        self.lock = Lock()
        self.connecting_lock = Lock()
        self.connected = False
        if connect: self.connect()

    def bind(self, **callbacks):
        """
        bind(event=function)
        Register callback on @event. Event can be any function in Amp
        """
        for name, callback in callbacks.items():
            setattr(self, name, call_sequence(getattr(self,name), callback))
        
    def _send(self, cmd):
        try:
            assert(self.connected)
            self._telnet.write(("%s\n"%cmd).encode("ascii"))
        except (OSError, EOFError, AssertionError, AttributeError) as e:
            self.on_disconnected()
            raise BrokenPipeError(e)
        
    def _read(self, timeout=None):
        try:
            assert(self.connected)
            return self._telnet.read_until(b"\r",timeout=timeout).strip().decode()
        except socket.timeout: return None
        except (OSError, EOFError, AssertionError, AttributeError) as e:
            self.on_disconnected()
            raise BrokenPipeError(e)
        
    def __call__(self, cmd, matches=None):
        """ send command to amp """
        if self.verbose: print("Freenon@%s:%s $ %s"%(self.host,self.protocol,cmd), file=sys.stderr)
        if not matches: return self._send(cmd)
        def _return(r):
            if self.verbose: print(r, file=sys.stderr)
            return r

        self.lock.acquire()
        try:
            pos_received = len(self._received)
            cmd = self._send(cmd)
            for i in range(25):
                pos_received_new = len(self._received)
                for r in self._received[pos_received:pos_received_new]:
                    if matches(r): 
                        self._received.remove(r)
                        return _return(r)
                pos_received = pos_received_new
                r = self._read(2)
                if not r:
                    if i>5: # timeout #TODO
                        sys.stderr.write("(timeout) ")
                        break
                    continue
                if matches(r): return _return(r)
                else: self._received.append(r)
            raise TimeoutError("WARNING: Got no answer for `%s`.\n"%cmd)
        finally: self.lock.release()

    def read(self):
        """ Wait until a message has been received from amp and return it """
        while True:
            self.lock.acquire()
            try:
                if self._received: return self._received.pop(0)
            finally: self.lock.release()
            r = self._read(5)
            if r: self._received.append(r)

    def connect(self, tries=1):
        """
        @tries int: -1 for infinite
        """
        self.connecting_lock.acquire() #blocking=False
        try:
            if self.connected: return
            while tries:
                if tries > 0: tries -= 1
                try: self._telnet = Telnet(self.host,23,timeout=2)
                except (ConnectionError, socket.timeout, socket.gaierror, socket.herror, OSError):
                    if tries == 0: raise
                else:
                    return self.on_connect()
                time.sleep(3)
        finally: self.connecting_lock.release()
    
    def connect_async(self):
        Thread(target=self.connect, args=(-1,), name="connecting", daemon=True).start()
        
    def disconnect(self):
        self.connected = False
        try: self._telnet.close()
        except AttributeError: pass
        
    @log_call
    def on_connect(self):
        """ Execute when connected e.g. after connection aborted """
        if self.verbose: print("[%s] connected to %s"%(self.__class__.__name__,self.host), file=sys.stderr)
        self.connected = True
        
    @log_call
    def on_disconnected(self):
        self.connected = False
        self.connect_async()

    def poweron(self,force=False):
        if not force and not config.getboolean("Amp","control_power_on") or self.power:
            return
        self.power = True
        time.sleep(3) #TODO
        if config.get("Amp","source"): self.source = config.get("Amp","source")

    def poweroff(self, force=False):
        if not force and (not config.getboolean("Amp","control_power_off") 
            or config.get("Amp","source") and self.source != config.get("Amp","source")): return
        self.power = False

    @log_call
    def on_change(self, attrib, new_val): pass
    @log_call
    def on_poweron(self): pass
    @log_call
    def on_poweroff(self): pass


class AsyncAmp(BasicAmp):

    def __init__(self, *args, **xargs):
        super().__init__(*args,connect=False,**xargs)
        
    def mainloop(self, blocking=True):
        if blocking: return self._mainloop()
        else: Thread(target=self._mainloop, name=self.__class__.__name__, daemon=True).start()

    def _mainloop(self):
        while True:
            try:
                cmd = self.read()
            except ConnectionError:
                self.connect(-1)
                continue
            else:
                # receiving
                consumed = []
                for attrib,f in self.features.items():
                    try: old, new = f.consume(cmd)
                    except ValueError: continue
                    else: consumed.append((attrib,old,new))
                if not consumed: self.on_change(None, cmd)
                for attrib,old,new in consumed:
                    if old != new: self.on_change(attrib,new)


class CommonAmpWithEvents(SystemEvents,AsyncAmp):
    """ Amp with system events listener """
    
    @log_call
    def on_shutdown(self, sig, frame):
        """ when shutting down computer """
        pass
        
    @log_call
    def on_suspend(self): pass
    
    @log_call
    def on_resume(self):
        """ Is being executed after resume computer from suspension """
        pass
        
    @log_call
    def on_start_playing(self):
        if hasattr(self,"_timer_poweroff"): self._timer_poweroff.cancel()

    @log_call
    def on_stop_playing(self):
        try: timeout = config.getfloat("Amp","poweroff_timeout")*60
        except ValueError: return
        if not timeout: return
        self._timer_poweroff = Timer(timeout,self.on_sound_idle)
        self._timer_poweroff.start()
    
    @log_call
    def on_sound_idle(self): pass
    

class AmpWithEvents(CommonAmpWithEvents):
    # TODO: move to other module?
    """ Amp implementing actions """
    
    def on_shutdown(self, sig, frame):
        """ when shutting down computer """
        super().on_shutdown(sig,frame)
        try: self.poweroff()
        except ConnectionError: pass
        self.disconnect()
        
    def on_suspend(self):
        super().on_suspend()
        try: self.poweroff()
        except ConnectionError: pass
        self.disconnect()
    
    def on_resume(self):
        super().on_resume()
        self.on_disconnected()

    def on_start_playing(self):
        super().on_start_playing()
        try: self.poweron()
        except ConnectionError: pass

    def on_sound_idle(self):
        super().on_sound_idle()
        try: self.poweroff()
        except ConnectionError: pass
    

def _make_amp_mixin(**features):
    """
    Make a class where all attributes are getters and setters for amp properties
    args: class_attribute_name=MyFeature
        where MyFeature inherits from Feature
    """
    
    class FeatureMixin(object):
        """ apply @features to Amp """

        def __init__(self,*args,**xargs):
            self.features = {k:v(self) for k,v in features.items()}
            super().__init__(*args,**xargs)
        
        def on_connect(self):
            for f in self.features.values(): f.unset()
            super().on_connect()
        
        def _set_feature_value(self, name, value):
            self.features[name].set(value)
        

    class SendOnceMixin(object):
        """ prevent the same values from being sent to the amp in a row """

        def __init__(self,*args,**xargs):
            self._block_on_set = {}
            super().__init__(*args,**xargs)
            
        def _set_feature_value(self, name, value):
            if name in self._block_on_set and self._block_on_set[name] == value:
                return
            self._block_on_set[name] = value
            super()._set_feature_value(name,value)
            
        def on_change(self,*args,**xargs):
            self._block_on_set.clear() # unblock values after amp switches on
            super().on_change(*args,**xargs)
        
        
    dict_ = dict()
    try: dict_["protocol"] = sys._getframe(3).f_globals['__name__']
    except: pass
    dict_.update({
        k:property(
            lambda self,k=k:self.features[k].get(),
            lambda self,val,k=k:self._set_feature_value(k,val)
        )
        for k,v in features.items()
    })
    cls = type("AmpFeatures", (SendOnceMixin,FeatureMixin), dict_)
    return cls


def _make_amp(features, base_cls=object):
    for name in features.keys(): 
        if hasattr(base_cls,name):
            raise KeyError("Key `%s` is ambiguous and may not be used as a feature."%name)
    return type("Amp", (_make_amp_mixin(**features),base_cls), dict())
    

def make_basic_amp(**features): return _make_amp(features, BasicAmp)
def make_amp(**features): return _make_amp(features, AmpWithEvents)

