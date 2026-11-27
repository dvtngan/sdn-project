#!/usr/bin/env python3
# Shared 3-LAN routed testbed (same as the team's), with the attacker
# placed on the VICTIM'S switch (s1 / LAN A) so the HLHA MITM can intercept.
from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import RemoteController, Node
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.log import setLogLevel


class HlhTopo(Topo):
    def build(self):
        s1 = self.addSwitch('s1', protocols='OpenFlow13')   # LAN A (victim + attacker)
        s2 = self.addSwitch('s2', protocols='OpenFlow13')   # LAN B
        s3 = self.addSwitch('s3', protocols='OpenFlow13')   # server LAN

        r1 = self.addHost('r1', ip='0.0.0.0')

        # LAN A: 10.0.10.0/24  (victim + attacker on the SAME switch)
        h1  = self.addHost('h1',  ip='10.0.10.11/24')   # victim
        h2  = self.addHost('h2',  ip='10.0.10.12/24')
        h3  = self.addHost('h3',  ip='10.0.10.13/24')
        atk = self.addHost('atk', ip='10.0.10.66/24')   # attacker (man in the middle)
        # LAN B: 10.0.20.0/24
        h4 = self.addHost('h4', ip='10.0.20.11/24')
        h5 = self.addHost('h5', ip='10.0.20.12/24')
        # server LAN: 10.0.30.0/24
        srv = self.addHost('srv', ip='10.0.30.10/24')   # the server h1 talks to

        self.addLink(h1,  s1)
        self.addLink(h2,  s1)
        self.addLink(h3,  s1)
        self.addLink(atk, s1)   # <-- attacker on the victim's switch
        self.addLink(h4,  s2)
        self.addLink(h5,  s2)
        self.addLink(srv, s3)

        self.addLink(r1, s1)   # r1-eth0 -> LAN A
        self.addLink(r1, s2)   # r1-eth1 -> LAN B
        self.addLink(r1, s3)   # r1-eth2 -> server LAN


def run():
    setLogLevel('info')
    net = Mininet(topo=HlhTopo(),
                  controller=RemoteController('c0', ip='127.0.0.1', port=6653),
                  link=TCLink, autoSetMacs=True)
    net.start()
    r1 = net.get('r1')
    r1.cmd('ifconfig r1-eth0 10.0.10.1/24')
    r1.cmd('ifconfig r1-eth1 10.0.20.1/24')
    r1.cmd('ifconfig r1-eth2 10.0.30.1/24')
    r1.cmd('sysctl -w net.ipv4.ip_forward=1')

    for name in ['h1', 'h2', 'h3', 'atk']:
        net.get(name).cmd('ip route add default via 10.0.10.1')
    for name in ['h4', 'h5']:
        net.get(name).cmd('ip route add default via 10.0.20.1')
    net.get('srv').cmd('ip route add default via 10.0.30.1')

    print("Shared routed testbed (attacker on the victim's LAN A).")
    print("Victim   : h1  10.0.10.11  (s1 / LAN A)")
    print("Attacker : atk 10.0.10.66  (s1 / LAN A)")
    print("Server   : srv 10.0.30.10  (s3 / server LAN)")
    CLI(net)
    net.stop()


if __name__ == '__main__':
    run()
