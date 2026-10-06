"""REQ-015: the optional dev browser proxy refuses private DNS results."""
import pytest

from devtools.public_egress_proxy import choose_public_address


def record(ip):
    return (None, None, None, None, (ip, 443))


def test_proxy_pins_public_ip_and_rejects_mixed_dns():
    assert choose_public_address([record("2606:4700:4700::1111"), record("1.1.1.1")]) == "1.1.1.1"
    for addresses in ([], [record("127.0.0.1")], [record("192.168.1.4")],
                      [record("1.1.1.1"), record("10.0.0.1")]):
        with pytest.raises(ValueError, match="Non-public"):
            choose_public_address(addresses)
