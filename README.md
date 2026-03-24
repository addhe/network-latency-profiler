# Network Latency Profiler

A Python tool designed for deep network latency analysis by breaking down measurements into distinct stages: Application, OS Kernel, and Network.

## Features
- **Hop Breakdown**: Measures latency at each stage (Socket, DNS, Kernel, TCP, ICMP, HTTP).
- **Webhook Integration**: Send reports automatically to **Slack** or **Google Chat**.
- **Cross-Platform**: Support for macOS and Linux.
- **High Precision**: Nanosecond-level measurement where available.

## Installation & Setup

### 1. Create a Virtual Environment (Recommended)
```bash
# Create venv
python3 -m venv venv

# Activate venv (macOS/Linux)
source venv/bin/activate

# Activate venv (Windows)
# venv\Scripts\activate
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

## Usage

### Basic Usage
Run with default settings (Target: google.com):
```bash
python3 network_latency_profiler.py
```

### Advanced Usage
Customize target, request count, and send report to Slack/Google Chat:
```bash
python3 network_latency_profiler.py \
  --host example.com \
  --port 443 \
  --requests 50 \
  --webhook "https://hooks.slack.com/services/T000/B000/XXXX"
```

## Running Tests
To run the automated test suite:
```bash
python3 test_latency_profiler.py
```

## Understanding the Breakdown
- **Local App/Kernel Overhead**: Baseline latency of your OS networking stack.
- **Actual Network Latency**: Derived by subtracting local overhead from the TCP handshake.
- **Total RTT**: The actual time perceived for a full round-trip.

---
Created for performance profiling and network troubleshooting.
