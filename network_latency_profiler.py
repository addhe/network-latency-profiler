#!/usr/bin/env python3
"""
Network Latency Profiler
Measures latency at each hop: App → OS → NIC → Router → Endpoint
Precision: microsecond (μs) with optional nanosecond (ns)
"""

import socket
import time
import subprocess
import statistics
import re
import os
import sys
import platform
import asyncio
import aiohttp
from datetime import datetime
from collections import defaultdict

# For nanosecond precision
try:
    from time import perf_counter_ns
    HAS_NS = True
except ImportError:
    from time import perf_counter
    HAS_NS = False
    def perf_counter_ns():
        return int(perf_counter() * 1e9)


class LatencyProfiler:
    def __init__(self, target_host: str, target_port: int = 443, num_requests: int = 20):
        self.target_host = target_host
        self.target_port = target_port
        self.num_requests = num_requests
        self.results = defaultdict(list)
        self.platform = platform.system().lower()

    def now_ns(self):
        """Get current time in nanoseconds"""
        return perf_counter_ns()

    def ns_to_ms(self, ns):
        """Convert nanoseconds to milliseconds"""
        return ns / 1_000_000

    def ns_to_us(self, ns):
        """Convert nanoseconds to microseconds"""
        return ns / 1_000

    def format_latency(self, ns):
        """Format nanoseconds to a human-readable string (ms or μs)"""
        if ns < 1_000_000:
            return f"{self.ns_to_us(ns):.2f} μs"
        return f"{self.ns_to_ms(ns):.2f} ms"

    def measure_dns_latency(self):
        """
        Measure DNS resolution latency (Application → OS DNS Resolver)
        """
        latencies = []
        for _ in range(self.num_requests):
            start = self.now_ns()
            try:
                # getaddrinfo is generally better than gethostbyname on modern systems
                socket.getaddrinfo(self.target_host, self.target_port)
                end = self.now_ns()
                latencies.append(end - start)
            except socket.gaierror as e:
                print(f"DNS resolution failed: {e}")
                continue
        
        if latencies:
            self.results['dns_resolution'] = latencies
            return statistics.mean(latencies)
        return None

    def measure_tcp_handshake_latency(self):
        """
        Measure TCP handshake latency (Full Network RTT)
        """
        latencies = []
        try:
            addr_info = socket.getaddrinfo(self.target_host, self.target_port, socket.AF_INET, socket.SOCK_STREAM)
            ip = addr_info[0][4][0]
        except (socket.gaierror, IndexError):
            print("Cannot resolve host for TCP test")
            return None

        for _ in range(self.num_requests):
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2.0)
            start = self.now_ns()
            try:
                sock.connect((ip, self.target_port))
                end = self.now_ns()
                latencies.append(end - start)
            except Exception as e:
                pass
            finally:
                sock.close()

        if latencies:
            self.results['tcp_handshake'] = latencies
            return statistics.mean(latencies)
        return None

    def measure_socket_syscall_latency(self):
        """
        Measure overhead of socket() system call (App → OS Kernel)
        """
        latencies = []
        for _ in range(self.num_requests):
            start = self.now_ns()
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            end = self.now_ns()
            latencies.append(end - start)
            sock.close()

        if latencies:
            self.results['socket_syscall'] = latencies
            return statistics.mean(latencies)
        return None

    def measure_icmp_latency(self):
        """
        Measure ICMP ping latency using system ping command
        """
        try:
            # -c: count, -i: interval, -W: timeout (ms)
            # macOS and Linux both support -c and -i for root or small intervals
            # For simplicity, we'll use 0.2s interval to avoid needing root
            cmd = ['ping', '-c', str(self.num_requests), '-i', '0.2', self.target_host]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            output = result.stdout
            # regex for macOS (round-trip min/avg/max/stddev) and Linux (rtt min/avg/max/mdev)
            match = re.search(r'(?:rtt|round-trip) min/avg/max/(?:mdev|stddev) = ([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+) ms', output)
            if match:
                avg_ms = float(match.group(2))
                # For ping, we usually only get stats, but we can synthesize a list for the summary
                ns_val = int(avg_ms * 1_000_000)
                self.results['icmp_ping'] = [ns_val] 
                return ns_val
        except Exception as e:
            print(f"Ping failed: {e}")
        return None

    async def measure_http_request_latency(self):
        """
        Measure complete HTTP request latency (Full Stack)
        """
        latencies = []
        url = f"https://{self.target_host}"
        
        # Avoid SSL overhead if needed, but for performance testing we usually want the real thing
        async with aiohttp.ClientSession() as session:
            for _ in range(self.num_requests):
                start = self.now_ns()
                try:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                        await resp.read()
                        end = self.now_ns()
                        latencies.append(end - start)
                except Exception:
                    pass

        if latencies:
            self.results['http_request'] = latencies
            return statistics.mean(latencies)
        return None

    def measure_kernel_loopback_latency(self):
        """
        Estimate kernel-to-NIC latency using localhost socket (Local Loopback)
        """
        latencies = []
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.bind(('127.0.0.1', 0))
        server_sock.listen(1)
        port = server_sock.getsockname()[1]
        server_sock.settimeout(1.0)

        for _ in range(self.num_requests):
            try:
                client_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                client_sock.settimeout(1.0)
                
                start = self.now_ns()
                client_sock.connect(('127.0.0.1', port))
                conn, _ = server_sock.accept()
                
                # Small payload
                client_sock.sendall(b"PING")
                conn.recv(4)
                
                end = self.now_ns()
                latencies.append(end - start)
                
                client_sock.close()
                conn.close()
            except Exception:
                break
        
        server_sock.close()
        if latencies:
            self.results['kernel_loopback'] = latencies
            return statistics.mean(latencies)
        return None

    def get_interface_stats(self):
        """
        Cross-platform Interface Statistics
        """
        stats = {}
        if self.platform == 'darwin':
            try:
                # Name Mtu Network Address Ipkts Ierrs Ibytes Opkts Oerrs Obytes Coll
                output = subprocess.check_output(['netstat', '-ibn'], text=True)
                lines = output.strip().split('\n')
                for line in lines[1:]:
                    parts = line.split()
                    if len(parts) >= 10:
                        name = parts[0]
                        try:
                            stats[name] = {
                                'rx_packets': int(parts[4]),
                                'tx_packets': int(parts[7]),
                                'rx_bytes': int(parts[6]),
                                'tx_bytes': int(parts[9])
                            }
                        except ValueError:
                            continue
            except Exception:
                pass
        else: # Default to Linux /proc/net/dev
            try:
                if os.path.exists('/proc/net/dev'):
                    with open('/proc/net/dev', 'r') as f:
                        lines = f.readlines()
                    for line in lines[2:]:
                        parts = line.split()
                        ifname = parts[0].rstrip(':')
                        stats[ifname] = {
                            'rx_bytes': int(parts[1]),
                            'rx_packets': int(parts[2]),
                            'tx_bytes': int(parts[9]),
                            'tx_packets': int(parts[10])
                        }
            except Exception:
                pass
        return stats

    def print_header(self):
        print("=" * 70)
        print(f" NETWORK LATENCY PROFILER ".center(70, "="))
        print(f" Target Host: {self.target_host}:{self.target_port}")
        print(f" Requests:    {self.num_requests}")
        print(f" Platform:    {platform.system()} ({platform.machine()})")
        print(f" Time:        {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 70)
        print()

    def measure_gateway_latency(self):
        """
        Measure latency to the default gateway (NIC -> Router).
        """
        gateway_ip = None
        try:
            if self.platform == 'darwin':
                # macOS: netstat -nr | grep default
                output = subprocess.check_output("netstat -nr | grep default | head -n 1", shell=True, text=True)
                gateway_ip = output.split()[1]
            else:
                # Linux: ip route | grep default
                output = subprocess.check_output("ip route | grep default | head -n 1", shell=True, text=True)
                gateway_ip = output.split()[2]
        except Exception:
            return None

        if not gateway_ip:
            return None

        # Measure RTT to gateway using 3 quick pings
        try:
            cmd = ['ping', '-c', '3', '-i', '0.2', '-W', '1', gateway_ip]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            match = re.search(r'(?:rtt|round-trip) min/avg/max/(?:mdev|stddev) = ([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+) ms', result.stdout)
            if match:
                avg_ms = float(match.group(2))
                ns_val = int(avg_ms * 1_000_000)
                self.results['gateway_ping'] = [ns_val]
                return ns_val
        except Exception:
            pass
        return None

    def get_rating(self, ms):
        if ms < 20: return "🟢 EXCELLENT"
        if ms < 50: return "🟢 GOOD"
        if ms < 150: return "🟡 FAIR"
        return "🔴 POOR / HIGH LATENCY"

    def print_journey_map(self):
        print("\n" + " DATA JOURNEY MAP ".center(60, "="))
        
        dns = statistics.mean(self.results.get('dns_resolution', [0]))
        gateway = statistics.mean(self.results.get('gateway_ping', [0]))
        tcp = statistics.mean(self.results.get('tcp_handshake', [0]))
        
        print(f"\n [🏠 APP] -> [💻 OS KERNEL] -> [📶 ROUTER] -> [🌐 INTERNET] -> [🎯 ENDPOINT]")
        print(f"    |           |               |               |               |")
        
        # Breakdown steps
        step1 = self.ns_to_us(statistics.mean(self.results.get('socket_syscall', [0])))
        step2 = self.ns_to_us(statistics.mean(self.results.get('kernel_loopback', [0])))
        
        print(f"    +-- Syscall: {step1:.1f} μs")
        print(f"    +-- OS Internal: {step2:.1f} μs")
        if gateway:
            print(f"    +-- Local Network (to Router): {self.ns_to_ms(gateway):.2f} ms")
        if tcp:
            net_only = max(0, tcp - gateway)
            print(f"    +-- ISP/Public Internet: {self.ns_to_ms(net_only):.2f} ms")
        if dns:
            print(f"    +-- Address Lookup (DNS): {self.ns_to_ms(dns):.2f} ms")

    def run_full_profile(self):
        self.print_header()

        # Execute tests sequentially
        tests = [
            ("Socket Syscall (App -> Kernel)", self.measure_socket_syscall_latency),
            ("Kernel Loopback (Local RTT)", self.measure_kernel_loopback_latency),
            ("Gateway Latency (To Router)", self.measure_gateway_latency),
            ("DNS Resolution (App -> DNS)", self.measure_dns_latency),
            ("ICMP Ping (NIC -> Endpoint)", self.measure_icmp_latency),
            ("TCP Ping (SYN-ACK RTT)", self.measure_tcp_handshake_latency),
        ]

        for i, (name, func) in enumerate(tests, 1):
            print(f"[{i}/{len(tests)+1}] Measuring {name}...", end="\r")
            val = func()
            if val:
                print(f"[{i}/{len(tests)+1}] {name:<30}: {self.format_latency(val)}")
            else:
                hint = " (Commonly blocked)" if "ICMP" in name else ""
                print(f"[{i}/{len(tests)+1}] {name:<30}: FAILED{hint}")

        print(f"[{len(tests)+1}/{len(tests)+1}] Measuring Full HTTP Request...", end="\r")
        http_latency = asyncio.run(self.measure_http_request_latency())
        if http_latency:
            print(f"[{len(tests)+1}/{len(tests)+1}] {'HTTP Request (Full Stack)':<30}: {self.format_latency(http_latency)}")

    def print_summary(self):
        summary_text = []
        header = f"{'MEASUREMENT TYPE':<35} {'MEAN':<15} {'RATING':<15}"
        summary_text.append(header)
        summary_text.append("-" * 75)

        metrics = [
            ('socket_syscall', 'Application Processing'),
            ('kernel_loopback', 'OS Internal Overhead'),
            ('gateway_ping', 'Local Network (Router)'),
            ('dns_resolution', 'DNS Translation'),
            ('tcp_handshake', 'Network Round-Trip (RTT)'),
            ('http_request', 'Total Transaction Time')
        ]

        for key, display_name in metrics:
            latencies = self.results.get(key)
            if not latencies: continue

            avg_val = statistics.mean(latencies)
            rating = self.get_rating(self.ns_to_ms(avg_val)) if 'Network' in display_name or 'Total' in display_name or 'Router' in display_name else "-"
            
            row = f"{display_name:<35} {self.format_latency(avg_val):<15} {rating:<15}"
            summary_text.append(row)

        print("\n" + " FINAL PERFORMANCE SUMMARY ".center(75, "="))
        print("-" * 75)
        for line in summary_text:
            print(line)
        print("=" * 75)

        self.print_journey_map()
        
        # interface snap
        stats = self.get_interface_stats()
        if stats:
            print("\n" + " INTERFACE SNAPSHOT ".center(40, "-"))
            for iface, s in sorted(stats.items(), key=lambda x: x[1]['rx_packets'], reverse=True)[:2]:
                if s['rx_packets'] > 0:
                    print(f" {iface:<8}: RX {s['rx_packets']} pkts, TX {s['tx_packets']} pkts")
            print("-" * 40)
            
        return "\n".join(summary_text)

    async def send_webhook_report(self, webhook_url, report_content):
        """Send the latency report to a Slack or Google Chat webhook."""
        if not webhook_url:
            return

        payload = {
            "text": f"🚀 *Network Latency Report*\nTarget: `{self.target_host}:{self.target_port}`\n```\n{report_content}\n```"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=payload, timeout=10) as resp:
                    if resp.status in [200, 201]:
                        print(f"\n✅ Report sent successfully to webhook.")
                    else:
                        print(f"\n❌ Failed to send report. Status: {resp.status}")
        except Exception as e:
            print(f"\n❌ Error sending webhook: {e}")

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Network Latency Profiler')
    parser.add_argument('--host', default='google.com', help='Target hostname (default: google.com)')
    parser.add_argument('--port', type=int, default=443, help='Target port (default: 443)')
    parser.add_argument('--requests', type=int, default=20, help='Number of requests (default: 20)')
    parser.add_argument('--webhook', help='Slack or Google Chat Webhook URL (optional)')
    args = parser.parse_args()

    profiler = LatencyProfiler(
        target_host=args.host,
        target_port=args.port,
        num_requests=args.requests
    )

    try:
        profiler.run_full_profile()
        # Collect summary for final display (and webhook if provided)
        summary = profiler.print_summary()
        
        if args.webhook:
            asyncio.run(profiler.send_webhook_report(args.webhook, summary))
            
    except KeyboardInterrupt:
        print("\nProfiling interrupted by user.")
    except Exception as e:
        print(f"\nAn error occurred: {e}")

if __name__ == '__main__':
    main()
