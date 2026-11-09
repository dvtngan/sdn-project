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


class DnsTopo(Topo):
    def build(self):
        # switches
        s1 = self.addSwitch('s1')   # LAN A
        s2 = self.addSwitch('s2')   # LAN B
        s3 = self.addSwitch('s3')   # server LAN

        # router (IPs set after start)
        r1 = self.addHost('r1', ip='0.0.0.0')

        # LAN A hosts
        h1 = self.addHost('h1', ip='10.0.10.11/24')
        h2 = self.addHost('h2', ip='10.0.10.12/24')
        h3 = self.addHost('h3', ip='10.0.10.13/24')
        # LAN B hosts
        h4 = self.addHost('h4', ip='10.0.20.11/24')
        h5 = self.addHost('h5', ip='10.0.20.12/24')
        # server LAN
        srv = self.addHost('srv', ip='10.0.30.10/24')

        # hosts <-> switches
        self.addLink(h1, s1)
        self.addLink(h2, s1)
        self.addLink(h3, s1)
        self.addLink(h4, s2)
        self.addLink(h5, s2)
        self.addLink(srv, s3)

        # router <-> switches (creates r1-eth0/eth1/eth2)
        self.addLink(r1, s1)   # r1-eth0 -> LAN A
        self.addLink(r1, s2)   # r1-eth1 -> LAN B
        self.addLink(r1, s3)   # r1-eth2 -> server LAN


def run():
    setLogLevel('info')
    topo = DnsTopo()
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

    # default route for each host via its gateway
    for name in ['h1', 'h2', 'h3']:
        net.get(name).cmd('ip route add default via 10.0.10.1')
    for name in ['h4', 'h5']:
        net.get(name).cmd('ip route add default via 10.0.20.1')
    net.get('srv').cmd('ip route add default via 10.0.30.1')

    print("Topology started.")
    print("LAN A: 10.0.10.0/24 (h1,h2,h3)")
    print("LAN B: 10.0.20.0/24 (h4,h5)")
    print("Server LAN: 10.0.30.0/24 (srv)")
    CLI(net)
    net.stop()


if __name__ == '__main__':
    run()
