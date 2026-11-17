#!/usr/bin/env python3

from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import RemoteController, Node
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


class HlhTopo(Topo):
    def build(self):
        # switches - pinned to OpenFlow 1.3 (ONOS<->OVS fail to negotiate 1.5:
        # meter-features reply length mismatch breaks the switch connection)
        s1 = self.addSwitch('s1', protocols='OpenFlow13')   # LAN A (victim side)
        s2 = self.addSwitch('s2', protocols='OpenFlow13')   # LAN B
        s3 = self.addSwitch('s3', protocols='OpenFlow13')   # server LAN (attacker + server)

        # router (IPs set after start)
        r1 = self.addHost('r1', ip='0.0.0.0')

        # LAN A: victim + a neighbour
        h1 = self.addHost('h1', ip='10.0.10.11/24')   # victim
        h2 = self.addHost('h2', ip='10.0.10.12/24')
        h3 = self.addHost('h3', ip='10.0.10.13/24')
        # LAN B: regular hosts (will try to reach the victim)
        h4 = self.addHost('h4', ip='10.0.20.11/24')
        h5 = self.addHost('h5', ip='10.0.20.12/24')
        # server LAN: a server + the attacker (different location than victim)
        srv = self.addHost('srv', ip='10.0.30.10/24')
        atk = self.addHost('atk', ip='10.0.30.66/24')  # attacker

        # hosts <-> switches
        self.addLink(h1, s1)
        self.addLink(h2, s1)
        self.addLink(h3, s1)
        self.addLink(h4, s2)
        self.addLink(h5, s2)
        self.addLink(srv, s3)
        self.addLink(atk, s3)

        # router <-> switches
        self.addLink(r1, s1)   # r1-eth0 -> LAN A
        self.addLink(r1, s2)   # r1-eth1 -> LAN B
        self.addLink(r1, s3)   # r1-eth2 -> server LAN


def run():
    setLogLevel('info')
    topo = HlhTopo()
    net = Mininet(topo=topo,
                  controller=RemoteController('c0', ip='127.0.0.1', port=6653),
                  link=TCLink, autoSetMacs=True)
    net.start()

    # configure router interfaces
    r1 = net.get('r1')
    r1.cmd('ifconfig r1-eth0 10.0.10.1/24')
    r1.cmd('ifconfig r1-eth1 10.0.20.1/24')
    r1.cmd('ifconfig r1-eth2 10.0.30.1/24')
    r1.cmd('sysctl -w net.ipv4.ip_forward=1')

    # default routes
    for name in ['h1', 'h2', 'h3']:
        net.get(name).cmd('ip route add default via 10.0.10.1')
    for name in ['h4', 'h5']:
        net.get(name).cmd('ip route add default via 10.0.20.1')
    for name in ['srv', 'atk']:
        net.get(name).cmd('ip route add default via 10.0.30.1')

    print("Topology started.")
    print("Victim   : h1  10.0.10.11  (s1 / LAN A)")
    print("Attacker : atk 10.0.30.66  (s3 / server LAN)")
    print("Server   : srv 10.0.30.10  (s3)")
    CLI(net)
    net.stop()


if __name__ == '__main__':
    run()
