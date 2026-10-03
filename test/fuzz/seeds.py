import zlib,sys
def build(objs, trailer_extra=b'', prev_self=False, xref_stream=None):
    out=bytearray(b'%PDF-1.7\n'); off={}
    for n,b in objs:
        off[n]=len(out); out+=b'%d 0 obj\n'%n+b+b'\nendobj\n'
    at=len(out); size=max(off)+1
    out+=b'xref\n0 %d\n0000000000 65535 f\r\n'%size
    for n in range(1,size):
        out+=(b'%010d 00000 n\r\n'%off[n]) if n in off else b'0000000000 00000 f\r\n'
    out+=b'trailer\n<< /Size %d /Root 1 0 R '%size+trailer_extra+((b'/Prev %d '%at) if prev_self else b'')+b'>>\nstartxref\n%d\n%%%%EOF\n'%at
    return bytes(out)
cat=b'<< /Type /Catalog >>'
open(sys.argv[1]+'/s-nest.pdf','wb').write(build([(1,b'<< /Type /Catalog /Deep '+b'['*300+b']'*300+b' >>')]))
open(sys.argv[1]+'/s-prev-loop.pdf','wb').write(build([(1,cat)],prev_self=True))
open(sys.argv[1]+'/s-length-cycle.pdf','wb').write(build([(1,cat),(2,b'<< /Length 2 0 R >>\nstream\nab\nendstream')]))
bomb=zlib.compress(bytes(4<<20),9)
open(sys.argv[1]+'/s-bomb.pdf','wb').write(build([(1,cat),(2,b'<< /Length %d /Filter /FlateDecode >>\nstream\n'%len(bomb)+bomb+b'\nendstream')]))
# an xref stream placing object 3 in object stream 2, which itself claims to be packed
out=bytearray(b'%PDF-1.7\n'); off={}
def o(n,b):
    off[n]=len(out); out.extend(b'%d 0 obj\n'%n+b+b'\nendobj\n')
o(1,cat)
data=b'3 0 << /A 3 0 R >>'
o(2,b'<< /Type /ObjStm /N 1 /First 4 /Length %d >>\nstream\n'%len(data)+data+b'\nendstream')
off[4]=len(out)
rows=bytes([1,0,0,0, 1,0,off[1],0, 2,0,2,0, 2,0,3,0, 1,(off[4]>>8)&255,off[4]&255,0])
out.extend(b'4 0 obj\n<< /Type /XRef /Size 5 /W [1 2 1] /Root 1 0 R /Length %d >>\nstream\n'%len(rows)+rows+b'\nendstream\nendobj\nstartxref\n%d\n%%%%EOF\n'%off[4])
open(sys.argv[1]+'/s-objstm-self.pdf','wb').write(bytes(out))
