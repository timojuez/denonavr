# Freenon Network AVR Controlling Software
### Control your Denon AVR's power and master volume with your Ubuntu laptop or similar

## Requirements
- Denon/Marantz AVR compatible, connected via LAN/Wifi (tested with Denon X1400H)
- Python 3 and Pip
- Telnet

**For automatic freenon_setup:**
- Private nameserver on LAN
- nmap and net-tools

**For automatic power control:**
- SystemD
- Pulseaudio

**For mouse and keyboard volume key support**
- Xserver, macOS or Windows

**For the tray icon**
- GTK


## Install

### Ubuntu and other GNU OS
Install the requirements:
`sudo apt-get install python3-dev python3-pip nmap net-tools python3-gi`

Cloning this repository in the current directory and installing via pip:
`$ git clone https://github.com/timojuez/denonavr.git freenon && pip3 install --user wheel && pip3 install --user ./freenon/[autosetup,gnu_desktop] && rm -R ./freenon && freenon_setup --keys`

### Proprietary OS
On Mac/Windows, download and install nmap and Python3 with Pip and PyGObject.
Then execute:
`$ git clone https://github.com/timojuez/denonavr.git freenon && pip3 install --user wheel && pip3 install --user ./freenon/[autosetup,nongnu_desktop] && rm -R ./freenon && freenon_setup`

To connect the extra mouse buttons, start `freenon_mouse_binding`. You may want to add the command to autostart.

### Uninstall
To uninstall: `pip3 uninstall freenon`

Ggf remove the lines after ## FREENON in ~/.xbindkeysrc and restart xbindkeys.


### Configuration
See configuration options in ~/.freenon.cfg and src/denon/freenon.cfg.default.


## Usage

Note that this program is still in development and therefore try it with all sound output stopped.

### Gtk Tray Icon
This lets you control the volume by scrolling over a tray icon.
`freenon_gtk_tray_icon`
You may want to add the command to autostart.


### CLI and shortcuts
Plain commands can be sent to the AVR
`freenon_cmd [command]`

See the ./examples/*.sh.


## Development
It is possible to create a customised controller that keeps your own program synchronised with the AVR. Its dependency is freenon[gi] and optionally freenon[autosetup] and pulsectl.
See ./examples/custom_app.py

If your development only relies on sending commands to the AVR, you need the class freenon.denon.Denon. Your requirement is purely the freenon package and optionally freenon[autosetup].


## Limitations
- If you do not have a nameserver in your LAN or freenon_setup cannot find your Denon device, set the host IP manually in the config file.
- This program is currently only controlling the sound channels alltogether. Controlling e.g. left and right channel separately is to be implemented.
- If you are on a GNU OS and the key binding does not work, you can try the setup for proprietary OS.

