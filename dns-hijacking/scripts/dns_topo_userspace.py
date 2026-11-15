#!/usr/bin/env python3
"""
Userspace-datapath version of the project topology (../dns_topo.py).
Identical addressing, but Open vSwitch is forced into USERSPACE datapath
mode so the topology runs in environments without the OVS kernel module
(e.g. containers). On a host with the kernel datapath, ../dns_topo.py works.

Topology:
  LAN A  10.0.10.0/24 : h1(.11)  h2(.12)  h3(.13 = attacker)
  LAN B  10.0.20.0/24 : h4(.11)  h5(.12)
  SrvLAN 10.0.30.0/24 : srv(.10 = legit DNS)
  Router r1 : 10.0.10.1 / 10.0.20.1 / 10.0.30.1
  Controller: ONOS (RemoteController 127.0.0.1:6653)

Switch port layout (needed for the OpenFlow rules):
  s1: port1=h1  port2=h2  port3=h3  port4=r1
"""
from functools import partial

from mininet.net import Mininet
from mininet.node import RemoteController, Node, OVSSwitch
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.log import setLogLevel


class Router(Node):
    def config(self, **params):
        super().config(**params)
        self.cmd('sysctl -w net.ipv4.ip_forward=1')

    def terminate(self):
        self.cmd('sysctl -w net.ipv4.ip_forward=0')
        super().terminate()


def run():
    setLogLevel('info')

    # datapath='user' => OVS userspace forwarding (works in containers).
    # protocols='OpenFlow13' => ONOS 2.7 requires OF1.3; without this the
    # switch offers OF1.0, the handshake fails, and ONOS logs DPID[?] /
    # "no dpid registered" and registers no device.
    UserSwitch = partial(OVSSwitch, datapath='user', protocols='OpenFlow13')

    net = Mininet(controller=None, switch=UserSwitch,
                  link=TCLink, autoSetMacs=True)

    c0 = net.addController('c0', controller=RemoteController,
                           ip='127.0.0.1', port=6653)

    s1 = net.addSwitch('s1')   # LAN A
    s2 = net.addSwitch('s2')   # LAN B
    s3 = net.addSwitch('s3')   # server LAN

    r1 = net.addHost('r1', cls=Router, ip='0.0.0.0')

    # LAN A hosts (h3 is the attacker)
    h1 = net.addHost('h1', ip='10.0.10.11/24', defaultRoute='via 10.0.10.1')
    h2 = net.addHost('h2', ip='10.0.10.12/24', defaultRoute='via 10.0.10.1')
    h3 = net.addHost('h3', ip='10.0.10.13/24', defaultRoute='via 10.0.10.1')
    # LAN B hosts
    h4 = net.addHost('h4', ip='10.0.20.11/24', defaultRoute='via 10.0.20.1')
    h5 = net.addHost('h5', ip='10.0.20.12/24', defaultRoute='via 10.0.20.1')
    # server LAN (legit DNS lives here)
    srv = net.addHost('srv', ip='10.0.30.10/24', defaultRoute='via 10.0.30.1')

    # hosts <-> switches  (order fixes the switch port numbers)
    net.addLink(h1, s1)   # s1-eth1
    net.addLink(h2, s1)   # s1-eth2
    net.addLink(h3, s1)   # s1-eth3  (attacker)
    net.addLink(h4, s2)
    net.addLink(h5, s2)
    net.addLink(srv, s3)

    # router <-> switches (creates r1-eth0/eth1/eth2)
    net.addLink(r1, s1)   # s1-eth4
    net.addLink(r1, s2)
    net.addLink(r1, s3)

    net.start()

    # Configure the router's three interfaces.
    r1.cmd('ifconfig r1-eth0 10.0.10.1/24')
    r1.cmd('ifconfig r1-eth1 10.0.20.1/24')
    r1.cmd('ifconfig r1-eth2 10.0.30.1/24')
    r1.cmd('sysctl -w net.ipv4.ip_forward=1')

    print("\nTopology started (userspace OVS).")
    print("LAN A: 10.0.10.0/24  h1(.11) h2(.12) h3(.13 attacker)")
    print("LAN B: 10.0.20.0/24  h4(.11) h5(.12)")
    print("Srv  : 10.0.30.0/24  srv(.10 legit DNS)")
    print("Run 'pingall' first so ONOS learns all hosts.\n")

    CLI(net)
    net.stop()


if __name__ == '__main__':
    run()
