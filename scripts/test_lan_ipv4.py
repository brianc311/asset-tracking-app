import unittest

from scripts.make_dev_https_cert import (
    _adapter_is_virtual,
    _ipv4_by_adapter_from_ipconfig,
)


IPCONFIG = """
Ethernet adapter Ethernet 2:

   IPv4 Address. . . . . . . . . . . : 192.168.30.73

Ethernet adapter vEthernet (Default Switch):

   Autoconfiguration IPv4 Address. . : 169.254.1.1
   IPv4 Address. . . . . . . . . . . : 172.26.240.1

Wireless LAN adapter Bluetooth Network Connection:

   IPv4 Address. . . . . . . . . . . : 192.168.44.1
"""


class LanIpv4Tests(unittest.TestCase):
    def test_ipconfig_parser_keeps_adapter_names(self):
        found = _ipv4_by_adapter_from_ipconfig(IPCONFIG)
        self.assertEqual(
            found,
            [
                ("Ethernet 2", "192.168.30.73"),
                ("vEthernet (Default Switch)", "172.26.240.1"),
                ("Bluetooth Network Connection", "192.168.44.1"),
            ],
        )

    def test_virtual_adapter_names(self):
        self.assertTrue(_adapter_is_virtual("vEthernet (Default Switch)"))
        self.assertTrue(_adapter_is_virtual("Bluetooth Network Connection"))
        self.assertFalse(_adapter_is_virtual("Ethernet 2"))
        self.assertFalse(_adapter_is_virtual("Wi-Fi"))


if __name__ == "__main__":
    unittest.main()
