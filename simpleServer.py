#!/usr/bin/env python3
#A simple DNS server that supports A, AAAA, CNAME requests
#REMEMBER TO DISABLE .ps1 SCRIPTS AFTER THE EXPERIMENT!

from dnslib import DNSRecord, RR, QTYPE, A, AAAA, MX, TXT, RCODE, SOA
from dnslib.server import DNSServer, DNSLogger
import socket, os, time

#Server configuration for the developing stage
PORT = 5353
ADDRESS = '127.0.0.1'
START_TIME = time.strftime("%m_%d_%H_%M_%S", time.localtime())
LOGNAME = 'DNSlog' + f'{START_TIME}.txt'

#Keep in track of the requests and replies, and print them out at the console
def mylogf(whattolog:str):
    with open('log\\' + LOGNAME, 'a') as f:
        f.writelines(whattolog + '\n')
    print(whattolog)

class HybridResolver:
    def __init__(self, upstream="8.8.8.8"):
        self.upstream = upstream
        self.records = {
            "local.test.": ("A", "192.168.1.100"),
            "ipv6.test.": ("AAAA", "2001:db8::1"),
            "mail.test.": ("MX", (10, "mail.local.test.")),
            "info.test.": ("TXT", "This is a test record"),
            # format: <site> : (<type>, <address>)      not good enough :(
        }
        #A temporary cache, waiting for an alternative...(TODO: Maybe use the sqlite3 library?)
        self.newrecord = {
            QTYPE.A:{'local.test.':'0.0.0.0'},
            QTYPE.AAAA:{'local.test.':'2001:db8::1'},
            QTYPE.CNAME:{},
            QTYPE.SOA:{},
        }

        #Calculate the processing time and total amount of requests
        self.processing_time = 0.
        self.count = 0

        if 'log' not in os.listdir():
            os.mkdir('log')
        with open('log\\' + LOGNAME, 'w') as f:
            f.write(f'DNSServer start logging at {START_TIME}\n')
    
    #The main function of the resolver, which would be called by the DNSServer object.
    def resolve(self, request, handler):
        start = time.time()
        q = request.q
        qname = str(q.qname)
        qtype = q.qtype
        #print(f'Processing {qname}, with type {qtype}')
        
        try:
            #Check local records
            if qname in self.newrecord[qtype]:
                rdata = self.newrecord[qtype][qname]
                return self._build_reply(request, qname, qtype, rdata)
            #If the authority server does not find the CNAME record, it will return a SOA record as reply in the Authority Section
            elif qname in self.newrecord[QTYPE.SOA]:
                rname, rdata = self.newrecord[QTYPE.SOA][qname]
                return self._build_reply(request, rname, QTYPE.SOA, rdata)

            '''if qname in self.records:
                rtype, rdata = self.records[qname]
                if self._match_type(qtype, rtype):
                    return self._build_reply(request, qname, qtype, rdata)'''
            
            #Foward to upstream
            reply = self._forward(request)
            self.add_records(reply, qname)
            return reply
        finally:
            self.processing_time += time.time() - start
            self.count += 1
    
    #QTYPE.xxx is a enumarate type, which will be evaluated into integers
    def _match_type(self, qtype, rtype_str):
        type_map = {"A": QTYPE.A, "AAAA": QTYPE.AAAA, "MX": QTYPE.MX, "TXT": QTYPE.TXT}
        return qtype == type_map.get(rtype_str)
    
    #Build replies according to the query type
    def _build_reply(self, request, qname, qtype, rdata):
        reply = request.reply()
        
        if qtype == QTYPE.A:
            reply.add_answer(RR(qname, QTYPE.A, rdata=A(rdata), ttl=60))
        elif qtype == QTYPE.AAAA:
            reply.add_answer(RR(qname, QTYPE.AAAA, rdata=AAAA(rdata), ttl=60))
        elif qtype == QTYPE.MX:
            pref, mx = rdata
            reply.add_answer(RR(qname, QTYPE.MX, rdata=MX(pref, mx), ttl=60))
        elif qtype == QTYPE.TXT:
            reply.add_answer(RR(qname, QTYPE.TXT, rdata=TXT(rdata), ttl=60))
        elif qtype == QTYPE.SOA:
            reply.add_auth(RR(qname, QTYPE.SOA, rdata=rdata, ttl=60)) 
        
        return reply
    
    #Use sockets to perform a query to higher-level DNS servers
    def _forward(self, request):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(3)
        try:
            sock.sendto(request.pack(), (self.upstream, 53))
            data, _ = sock.recvfrom(512)
            return DNSRecord.parse(data)
        except:
            reply = request.reply()
            reply.header.rcode = RCODE.SERVFAIL
            return reply
        finally:
            sock.close()

    #Once a new record appears, add it to the cache
    def add_records(self, reply, qname:str):
        for rr in reply.rr:
            mylogf(f'Adding new record : {rr.rtype} {rr.rname} {rr.rdata}')
            self.newrecord[rr.rtype][qname] = str(rr.rdata)
        if reply.auth:
            for rr in reply.auth:
                mylogf(f'Adding new record : {rr.rtype} {rr.rname} {rr.rdata} from SOA')
                self.newrecord[rr.rtype][qname] = (rr.rname, rr.rdata)
        

if __name__ == "__main__":

    #Initiating resolver and the DNSServer object
    resolver = HybridResolver()
    server = DNSServer(resolver, port=PORT, address=ADDRESS, logger=DNSLogger(logf=mylogf))
    print(f"DNS Server running on {ADDRESS}:{PORT}, with starting time {START_TIME}")

    #Start the server until being terminated by the keyboard
    try:      
        server.start()
    except KeyboardInterrupt:
        #The average processing time for a request is about 0.2 sec. 
        #With cache in hand, we can accelerate it to lesser than 0.01 sec!
        #How to manage it is another problem, though...
        print(f'DNS server terminates after resolving {resolver.count} requests, with total processing time {resolver.processing_time:.2f}s. \
              \nAverage processing time {resolver.processing_time/resolver.count:.2f}s.')
        #print(f'Final record list: {resolver.newrecord}')
        