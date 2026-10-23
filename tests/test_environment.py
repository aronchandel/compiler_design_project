import sys
import cpp2py

def test_python_version():
    assert sys.version_info >= (3, 10)

def test_cpp2py_version():
    assert isinstance(cpp2py.__version__, str)
