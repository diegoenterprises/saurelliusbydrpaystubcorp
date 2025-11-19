#!/bin/bash
set -xe

# Install Chromium dependencies for Amazon Linux 2
sudo yum install -y \
    libX11 \
    libXcomposite \
    libXcursor \
    libXdamage \
    libXext \
    libXi \
    libXtst \
    cups-libs \
    libXScrnSaver \
    libXrandr \
    alsa-lib \
    atk \
    at-spi2-atk \
    gtk3 \
    ipa-gothic-fonts

# Ensure pip and Playwright are installed
pip install --upgrade pip
pip install playwright

# Install Chromium browser for Playwright runtime
playwright install chromium
