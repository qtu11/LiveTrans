import pytest

from livetrans.app import self_test
from livetrans.config import Config

pytestmark = pytest.mark.slow


def test_self_test_passes():
    """Cùng bước kiểm tra mà build.ps1 chạy trên LiveTrans.exe — bắt lỗi import/đổi tên trước khi build."""
    assert self_test(Config()) == 0
