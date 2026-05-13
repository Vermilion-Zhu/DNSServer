#!/usr/bin/env python3
"""Simple human-friendly DNS query tool (dig-like).

Usage examples:
  python dns_client.py @127.0.0.1 example.com A
  python dns_client.py example.com AAAA
"""
import argparse
import sys
import socket
import dns.message
import dns.query
import dns.rdatatype
import dns.rcode
import dns.resolver


def usage():
    print("Usage: dns_client.py [@server] name [type]")
    print("Example: dns_client.py @127.0.0.1 example.com A")


def parse_args(argv):
    parser = argparse.ArgumentParser(
        prog="dns_client.py",
        description="DNS query tool (dig-like)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
            python dns_client.py @127.0.0.1 example.com A
            python dns_client.py example.com AAAA
            python dns_client.py -h"""
    )
    parser.add_argument('arguments', nargs='+', 
                        help='[@server] name [type] - server with @ prefix, name is required, type defaults to A')
    
    args = parser.parse_args(argv)
    
    server = None
    qtype = "A"
    qname = None
    i = 0
    
    if args.arguments[0].startswith("@"):
        server = args.arguments[0][1:]
        i = 1
    
    if i < len(args.arguments):
        qname = args.arguments[i]
        i += 1
    
    if i < len(args.arguments):
        qtype = args.arguments[i].upper()
    
    if not qname:
        parser.error("name is required")
    
    return server, qname, qtype


def send_query(server: str, qname: str, qtype: str, port: int = 53):
    q = dns.message.make_query(qname, qtype)
    try:
        # try UDP first
        resp = dns.query.udp(q, server, port=port, timeout=3)
        return resp
    except Exception:
        try:
            resp = dns.query.tcp(q, server, port=port, timeout=5)
            return resp
        except Exception as e:
            raise



def print_section(title: str, section):
    if not section:
        return
    print(f"{title} SECTION:")
    for rrset in section:
        try:
            name = rrset.name.to_text()
        except Exception:
            name = str(rrset)
        ttl = getattr(rrset, "ttl", "")
        rtype = dns.rdatatype.to_text(rrset.rdtype)
        # join records in rrset
        rdatas = []
        for r in rrset:
            try:
                rdatas.append(r.to_text())
            except Exception:
                rdatas.append(str(r))
        print(f"{name}\t{ttl}\tIN\t{rtype}\t{', '.join(rdatas)}")


def main(argv):
    server, qname, qtype = parse_args(argv)

    resolver = dns.resolver.Resolver()
    if not server:
        # use first system nameserver
        if resolver.nameservers:
            server = resolver.nameservers[0]
        else:
            server = "127.0.0.1"

    try:
        print(f"\U0001F50D Querying {server} for {qname} {qtype}")
        resp = send_query(server, qname, qtype)
    except Exception as e:
        print(f"\u274C Query failed: {e}")
        sys.exit(1)

    # Header
    rcode_text = dns.rcode.to_text(resp.rcode())
    print(f"\u2705 Query succeeded!\nHEADER:\nid: {resp.id}, opcode: {resp.opcode()}, status: {rcode_text}")
    print()
    # Question
    print(f"QUESTION SECTION:")
    for q in resp.question:
        print(f"{q.name.to_text()}\tIN\t{dns.rdatatype.to_text(q.rdtype)}")
        print()

    # Sections
    print_section("ANSWER", resp.answer)
    print_section("AUTHORITY", resp.authority)
    print_section("ADDITIONAL", resp.additional)
    print()

    # Summary
    print(f"Query time: {getattr(resp, 'time', 'N/A')}s, server: {server}\n")


if __name__ == "__main__":
    main(sys.argv[1:])
