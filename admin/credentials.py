"""Windows Credential Manager, current user, generic credential."""
import ctypes as c
from ctypes import wintypes as w
import sys
TARGET='WordclockAdmin:ccachin/wordclock-themes'
if sys.platform=='win32':
    class Credential(c.Structure):
        _fields_=[('Flags',w.DWORD),('Type',w.DWORD),('TargetName',w.LPWSTR),('Comment',w.LPWSTR),('LastWritten',w.FILETIME),('CredentialBlobSize',w.DWORD),('CredentialBlob',c.POINTER(c.c_ubyte)),('Persist',w.DWORD),('AttributeCount',w.DWORD),('Attributes',c.c_void_p),('TargetAlias',w.LPWSTR),('UserName',w.LPWSTR)]
    P=c.POINTER(Credential)
    dll=c.WinDLL('Advapi32',use_last_error=True)
    dll.CredReadW.argtypes=[w.LPCWSTR,w.DWORD,w.DWORD,c.POINTER(P)]; dll.CredReadW.restype=w.BOOL
    dll.CredWriteW.argtypes=[P,w.DWORD]; dll.CredWriteW.restype=w.BOOL
    dll.CredDeleteW.argtypes=[w.LPCWSTR,w.DWORD,w.DWORD]; dll.CredDeleteW.restype=w.BOOL
    dll.CredFree.argtypes=[c.c_void_p]; dll.CredFree.restype=None

def check_platform():
    if sys.platform!='win32': raise RuntimeError('Le stockage persistant requiert Windows.')

def read():
    check_platform(); p=P()
    if not dll.CredReadW(TARGET,1,0,c.byref(p)):
        err=c.get_last_error()
        if err==1168: return None
        raise c.WinError(err)
    try: return c.string_at(p.contents.CredentialBlob,p.contents.CredentialBlobSize).decode('utf-8')
    finally: dll.CredFree(p)

def write(token):
    check_platform(); raw=token.encode('utf-8'); buf=(c.c_ubyte*len(raw)).from_buffer_copy(raw)
    cred=Credential(); cred.Type=1; cred.TargetName=TARGET; cred.CredentialBlobSize=len(raw); cred.CredentialBlob=buf; cred.Persist=2; cred.UserName='github'
    try:
        if not dll.CredWriteW(c.byref(cred),0): raise c.WinError(c.get_last_error())
    finally: c.memset(buf,0,len(raw))

def delete():
    check_platform()
    if not dll.CredDeleteW(TARGET,1,0):
        err=c.get_last_error()
        if err!=1168: raise c.WinError(err)
