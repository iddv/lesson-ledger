import socket


def raw(port, data, timeout=3.0, close_write=False):
    """Send raw bytes, return what the server sends back (b'' on timeout/close)."""
    s = socket.create_connection(('127.0.0.1', port))
    s.settimeout(timeout)
    try:
        s.sendall(data)
        if close_write:
            s.shutdown(socket.SHUT_WR)
        try:
            return s.recv(4096)
        except socket.timeout:
            return b''
    finally:
        s.close()


def port_of(app):
    return int(app.base.rsplit(':', 1)[1])
