"""
Connects system events to the amp.
Main class AmpController
"""

from ..util.system_events import SystemEvents
from ..util import log_call
from ..amp.features import require
from ..common.config import config


class _Base(SystemEvents):

    def __init__(self, amp, *args, **xargs):
        self.verbose = xargs.get("verbose",0)
        self.amp = amp
        super().__init__(*args, **xargs)

    @require(config.power, config.source)
    def poweron(self):
        if config["Amp"].get("source"): self.features[config.source].set(config["Amp"]["source"], force=True)
        setattr(self, config.power, True)

    can_poweroff = property(
        lambda self: getattr(self,config.power)
        and (not config["Amp"].get("source") or getattr(self,config.source) == config["Amp"]["source"]))

    @require(config.power, config.source)
    def poweroff(self, force=False):
        if force or self.can_poweroff: setattr(self,config.power,False)


class SoundMixin(_Base):
    """ call amp.on_start_playing and amp.on_stop_playing when pulse decides """
    
    def __init__(self, *args, **xargs):
        super().__init__(*args, **xargs)
        self.amp.bind(on_connect=self.on_amp_connect)

    @log_call
    def on_start_playing(self): self.amp.on_start_playing()

    @log_call
    def on_stop_playing(self): self.amp.on_stop_playing()
    
    def on_amp_connect(self):
        if hasattr(self,"pulse") and self.pulse.connected and self.pulse.is_playing:
            self.on_start_playing()

    
class KeepConnected(_Base):
    """ keep amp connected whenever possible """

    @log_call
    def on_shutdown(self, sig, frame):
        """ when shutting down computer """
        self.amp.exit()
        self.exit()
        
    @log_call
    def on_suspend(self):
        super().on_suspend()
        self.amp.exit()

    @log_call
    def on_resume(self):
        """ Is being executed after resume computer from suspension """
        self.amp.enter()
        super().on_resume()


class AutoPower(_Base):
    """ implementing actions for automatic power management """
    
    def __init__(self, *args, **xargs):
        super().__init__(*args, **xargs)
        self.amp.preload_features.update((config.source, config.power))
        self.amp.bind(on_start_playing = self.poweron)
        self.amp.bind(on_idle = self.on_amp_idle)
    
    def on_amp_idle(self): self.amp.poweroff()

    def on_shutdown(self, sig, frame):
        """ when shutting down computer """
        self.poweroff()
        super().on_shutdown(sig,frame)
        
    def on_suspend(self):
        self.poweroff()
        super().on_suspend()


class AmpController(AutoPower, KeepConnected, SoundMixin, _Base):
    """
    Adds system events listener. Keep amp connected whenever possible
    Features: Auto power, auto reconnecting, 
    """
    pass
