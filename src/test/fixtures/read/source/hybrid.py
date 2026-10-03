import zlib
def png_up(rows, cols):
    out=b''; prev=bytes(cols)
    for r in rows:
        out+=b'\x02'+bytes((r[i]-prev[i])&0xff for i in range(cols)); prev=r
    return out
content=b'BT /F1 12 Tf 20 100 Td (hybrid) Tj ET'
ccomp=zlib.compress(content,9)
# object stream: 6 info, 7 font, 9 length of 4
objs=[(6,b'<< /Title (hybrid sample) >>'),(7,b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>'),(9,str(len(ccomp)).encode())]
body=b''; head=b''
for n,o in objs:
    head+=b'%d %d '%(n,len(body)); body+=o+b' '
osdata=head+body
oscomp=zlib.compress(osdata,9)
out=bytearray(b'%PDF-1.5\n%\xe2\xe3\xcf\xd3\n')
off={}
def obj(n,b):
    off[n]=len(out); out.extend(b'%d 0 obj\n'%n+b+b'\nendobj\n')
obj(1,b'<< /Type /Catalog /Pages 2 0 R >>')
obj(2,b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>')
obj(3,b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Resources << /Font << /F1 7 0 R >> >> /Contents 4 0 R >>')
obj(4,b'<< /Length 9 0 R /Filter /FlateDecode >>\nstream\n'+ccomp+b'\nendstream')
obj(5,b'<< /Type /ObjStm /N 3 /First %d /Length %d /Filter /FlateDecode >>\nstream\n'%(len(head),len(oscomp))+oscomp+b'\nendstream')
# xref stream 8: rows for 6,7 (type2 in 5), 8 itself (type1), 9 (type2)
off[8]=len(out)
rows=[bytes([2,0,5,0]),bytes([2,0,5,1]),bytes([1,(off[8]>>8)&0xff,off[8]&0xff,0]),bytes([2,0,5,2])]
xs=zlib.compress(png_up(rows,4),9)
out.extend(b'8 0 obj\n<< /Type /XRef /Size 10 /Index [6 4] /W [1 2 1] /DecodeParms << /Predictor 12 /Columns 4 >> /Filter /FlateDecode /Length %d >>\nstream\n'%len(xs)+xs+b'\nendstream\nendobj\n')
xref=len(out)
# the table leaves the numbers the stream lists out
t=b'xref\n0 6\n0000000000 65535 f \n'
for n in range(1,6):
    t+=b'%010d 00000 n \n'%off[n]
out.extend(t+b'trailer\n<< /Size 10 /Root 1 0 R /Info 6 0 R /XRefStm %d >>\nstartxref\n%d\n%%%%EOF\n'%(off[8],xref))
open('hybrid.pdf','wb').write(out)
