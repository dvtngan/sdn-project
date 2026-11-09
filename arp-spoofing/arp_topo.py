#!/usr/bin/env python3
from mininet.topo import Topo
from mininet.node import Node


class Router(Node):
    def config(self, **params):
        super().config(**params)
        self.cmd('sysctl -w net.ipv4.ip_forward=1')

    def terminate(self):
        self.cmd('sysctl -w net.ipv4.ip_forward=0')
        super().terminate()


class MyTopo(Topo):
    def build(self):
        r1 = self.addNode('r1', cls=Router, ip='10.0.10.1/24')

        s1 = self.addSwitch('s1')   # LAN A
        s2 = self.addSwitch('s2')   # LAN B
        s3 = self.addSwitch('s3')   # server LAN

        # router <-> switches
        self.addLink(s1, r1, intfName2='r1-eth1', params2={'ip': '10.0.10.1/24'})
        self.addLink(s2, r1, intfName2='r1-eth2', params2={'ip': '10.0.20.1/24'})
        self.addLink(s3, r1, intfName2='r1-eth3', params2={'ip': '10.0.30.1/24'})

        # LAN A: 10.0.10.0/24
        h1 = self.addHost('h1', ip='10.0.10.11/24', defaultRoute='via 10.0.10.1')
        h2 = self.addHost('h2', ip='10.0.10.12/24', defaultRoute='via 10.0.10.1')
        h3 = self.addHost('h3', ip='10.0.10.13/24', defaultRoute='via 10.0.10.1')
        # LAN B: 10.0.20.0/24
        h4 = self.addHost('h4', ip='10.0.20.11/24', defaultRoute='via 10.0.20.1')
        h5 = self.addHost('h5', ip='10.0.20.12/24', defaultRoute='via 10.0.20.1')
        # server LAN: 10.0.30.0/24
        srv = self.addHost('srv', ip='10.0.30.10/24', defaultRoute='via 10.0.30.1')

        # hosts <-> switches
        self.addLink(h1, s1)
        self.addLink(h2, s1)
        self.addLink(h3, s1)
        self.addLink(h4, s2)
        self.addLink(h5, s2)
        self.addLink(srv, s3)


topos = {'mytopo': (lambda: MyTopo())}
