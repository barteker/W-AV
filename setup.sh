#!/bin/bash

# Exit on error
set -e

echo "Starting W-AV setup..."

# Update system
echo "Updating system packages..."
sudo apt-get update
sudo apt-get upgrade -y

# Install system dependencies
echo "Installing system dependencies..."
sudo apt-get install -y \
    python3-pip \
    python3-venv \
    nodejs \
    npm \
    x11-xserver-utils \
    openbox \
    firefox-esr \
    alsa-utils \
    python3-pyqt5 \
    python3-numpy \
    python3-scipy \
    libportaudio2 \
    portaudio19-dev \
    python3-pyaudio \
    git

# Install Node.js dependencies
echo "Installing Node.js dependencies..."
cd "$(dirname "$0")"
npm install

# Create and activate Python virtual environment
echo "Setting up Python virtual environment..."
python3 -m venv env
source env/bin/activate

# Install Python dependencies
echo "Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Additional Python packages needed for specific scripts
pip install \
    pyaudio \
    pyqtgraph \
    adafruit-blinka \
    adafruit-circuitpython-mcp3xxx \
    RPi.GPIO \
    requests

# Setup systemd services
echo "Setting up systemd services..."
sudo cp boot_files/power-switch.service /etc/systemd/system/
sudo cp boot_files/gpio-control.service /etc/systemd/system/
sudo cp boot_files/gpio-rotary-control.service /etc/systemd/system/

# Reload systemd and enable services
sudo systemctl daemon-reload
sudo systemctl enable power-switch.service
sudo systemctl enable gpio-control.service
sudo systemctl enable gpio-rotary-control.service

# Setup boot configuration
echo "Setting up boot configuration..."
if [ -f "/boot/config.txt" ]; then
    echo "Backing up existing config.txt..."
    sudo cp /boot/config.txt /boot/config.txt.backup
    echo "Copying W-AV config.txt..."
    sudo cp boot_files/config.txt /boot/config.txt
else
    echo "Warning: /boot/config.txt not found. Make sure boot partition is mounted."
fi

if [ -f "/boot/cmdline.txt" ]; then
    echo "Backing up existing cmdline.txt..."
    sudo cp /boot/cmdline.txt /boot/cmdline.txt.backup
    echo "Copying W-AV cmdline.txt..."
    sudo cp boot_files/cmdline.txt /boot/cmdline.txt
else
    echo "Warning: /boot/cmdline.txt not found. Make sure boot partition is mounted."
fi

# Setup .bash_profile
echo "Setting up .bash_profile..."
cat > ~/.bash_profile << EOL
[[ -z \$DISPLAY && \$XDG_VTNR -eq 1 ]] && startx /home/wave/W-AV/minimal-x-session.sh
EOL

# Make scripts executable
echo "Making scripts executable..."
chmod +x minimal-wav-start.sh
chmod +x minimal-x-session.sh

# Create necessary directories
echo "Creating necessary directories..."
mkdir -p .credentials
mkdir -p public

# Setup logging directories
echo "Setting up logging..."
sudo touch /var/log/w-av.log
sudo chown wave:wave /var/log/w-av.log

echo "Setup complete! Please reboot your system."
echo "After reboot, the W-AV system should start automatically." 