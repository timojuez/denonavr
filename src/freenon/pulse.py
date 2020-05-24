import pulsectl, time, sys
from threading import Thread


class ConnectedPulse(pulsectl.Pulse):

    def __init__(self,*args,**xargs):
        super().__init__(*args,connect=False,**xargs)
        self.connect_pulse()

    def connect_pulse(self):
        def connect():
            self.connect()
            self.on_connected()
        def keep_reconnecting():
            while True:
                try: connect()
                except pulsectl.pulsectl.PulseError: time.sleep(3)
                else: break
        print("[%s] Connecting..."%self.__class__.__name__, file=sys.stderr)
        try: connect()
        except pulsectl.pulsectl.PulseError:
            Thread(target=keep_reconnecting,daemon=True).start()
    
    def on_connected(self):
        print("[%s] Connected to Pulseaudio."%self.__class__.__name__, file=sys.stderr)
    
    
class Pulse(ConnectedPulse):
    """ Listen for pulseaudio change events """
    
    def __init__(self, el):
        self.pulse_is_playing = False
        self.el = el
        self.pulse = self
        super().__init__("Freenon")

    def is_playing(self):
        return len(self.sink_input_list()) > 0
    
    def on_connected(self):
        # Pulseaudio connected
        super().on_connected()
        try: self.pulse_is_playing = self.pulse.is_playing()
        except pulsectl.pulsectl.PulseDisconnected: return self.connect_pulse() 
        Thread(target=self.loop, name=self.__class__.__name__, daemon=True).start()
        
    def loop(self):
        try:
            #self.pulse.event_mask_set('all')
            self.pulse.event_mask_set(pulsectl.PulseEventMaskEnum.sink,
                pulsectl.PulseEventMaskEnum.sink_input)
            self.pulse.event_callback_set(self._callback)
            while True:
                self.pulse.event_listen()
                if self.ev.facility == pulsectl.PulseEventFacilityEnum.sink:
                    self._on_pulse_sink_event()
                elif self.ev.facility == pulsectl.PulseEventFacilityEnum.sink_input:
                    self._on_pulse_sink_input_event()
        except KeyboardInterrupt: pass
        except pulsectl.pulsectl.PulseDisconnected: self.connect_pulse()
        
    def _callback(self, ev):
        self.ev = ev
        #print('Pulse event:', ev)
        raise pulsectl.PulseLoopStop

    def _on_pulse_sink_event(self):
        if self.ev.t == pulsectl.PulseEventTypeEnum.change:
            pass

    def _on_pulse_sink_input_event(self):
        self.pulse_is_playing = self.pulse.is_playing()
        if self.ev.t == pulsectl.PulseEventTypeEnum.new:
            self.el.on_start_playing()
        elif self.ev.t == pulsectl.PulseEventTypeEnum.remove and not self.pulse_is_playing:
            self.el.on_stop_playing()
