#!/usr/bin/env python3
# Flat single-subnet SDN fabric for Host Location Hijacking MITM (3 nodes).
# s1-s2-s3 wired as one OpenFlow fabric under ONOS.
#   h1  (victim)   on s1
#   srv (the peer) on s2   <- talks to h1
#   atk (attacker) on s3   <- hijacks h1, sits in the middle

from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import RemoteController
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.log import setLogLevel


class HlhTopo(Topo):
    def build(self):
        s1 = self.addSwitch('s1', protocols='OpenFlow13')
        s2 = self.addSwitch('s2', protocols='OpenFlow13')
        s3 = self.addSwitch('s3', protocols='OpenFlow13')

        # three nodes, one subnet 10.0.0.0/24
        h1  = self.addHost('h1',  ip='10.0.0.11/24')   # victim
        srv = self.addHost('srv', ip='10.0.0.10/24')   # the peer h1 talks to
        atk = self.addHost('atk', ip='10.0.0.66/24')   # attacker (man in the middle)

        self.addLink(h1,  s1)
        self.addLink(srv, s2)
        self.addLink(atk, s3)

        # inter-switch OpenFlow links (line s1-s2-s3, loop-free)
        self.addLink(s1, s2)
        self.addLink(s2, s3)


def run():
    setLogLevel('info')
    net = Mininet(topo=HlhTopo(),
                  controller=RemoteController('c0', ip='127.0.0.1', port=6653),
                  link=TCLink, autoSetMacs=True)
    net.start()
    print("Flat SDN fabric started (3 nodes, one subnet, s1-s2-s3).")
    print("Victim   : h1  10.0.0.11  (s1)")
    print("Server   : srv 10.0.0.10  (s2)")
    print("Attacker : atk 10.0.0.66  (s3)")
    CLI(net)
    net.stop()


if __name__ == '__main__':
    run()
