# W-AV
W-AV is a custom music player system designed for Raspberry Pi, featuring a web-based interface for Spotify integration and hardware controls. The system combines software and hardware components to create an immersive music playback experience.

## Features
- Web-based Spotify integration
- Hardware volume control and playback buttons
- Rotary encoder for navigation
- Oscilloscope visualization
- Power management system
- Automatic startup and display configuration

## Project Website
Visit [wavmusicplayer.com](https://wavmusicplayer.com) for more information about the project.

## Documentation
All of the code for the W/AV project including setup files located in the boot_files folder. Requires node to run

## Setup Instructions

### 1. System Dependencies
Run the setup script to install all required dependencies:
```bash
chmod +x setup.sh
./setup.sh
```

### 2. Boot Configuration (Manual Setup)
The following boot configuration files need to be manually copied to the boot partition:

1. Mount the boot partition if not already mounted:
```bash
sudo mount /dev/mmcblk0p1 /boot/firmware
```

2. Backup existing configuration files:
```bash
sudo cp /boot/firmware/config.txt /boot/firmware/config.txt.backup
sudo cp /boot/firmware/cmdline.txt /boot/firmware/cmdline.txt.backup
```

3. Copy W-AV configuration files:
```bash
sudo cp boot_files/config.txt /boot/firmware/config.txt
sudo cp boot_files/cmdline.txt /boot/firmware/cmdline.txt
```

4. Reboot the system:
```bash
sudo reboot
```

### 3. Post-Installation
After installation and reboot:
- The system will automatically start the X server
- W-AV services will start automatically
- The web interface will be available at http://127.0.0.1:8888

### 4. Troubleshooting
If you need to restore the original boot configuration:
```bash
sudo cp /boot/firmware/config.txt.backup /boot/firmware/config.txt
sudo cp /boot/firmware/cmdline.txt.backup /boot/firmware/cmdline.txt
sudo reboot
```
