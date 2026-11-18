#!/usr/bin/env python3
from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import RemoteController
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.log import setLogLevel


class ArpTopo(Topo):
    def build(self):
        s1 = self.addSwitch('s1', protocols='OpenFlow13')   # LAN A
        s2 = self.addSwitch('s2', protocols='OpenFlow13')   # LAN B
        s3 = self.addSwitch('s3', protocols='OpenFlow13')   # server LAN

        r1 = self.addHost('r1', ip='0.0.0.0')

        # LAN A: two victims + the attacker, all on the same switch
        h1 = self.addHost('h1', ip='10.0.10.11/24')    # victim 1
        h2 = self.addHost('h2', ip='10.0.10.12/24')    # victim 2
        h3 = self.addHost('h3', ip='10.0.10.13/24')
        atk = self.addHost('atk', ip='10.0.10.66/24')  # attacker (me)

        # LAN B
        h4 = self.addHost('h4', ip='10.0.20.11/24')
        h5 = self.addHost('h5', ip='10.0.20.12/24')
        # server LAN
        srv = self.addHost('srv', ip='10.0.30.10/24')

        self.addLink(h1, s1)
        self.addLink(h2, s1)
        self.addLink(h3, s1)
        self.addLink(atk, s1)
        self.addLink(h4, s2)
        self.addLink(h5, s2)
        self.addLink(srv, s3)

        # router to each switch
        self.addLink(r1, s1)   # r1-eth0 -> LAN A
        self.addLink(r1, s2)   # r1-eth1 -> LAN B
        self.addLink(r1, s3)   # r1-eth2 -> server LAN


def run():
    setLogLevel('info')
    topo = ArpTopo()
    # NOTE: 172.17.0.2 is the ONOS Docker container's address on this machine.
    # On another machine, check it with:
    #   docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' onos
    # and change the ip below if it differs.
    net = Mininet(topo=topo,
                  controller=RemoteController('c0', ip='172.17.0.2', port=6653),
                  link=TCLink, autoSetMacs=True)
    net.start()

    # give the router an IP on each side
    r1 = net.get('r1')
    r1.cmd('ifconfig r1-eth0 10.0.10.1/24')
    r1.cmd('ifconfig r1-eth1 10.0.20.1/24')
    r1.cmd('ifconfig r1-eth2 10.0.30.1/24')
    r1.cmd('sysctl -w net.ipv4.ip_forward=1')

    # default route for each host
    for name in ['h1', 'h2', 'h3', 'atk']:
        net.get(name).cmd('ip route add default via 10.0.10.1')
    for name in ['h4', 'h5']:
        net.get(name).cmd('ip route add default via 10.0.20.1')
    net.get('srv').cmd('ip route add default via 10.0.30.1')

    print("Topology started.")
    print("Victim 1 : h1  10.0.10.11  (LAN A / s1)")
    print("Victim 2 : h2  10.0.10.12  (LAN A / s1)")
    print("Attacker : atk 10.0.10.66  (LAN A / s1)")
    CLI(net)
    net.stop()


if __name__ == '__main__':
    run()
