#!/usr/bin/env python3
"""Probe only Rockchip 2207:0019; temporary RNDIS session, no system changes."""
import ctypes as C
import struct as S
import time
import socket
import json
import sys
import ctypes.util
from pathlib import Path

# Usage: probe_hat.py <network.json output path>
NETWORK_FILE = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name('hat-network.json')
FRAMES_LOG = NETWORK_FILE.with_name('usb-frames.log')

def load_libusb():
    for path in ('/opt/homebrew/lib/libusb-1.0.dylib', '/usr/local/lib/libusb-1.0.dylib', ctypes.util.find_library('usb-1.0')):
        if path:
            try:
                return C.CDLL(path)
            except OSError:
                pass
    raise SystemExit('libusb not found. Run: brew install libusb')

u = load_libusb()
P = C.c_void_p
u.libusb_init.argtypes = [C.POINTER(P)]
u.libusb_get_device_list.argtypes = [P, C.POINTER(C.POINTER(P))]
u.libusb_get_device_list.restype = C.c_ssize_t
u.libusb_get_device_descriptor.argtypes = [P, P]
u.libusb_open.argtypes = [P, C.POINTER(P)]
u.libusb_claim_interface.argtypes = [P, C.c_int]
u.libusb_release_interface.argtypes = [P, C.c_int]
u.libusb_close.argtypes = [P]
u.libusb_error_name.argtypes = [C.c_int]
u.libusb_error_name.restype = C.c_char_p
u.libusb_control_transfer.argtypes = [P, C.c_uint8, C.c_uint8, C.c_uint16, C.c_uint16, P, C.c_uint16, C.c_uint]
u.libusb_bulk_transfer.argtypes = [P, C.c_ubyte, P, C.c_int, C.POINTER(C.c_int), C.c_uint]

def check(rc):
    if rc < 0:
        raise RuntimeError(u.libusb_error_name(rc).decode())
    return rc

ctx = P()
check(u.libusb_init(C.byref(ctx)))
devs = C.POINTER(P)()
n = check(u.libusb_get_device_list(ctx, C.byref(devs)))
print('USB devices visible:', n, flush=True)
h = P()
for i in range(n):
    desc = C.create_string_buffer(18)
    check(u.libusb_get_device_descriptor(devs[i], desc))
    if S.unpack_from('<HH', desc.raw, 8) == (0x2207, 0x0019):
        check(u.libusb_open(devs[i], C.byref(h)))
        break
if not h:
    raise SystemExit('Hat not found on USB (Rockchip 2207:0019). Check it is powered on and plugged in with a data cable, not a charge-only cable.')
claimed = []
try:
    for iface in (0, 1):
        check(u.libusb_claim_interface(h, iface))
        claimed.append(iface)
    buf = C.create_string_buffer(4096)
    size = check(u.libusb_control_transfer(h, 0x80, 6, 0x0200, 0, buf, len(buf), 2000))
    raw = buf.raw[:size]
    eps = []
    current = None
    pos = 0
    while pos + 2 <= len(raw) and raw[pos]:
        length, kind = raw[pos:pos+2]
        d = raw[pos:pos+length]
        if kind == 4:
            current = d[2]
        elif kind == 5 and current == 1 and d[3] & 3 == 2:
            eps.append(d[2])
        pos += length
    epin = next(x for x in eps if x & 0x80)
    epout = next(x for x in eps if not x & 0x80)
    print('RNDIS bulk endpoints:', hex(epin), hex(epout), flush=True)
    request = 0
    def command(words, tail=b''):
        global request
        request += 1
        msg = S.pack('<'+'I'*len(words), *words) + tail
        b = C.create_string_buffer(msg)
        check(u.libusb_control_transfer(h, 0x21, 0, 0, 0, b, len(msg), 2000))
        for _ in range(10):
            time.sleep(.05)
            out = C.create_string_buffer(4096)
            z = check(u.libusb_control_transfer(h, 0xa1, 1, 0, 0, out, len(out), 2000))
            response = out.raw[:z]
            if len(response) >= 16 and S.unpack_from('<I', response, 8)[0] == words[2]:
                if S.unpack_from('<I', response, 12)[0]:
                    raise RuntimeError('RNDIS command failed: '+response.hex())
                return response
        raise RuntimeError('No matching RNDIS response')
    command([2,24,1,1,0,16384])
    print('RNDIS initialization succeeded', flush=True)
    r = command([4,28,2,0x01010102,0,0,0])
    length, offset = S.unpack_from('<II', r, 16)
    mac = r[8+offset:8+offset+length]
    print('USB network adapter MAC:', mac.hex(':'), flush=True)
    command([5,32,3,0x0001010e,4,20,0], S.pack('<I', 0x0f))
    def send(frame):
        packet = S.pack('<11I',1,44+len(frame),36,len(frame),0,0,0,0,0,0,0)+frame
        b = C.create_string_buffer(packet)
        count = C.c_int()
        check(u.libusb_bulk_transfer(h,epout,b,len(packet),C.byref(count),2000))
    # Ask the hat's DHCP server for its network configuration.
    hostmac = mac if len(mac) == 6 else bytes.fromhex('020000484154')
    bootp = S.pack('!BBBBIHH',1,1,6,0,0x48415431,0,0x8000)+bytes(16)+hostmac+bytes(10)+bytes(64+128)
    bootp += bytes.fromhex('63825363') + bytes([53,1,1,55,3,1,3,54,255])
    udp = S.pack('!HHHH',68,67,8+len(bootp),0)+bootp
    ip = S.pack('!BBHHHBBH4s4s',0x45,0,20+len(udp),1,0,64,17,0,bytes(4),bytes([255]*4))
    total=sum(S.unpack('!10H',ip));total=(total&65535)+(total>>16);total=(total&65535)+(total>>16)
    ip=ip[:10]+S.pack('!H',(~total)&65535)+ip[12:]
    send(bytes([255]*6)+hostmac+b'\x08\x00'+ip+udp)
    candidates = ['172.32.0.93', '192.168.1.1', '192.168.0.1', '192.168.42.1', '192.168.137.1', '192.168.100.1', '192.168.2.1', '192.168.77.2', '192.168.7.2', '192.168.55.1', '192.168.6.1', '192.168.42.129', '192.168.1.93', '192.168.0.93', '192.168.10.1', '192.168.10.93', '10.0.0.1']
    def arp_probes():
        for peer in candidates:
            host = '192.168.77.1' if peer == '192.168.77.2' else peer.rsplit('.', 1)[0] + '.100'
            arp = S.pack('!HHBBH',1,0x0800,6,4,1)+hostmac+socket.inet_aton(host)+bytes(6)+socket.inet_aton(peer)
            send(bytes([255]*6)+hostmac+b'\x08\x06'+arp)
    def dhcp_reply(frame):
        # Only answer a DHCP client on this physical USB device, never the Mac LAN.
        ihl = (frame[14] & 15)*4
        if frame[23] != 17 or len(frame) < 14+ihl+8+240:
            return
        if S.unpack_from('!HH', frame, 14+ihl) != (68,67):
            return
        boot = frame[14+ihl+8:]
        if boot[0] != 1 or boot[28:34] == hostmac:
            return
        options = boot[240:]; kind = None; j = 0
        while j < len(options):
            code = options[j]; j += 1
            if code == 255: break
            if code == 0: continue
            if j >= len(options): break
            length = options[j]; j += 1
            val = options[j:j+length]; j += length
            if code == 53 and val: kind = val[0]
        print('Hat DHCP client message:', kind, 'client MAC:', boot[28:34].hex(':'), flush=True)
        if kind not in (1,3): return
        peer = socket.inet_aton('192.168.77.2'); server = socket.inet_aton('192.168.77.1')
        response = bytes([2,1,6,0])+boot[4:8]+bytes(2)+b'\x80\x00'+bytes(4)+peer+server+bytes(4)+boot[28:44]+bytes(192)
        response += bytes.fromhex('63825363')+bytes([53,1,2 if kind==1 else 5,54,4])+server
        response += bytes([51,4])+S.pack('!I',3600)+bytes([1,4,255,255,255,0,255])
        udp = S.pack('!HHHH',67,68,8+len(response),0)+response
        ip = S.pack('!BBHHHBBH4s4s',0x45,0,20+len(udp),2,0,64,17,0,server,bytes([255]*4))
        total=sum(S.unpack('!10H',ip));total=(total&65535)+(total>>16);total=(total&65535)+(total>>16)
        ip=ip[:10]+S.pack('!H',(~total)&65535)+ip[12:]
        send(bytes([255]*6)+hostmac+b'\x08\x00'+ip+udp)
        print('Sent DHCP '+('OFFER' if kind==1 else 'ACK')+' for 192.168.77.2',flush=True)
    arp_probes()
    retry_at = time.monotonic()+3
    NETWORK_FILE.unlink(missing_ok=True)
    print('Checking addresses and DHCP requests for 30 seconds...', flush=True)
    deadline=time.monotonic()+30
    seen=set()
    while time.monotonic()<deadline:
        if time.monotonic() >= retry_at:
            arp_probes(); retry_at = time.monotonic()+3
        b=C.create_string_buffer(65536);count=C.c_int()
        rc=u.libusb_bulk_transfer(h,epin,b,len(b),C.byref(count),1000)
        if rc==-7: continue
        check(rc)
        data=b.raw[:count.value]
        while len(data)>=44:
            kind,length,offset,flen=S.unpack_from('<4I',data)
            if length<44 or length>len(data):break
            f=data[8+offset:8+offset+flen]
            if kind==1 and len(f)>=34:
                with FRAMES_LOG.open('a') as log: log.write(f.hex()+'\n')
                typ=f[12:14]
                if typ==b'\x08\x00':
                    dhcp_reply(f)
                    addr=socket.inet_ntoa(f[26:30])
                    if addr not in seen:
                        print('Hat IPv4 source:',addr,flush=True);seen.add(addr)
                    ihl=(f[14]&15)*4
                    if f[23]==17 and len(f)>14+ihl+8+240:
                        ports=S.unpack_from('!HH',f,14+ihl)
                        if ports==(67,68):
                            dh=f[14+ihl+8:]
                            print('DHCP offered host IP:',socket.inet_ntoa(dh[16:20]),flush=True)
                            print('DHCP server IP field:',socket.inet_ntoa(dh[20:24]),flush=True)
                elif typ==b'\x08\x06' and len(f)>=42:
                    addr=socket.inet_ntoa(f[28:32])
                    if addr not in seen:
                        print('Hat ARP IPv4:',addr,flush=True);seen.add(addr)
                    if addr in candidates and S.unpack_from('!H', f, 20)[0] == 2:
                        host = '192.168.77.1' if addr == '192.168.77.2' else addr.rsplit('.',1)[0]+'.100'
                        NETWORK_FILE.write_text(json.dumps({'peer':addr,'host':host,'host_mac':hostmac.hex(':')}))
                        deadline = time.monotonic()

            data=data[length:]
    network_file = NETWORK_FILE
    if not network_file.exists():
        network_file.write_text(json.dumps({'peer':'192.168.77.2','host':'192.168.77.1','host_mac':hostmac.hex(':')}))
        print('No address confirmed yet. Starting the persistent DHCP bridge to restore the USB lease.',flush=True)
finally:
    for iface in reversed(claimed):u.libusb_release_interface(h,iface)
    u.libusb_close(h)
