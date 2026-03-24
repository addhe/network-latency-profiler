import unittest
from unittest.mock import patch, MagicMock
import socket
import asyncio
from network_latency_profiler import LatencyProfiler

class TestLatencyProfiler(unittest.TestCase):
    def setUp(self):
        self.profiler = LatencyProfiler(target_host="localhost", num_requests=1)

    @patch('socket.getaddrinfo')
    def test_measure_dns_latency(self, mock_getaddr):
        mock_getaddr.return_value = [ (2, 1, 6, '', ('127.0.0.1', 443)) ]
        latency = self.profiler.measure_dns_latency()
        self.assertIsNotNone(latency)
        self.assertIn('dns_resolution', self.profiler.results)

    @patch('socket.socket')
    def test_measure_socket_syscall_latency(self, mock_socket):
        latency = self.profiler.measure_socket_syscall_latency()
        self.assertIsNotNone(latency)
        self.assertIn('socket_syscall', self.profiler.results)

    @patch('subprocess.run')
    def test_measure_icmp_latency_macos(self, mock_run):
        # Mock macOS ping output
        mock_run.return_value.stdout = "round-trip min/avg/max/stddev = 10.0/15.0/20.0/5.0 ms"
        latency = self.profiler.measure_icmp_latency()
        self.assertEqual(latency, 15_000_000) # 15ms in ns

    @patch('subprocess.run')
    def test_measure_icmp_latency_linux(self, mock_run):
        # Mock Linux ping output
        mock_run.return_value.stdout = "rtt min/avg/max/mdev = 10.0/15.0/20.0/5.0 ms"
        latency = self.profiler.measure_icmp_latency()
        self.assertEqual(latency, 15_000_000) # 15ms in ns

    def test_format_latency_us(self):
        formatted = self.profiler.format_latency(500_000) # 500us
        self.assertEqual(formatted, "500.00 μs")

    def test_format_latency_ms(self):
        formatted = self.profiler.format_latency(5_000_000) # 5ms
        self.assertEqual(formatted, "5.00 ms")

if __name__ == '__main__':
    unittest.main()
