from threading import Event, Lock

class AbstractFeature(object):
    call = None
    default_value = None #if no response
    
    def matches(self, cmd):
        """ return True if cmd shall be parsed with this class """
        raise NotImplementedError()
        
    def parse(self, cmd): # rename to decodeVal?
        """ transform string @cmd to native value """
        raise NotImplementedError()
        
    def send(self, value):
        """ send @value to amp """
        raise NotImplementedError()
    
    def on_change(self, old, new): pass


class Feature(AbstractFeature):
    """
    An attribute of the amplifier
    High level telnet protocol communication
    """

    def __init__(self, amp, name=None):
        self.amp = amp
        amp.features[name] = self
        self._value_set_event = Event()
        self._value_set_event.set()
        self._poll_lock = Lock()
        
    name = property(lambda self:self.__class__.__name__)

    def get(self):
        self._poll_lock.acquire()
        try:
            if not self.amp.connected: 
                raise ConnectionError("`%s` is not available when amp is disconnected."%self.__class__.__name__)
            try: return self._val
            except AttributeError:
                self.poll()
                return self._val
        finally: self._poll_lock.release()
        
    def set(self, value): self.send(value)

    def isset(self): return hasattr(self,'_val')
        
    def unset(self): self.__dict__.pop("_val",None)
    
    def async_poll(self): return self.amp.send(self.call)
    
    def poll(self):
        self._value_set_event.clear()
        self.async_poll()
        if not self._value_set_event.wait(timeout=2):
            if self.default_value: return self.store(self.default_value)
            else: raise ConnectionError("Timeout on waiting for answer for %s"%self.__class__.__name__)
        else: return self._val
    
    def resend(self): return self.send(self._val)
    
    def consume(self, cmd):
        """ parse and apply @cmd to this object """
        return self.store(self.parse(cmd))
        
    def store(self, value):
        old = getattr(self,'_val',None)
        self._val = value
        if not self._value_set_event.is_set():
            # call caused by poll(). Return False -> will not call amp.on_change
            self._value_set_event.set()
            return False
        if self._val != old: self.on_change(old, self._val)
        return old, self._val


class RawFeature(Feature): # TODO: move to protocol.raw_telnet
    
    def parse(self, cmd): return cmd
    def send(self, value): self.amp.send(value)
    def matches(self, cmd): return False
    

def make_feature(amp, cmd, matches=None):
    return type(cmd, (RawFeature,), dict(call=cmd, matches=lambda self,cmd:matches(cmd)))(amp)


