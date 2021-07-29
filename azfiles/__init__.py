from pathlib import Path,PosixPath
import xml.etree.ElementTree as ET
import json
from typing import Dict, List, Tuple

import requests

CONFIG_PATH= Path.home() / '.azfiles.json'

class Config:

    def __init__(self, f:Path=None):
        self.path=Path(f)
        self.data = json.load(self.path.open("rt"))  if f and f.exists() else {}

    def save(self):
        json.dump(self.path.open("wt"), self.data, indent=2, sort_keys=True)
        self.path.chmod(0o0600)

_CONFIG = Config(CONFIG_PATH)


class Mount:

    def __init__(self, mount: str, config = _CONFIG):
        mount_cfg = config.data[mount]
        self.mount_name = mount
        self.storage_account = mount_cfg["storage_account"]
        self.share = mount_cfg["share"]
        self.sas_token = mount_cfg["sas_token"]

    def __str__(self):
        return f"{self.mount_name}:"

    def url (self, path: PosixPath, query: str = None):
        assert path.is_absolute()
        query = self.sas_token if query is None else f'{query}&{self.sas_token}'
        return f"https://{self.storage_account}.file.core.windows.net/{self.share}{str(path)}?{query}"



class Remote:

    def __init__(self, remote_str:str, config = _CONFIG):
        self.is_dir = remote_str.endswith("/")
        m, p = remote_str.split(':')
        self.mount = Mount(m, config=config)
        path = PosixPath(p)
        if len(path.parts) > 0 and not(path.is_absolute()):
            path = PosixPath('/', *path.parts)
        self.remote_file = path if not(self.is_dir) and path.is_absolute() else None
        self.remote_path = path

    def __str__(self):
        return str(self.mount)+str(self.remote_file)

    def set_remote_file(self, local_path:Path):
        """
        Required when remote file is not predetermined by remote_str and
        need to be derived from local path as relative path rooted in current directory.
        """
        if not self.remote_file :
            if self.is_dir:
                self.remote_file = PosixPath(*self.remote_path.parts, local_path.name)
            else:
                curdir = Path().absolute()
                l = len(curdir.parts)
                local_path =local_path.absolute()
                if curdir.parts == local_path.parts[:l]:
                    self.remote_file = PosixPath('/', *local_path.parts[l:] )
                else:
                    raise ValueError(
                        f"Cannot derive remote file from local_path:{local_path!s} ,\n"
                        f"   because is is outside curdir:{curdir!s}")





class ApiCall:

    @classmethod
    def clear_file(cls, remote:Remote, size:int):
        call = cls('PUT',
                   remote.mount.url(remote.remote_file),
                   headers = {
                        "x-ms-content-length" : str(size),
                        "x-ms-type" : "file"
        })
        call.if_error(f"Can't clear_file:{remote!s} ")


    @classmethod
    def upload_file_range(cls, remote:Remote, file:Path, start:int, end:int):
        with file.open("rb") as fp:
            fp.seek(start)
            call = cls(
                'PUT',
                remote.mount.url(remote.remote_file,"comp=range"),
                data = fp.read(end-start),
                headers = {
                    "x-ms-range" : f"bytes={start}-{end-1}",
                    "x-ms-write" : "update"
                })
        call.if_error(f"Can't upload_file_range: {remote!s}[{start}:{end}] ")

    @classmethod
    def directory_exists(cls, remote:Remote, remote_dir:PosixPath) -> bool:
        call = cls('HEAD', remote.mount.url(remote_dir, "restype=directory"))
        if call.response.status_code == 404:
            return False
        call.if_error()
        return True

    @classmethod
    def create_directory(cls, remote:Remote, remote_dir:PosixPath):
        call = cls('PUT', remote.mount.url(remote_dir, "restype=directory"))
        call.if_error(f"Can't create dir:{remote_dir!s} ")

    @classmethod
    def download_file(cls, remote:Remote, local_path:Path):
        pass


    @classmethod
    def list_files(cls, remote:Remote) -> List[str]:
        pass

    def __init__(self, method:str, url:str, data:bytes=None, headers: Dict[str,str]=None):
        if headers is None:
            headers = {}
        headers["x-ms-version"] = "2018-11-09"
        self.response = requests.request(method, url, data=data, headers=headers)

    def if_error(self, msg=""):
        if self.response.status_code >= 400:
            raise ValueError(f"{msg}status:{self.response.status_code}\n{self.response.text}")


def split_buffer(sz:int, max:int)->List[Tuple[int,int]]:
    """
    >>> split_buffer(100,4000000)
    [(0, 100)]
    >>> split_buffer(300,100)
    [(0, 100), (100, 200), (200, 300)]
    >>> split_buffer(301,100)
    [(0, 100), (100, 200), (200, 300), (300, 301)]

    """

    starts = list(range(0,sz,max))
    ends = [ *starts[1:], sz]
    return list(zip(starts,ends))

class Actions:
    def __init__(self, remote:Remote):
        self.remote = remote

    def upload(self, local_path):
        local = Path(local_path)
        self.remote.set_remote_file(local)

        #ensure dirs
        dir = self.remote.remote_file.parent
        assert dir.is_absolute()
        dirs_to_create = []
        while True:
            if len(dir.parts) <= 1:
                break
            if ApiCall.directory_exists(self.remote, dir):
                break
            dirs_to_create.insert(0, dir)
            dir = dir.parent
        for dir in dirs_to_create:
            ApiCall.create_directory(self.remote, dir)

        sz = local.stat().st_size
        ApiCall.clear_file(self.remote, sz)
        ranges = split_buffer(sz,4000000)
        for start, end in ranges:
            ApiCall.upload_file_range(self.remote, local, start, end)

    def download(self, local_path):
        pass

    def list(self):
        pass

    def mount(self, storage_accout, share, sas_token):
        pass


import sys
def main():
    getattr(Actions(Remote(sys.argv[1], _CONFIG)), sys.argv[2])(*sys.argv[3:])

