__version__ = '0.1'
__all__ = [ 'getDateAdded', 'setDateAdded' ]
#############################################################################################
# There is a need to update (migrate) file's DateAdded timestamp.
# DateAdded timestamp is a timestamp when a file or directory was added to the directory. 
#############################################################################################
# mdls -attr kMDItemDateAdded ~/Downloads/test_added.txt
# kMDItemDateAdded = 2024-01-15 18:00:37 +0000
#############################################################################################
# based on: https://stackoverflow.com/a/73616027
# based on: https://apple.stackexchange.com/a/446258
#############################################################################################

from ctypes import (
    Structure, get_errno, byref, sizeof, CDLL, POINTER,
    c_char_p, c_long, c_uint16, c_ushort, c_void_p, c_size_t, c_ulong, c_uint32
)
from datetime import datetime


# Source of below constants and structures (classes):
# /Library/Developer/CommandLineTools/SDKs/MacOSX.sdk/usr/include/sys/attr.h
ATTR_BIT_MAP_COUNT       =  5
ATTR_CMN_RETURNED_ATTRS  =  0x80000000
ATTR_CMN_ADDEDTIME       =  0x10000000
FSOPT_NOFOLLOW           =  0x00000001

class c_time_t(c_long): pass
class attrgroup_t(c_uint32): pass

class attribute_set(Structure):
    _fields_ = [
        ( "commonattr",  attrgroup_t ),
        ( "volattr",     attrgroup_t ),
        ( "dirattr",     attrgroup_t ),
        ( "fileattr",    attrgroup_t ),
        ( "forkattr",    attrgroup_t )
    ]

class attrlist(Structure):
    _anonymous_ = ( "a" )
    _fields_ = [
        ( "bitmapcount", c_ushort ),
        ( "reserved",    c_uint16 ),
        ( "a",           attribute_set )
    ]
    def __init__(self, *, commonattr = 0, volattr = 0, dirattr = 0, fileattr = 0, forkattr = 0):
        super().__init__(
            bitmapcount=ATTR_BIT_MAP_COUNT, reserved=0, 
            commonattr=commonattr, volattr=volattr, dirattr=dirattr,
            fileattr=fileattr, forkattr=forkattr)

class timespec(Structure):
    _fields_ = [("tv_sec", c_time_t), ("tv_nsec", c_long)]
    def __init__(self, tv_sec = 0, tv_nsec = 0):
        super().__init__(tv_sec, tv_nsec)


class dateaddedResponse(Structure):
    _fields_ = [
        ("length", c_uint32), ("returned", attribute_set), ("dateadded", timespec)
    ]


def raise_for_errno(result, func, arguments):
    if result != 0:
        e = get_errno()
        # msg = '%s: %s for %s' % (errno.errorcode[e], os.strerror(e), arguments[0].decode())
        raise OSError(e, None, arguments[0].decode())
    

libc = CDLL('libc.dylib', use_errno=True)
getattrlist = libc.getattrlist
getattrlist.argtypes = (c_char_p, POINTER(attrlist), c_void_p, c_size_t, c_ulong)
getattrlist.errcheck = raise_for_errno
setattrlist = libc.setattrlist
setattrlist.argtypes = (c_char_p, POINTER(attrlist), c_void_p, c_size_t, c_ulong)
setattrlist.errcheck = raise_for_errno


def getDateAdded(path : str | bytes) -> datetime:
    bPath = path if isinstance(path, bytes) else path.encode()
    req = attrlist(commonattr = attrgroup_t(ATTR_CMN_RETURNED_ATTRS | ATTR_CMN_ADDEDTIME))
    res = dateaddedResponse()
    r = getattrlist(bPath, byref(req), byref(res), sizeof(res), FSOPT_NOFOLLOW)

    if res.returned.commonattr.value != req.commonattr.value:
        return None
    else:
        return datetime.fromtimestamp(res.dateadded.tv_sec.value)

def setDateAdded(path : str | bytes, timestamp : str | int | datetime) -> None:
    bPath = path if isinstance(path, bytes) else path.encode()
    iTimestamp = timespec()
    if isinstance(timestamp, str):
        iTimestamp.tv_sec = c_time_t(int(datetime.fromisoformat(timestamp).timestamp()))
    elif isinstance(timestamp, datetime):
        iTimestamp.tv_sec = c_time_t(int(timestamp.timestamp()))
    else:
        iTimestamp.tv_sec = c_time_t(timestamp)
    req = attrlist(commonattr = ATTR_CMN_ADDEDTIME)
    r = setattrlist(bPath, byref(req), byref(iTimestamp), sizeof(iTimestamp), FSOPT_NOFOLLOW)


#############################################
# Main section
#############################################
if __name__ == '__main__':
    import sys, argparse
    
    argparser = argparse.ArgumentParser()
    argparsers = argparser.add_subparsers(title='actions', dest='mode', required=True)
    
    argget = argparsers.add_parser('get', description='Getting DateAdded information:').add_argument_group()
    argget.add_argument('-v', action='count', default=0, help='Verbose output')
    argget.add_argument('-i', help='Read list from file. If filename is - then stdin is used.', metavar='filename')
    argget.add_argument('path', action='extend', nargs='*', type=str,
            help='path to get DateAdded timestamp of (supports wildcards) (kMDItemDateAdded). ' +
                 'Similar to: mdls -attr kMDItemDateAdded path')

    argset = argparsers.add_parser('set', description='Setting DateAdded information:').add_argument_group()
    argset.add_argument('-v', action='count', default=0, help='Verbose output')
    argset.add_argument('-i', help='Read list from file. If filename is - then stdin is used.', metavar='filename')
    argset.add_argument('path', action='extend', nargs='*', type=str, metavar='timestamp,path', 
            help='timestamp is in ISO format (e.g.: 2024-01-15T21:20:37,/foo/bar or "2024-01-15 21:20:37,/foo/bar")')

    args = argparser.parse_args()

    setmode = args.mode == 'set'

    def pathWithTimestamp(timestampath : str) -> tuple[datetime,str]:
        if ',' not in timestampath:
            raise ValueError('Invalid format! Should be "timestamp,path", got: %s.' % timestampath)
        ts, path = timestampath.split(',', maxsplit=1)
        return (datetime.fromisoformat(ts), path)

    def iterfiles():
        from glob import iglob
        global setmode, args
        if args.i:
            for l in open(args.i):
                l = l.strip()
                if not l or l.startswith('#'):
                    continue
                yield l
        if args.path:
            for p in args.path:
                if not setmode and ('*' in p or '_' in p):
                    for pp in iglob(p):
                        yield pp
                else:
                    yield p

    for p in iterfiles():
        if setmode:
            try:
                t,p = pathWithTimestamp(p)
                print('Setting: %s,%s' % (t,p))
                setDateAdded(p,t)
            except Exception as e:
                print(e, file=sys.stderr)
        else:
            try: 
                print('%s,%s' % (getDateAdded(p).isoformat(), p))
            except Exception as e:
                print(e, file=sys.stderr)
