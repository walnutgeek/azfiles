import traceback
import sys
import inspect
from datetime import datetime
from pathlib import Path, PosixPath
import xml.etree.ElementTree as ET
import json
from typing import Dict, List, Tuple, Type, Any, get_type_hints
import re

import typing
from dateutil.parser import parse as dt_parse


import requests

CHUNK_SIZE = 64 * 1024

API_VERSION = "2020-04-08"

CONFIG_PATH = Path.home() / ".azfiles.json"


class Config:
    def __init__(self, f: Path = None):
        self.path = Path(f)
        self.data = json.load(self.path.open("rt")) if f and f.exists() else {}

    def save(self):
        json.dump(self.data, self.path.open("wt"), indent=2, sort_keys=True)
        self.path.chmod(0o0600)
        print(f"{self.path!s} saved. mounts={list(self.data.keys())}")


_CONFIG = Config(CONFIG_PATH)

_MOUNT_VARS = ["storage_account", "share", "sas_token"]


class Mount:
    def __init__(self, mount: str, config: Config):
        self.mount_name = mount
        self.config = config
        self.storage_account = ""
        self.share = ""
        self.sas_token = ""
        if mount in config.data:
            self.from_dict(self.config.data[mount])

    def delete(self):
        del self.config.data[self.mount_name]
        self.config.save()

    def save(self):
        d = self.to_dict()
        if all(d.values()):
            self.config.data[self.mount_name] = d
            self.config.save()
        else:
            raise ValueError(f"Invalid mount:{self.mount_name} {d}")

    def to_dict(self):
        return {k: getattr(self, k) for k in _MOUNT_VARS}

    def from_dict(self, d):
        for k in _MOUNT_VARS:
            setattr(self, k, d[k])

    def __str__(self):
        return f"{self.mount_name}:"

    def url(self, path: PosixPath, query: str = None):
        assert path.is_absolute(), path
        query = self.sas_token if query is None else f"{query}&{self.sas_token}"
        return f"https://{self.storage_account}.file.core.windows.net/{self.share}{str(path)}?{query}"


class Remote:
    def __init__(self, remote_str: str, config, ask):
        self.ask = ask
        self.is_dir = remote_str.endswith("/")
        m, p = remote_str.split(":")
        self.mount = Mount(m, config)
        path = PosixPath(p)
        if len(path.parts) > 0 and not (path.is_absolute()):
            path = PosixPath("/", *path.parts)
        self.remote_file = path if not (self.is_dir) and path.is_absolute() else None
        self.remote_path = path

    def proceed(self, msg="Proceed?"):
        return input(msg).lower()[:1] == "y" if self.ask else True

    def url(self, query: str = None):
        return self.mount.url(self.remote_file, query)

    def __str__(self):
        return str(self.mount) + str(self.remote_file)

    def set_remote_file(self, local_path: Path):
        """
        Required when remote file is not predetermined by remote_str and
        need to be derived from local path as relative path rooted in current directory.
        """
        if not self.remote_file:
            if self.is_dir:
                self.remote_file = PosixPath(*self.remote_path.parts, local_path.name)
            else:
                curdir = Path().absolute()
                l = len(curdir.parts)
                local_path = local_path.absolute()
                if curdir.parts == local_path.parts[:l]:
                    self.remote_file = PosixPath("/", *local_path.parts[l:])
                else:
                    raise ValueError(
                        f"Cannot derive remote file from local_path:{local_path!s} ,\n"
                        f"   because is is outside curdir:{curdir!s}"
                    )

    def get_local_file(self, local_str: Path):
        local_path = Path(local_str)
        return local_path / self.remote_file.name if local_path.is_dir() else local_path


def to_snake_case(name):
    """
    >>> list(map(to_snake_case,['Content-Length', 'Content-Length', 'CreationTime','LastAccessTime', 'LastWriteTime', 'Etag']))
    ['content_length', 'content_length', 'creation_time', 'last_access_time', 'last_write_time', 'etag']
    """
    return re.sub("([a-z0-9])[-_]?([A-Z])", r"\1_\2", name).lower()


def clean_header(s):
    """
    >>> hh = ['Content-Length', 'Content-Type', 'Last-Modified', 'ETag', 'Server', 'x-ms-request-id', 'x-ms-version', 'x-ms-type', 'x-ms-server-encrypted', 'x-ms-lease-status', 'x-ms-lease-state', 'x-ms-file-change-time', 'x-ms-file-last-write-time', 'x-ms-file-creation-time', 'x-ms-file-permission-key', 'x-ms-file-attributes', 'x-ms-file-id', 'x-ms-file-parent-id', 'Date']
    >>> list(map(clean_header,hh))
    ['content_length', 'content_type', 'last_modified', 'etag', 'server', 'x_ms_request_id', 'x_ms_version', 'x_ms_type', 'x_ms_server_encrypted', 'x_ms_lease_status', 'x_ms_lease_state', 'change_time', 'last_write_time', 'creation_time', 'permission_key', 'attributes', 'id', 'parent_id', 'date']

    """
    return to_snake_case(re.sub("-", "_", re.sub("x-ms-file-", "", s)))


class DirContent:
    def __init__(self, path: PosixPath):
        self.path = path
        self.entries: Dict[str, "DirEntry"] = {}


def is_from_typing_module(cls):
    """
    >>> is_from_typing_module(typing.Any)
    True
    >>> is_from_typing_module(typing.Callable[[],typing.IO[bytes]])
    True
    >>> is_from_typing_module(str)
    False
    """
    return cls.__module__ == typing.__name__


def is_classvar(t):
    """
    >>> is_classvar(typing.ClassVar[int])
    True
    >>> is_classvar(int)
    False
    """
    return is_from_typing_module(t) and str(t).startswith("typing.ClassVar[")


def get_attr_hints(o):
    """
    Extracts hints without class variables
    >>> class X:
    ...     x:typing.ClassVar[int]
    ...     y:float
    ...
    >>> get_attr_hints(X)
    {'y': <class 'float'>}
    """
    return {k: h for k, h in get_type_hints(o).items() if not is_classvar(h)}


class DirEntry:
    name: str
    type: str
    size: int
    creation_time: datetime
    last_access_time: datetime
    last_write_time: datetime
    etag: str

    @classmethod
    def from_xml(cls, parent: DirContent, xml: ET.Element):
        return cls(
            next(xml.iter("Name")).text,
            xml.tag,
            {
                to_snake_case(prop.tag): prop.text
                for prop in next(xml.iter("Properties"))
            },
            parent=parent,
        )

    def __init__(
        self, name, t, properties, parent: DirContent = None, path: PosixPath = None
    ):
        self.parent = parent
        self.path = path
        self.name = name
        self.type = t
        properties["size"] = properties.get("content_length", None)
        for k in _DIR_ENTRY_HEADER:
            v: Any = None
            if k in properties:
                v = properties[k]
                if v is not None:
                    t = _DIR_ENTRY_HINTS[k]
                    if t == datetime:
                        v = dt_parse(v)
                    elif t == int:
                        v = int(v)
            if not hasattr(self, k):
                setattr(self, k, v)
        if self.parent:
            self.path = self.parent.path / self.name
            self.parent.entries[self.name] = self

    def get_str_field(self, k):
        v = getattr(self, k)
        if v is None:
            return ""
        elif _DIR_ENTRY_HINTS[k] == datetime:
            return v.replace(microsecond=0).isoformat()
        else:
            return str(v)

    def __str__(self):
        return ",".join(self.get_str_field(k) for k in _DIR_ENTRY_HEADER)


_DIR_ENTRY_HINTS = get_attr_hints(DirEntry)
_DIR_ENTRY_HEADER = list(_DIR_ENTRY_HINTS.keys())


class ApiCall:
    @classmethod
    def clear_file(cls, remote: Remote, size: int):
        """
        https://docs.microsoft.com/en-us/rest/api/storageservices/create-file
        """
        call = cls(
            "PUT",
            remote.url(),
            headers={
                "x-ms-content-length": str(size),
                "x-ms-type": "file",
                "x-ms-file-permission": "inherit",
                "x-ms-file-attributes": "None",
                "x-ms-file-creation-time": "now",
                "x-ms-file-last-write-time": "now",
            },
        )
        call.if_error(f"Can't clear_file:{remote!s} ")

    @classmethod
    def upload_file_range(cls, remote: Remote, file: Path, start: int, end: int):
        """
        https://docs.microsoft.com/en-us/rest/api/storageservices/put-range
        """
        with file.open("rb") as fp:
            fp.seek(start)
            call = cls(
                "PUT",
                remote.url("comp=range"),
                data=fp.read(end - start),
                headers={
                    "x-ms-range": f"bytes={start}-{end-1}",
                    "x-ms-write": "update",
                },
            )
            call.if_error(f"Can't upload_file_range: {remote!s}[{start}:{end}] ")

    @classmethod
    def directory_exists(cls, remote: Remote, remote_dir: PosixPath) -> bool:
        """
        https://docs.microsoft.com/en-us/rest/api/storageservices/get-directory-properties
        """
        call = cls("HEAD", remote.mount.url(remote_dir, "restype=directory"))
        if call.response.status_code == 404:
            return False
        call.if_error()
        return True

    @classmethod
    def get_dir_properties(cls, remote: Remote, remote_path: PosixPath) -> DirEntry:
        """
        https://docs.microsoft.com/en-us/rest/api/storageservices/get-directory-properties
        """
        call = cls("HEAD", remote.mount.url(remote_path, "restype=directory"))
        if call.response.status_code == 200:
            return call.headers_to_direntry(remote_path, "Directory")
        return None

    @classmethod
    def get_file_properties(cls, remote: Remote, remote_path: PosixPath) -> DirEntry:
        """
        https://docs.microsoft.com/en-us/rest/api/storageservices/get-file-properties
        """
        call = cls("HEAD", remote.mount.url(remote_path))
        if call.response.status_code == 200:
            return call.headers_to_direntry(remote_path, "File")
        return None

    @classmethod
    def create_directory(cls, remote: Remote, remote_dir: PosixPath):
        """
        https://docs.microsoft.com/en-us/rest/api/storageservices/create-directory
        """
        call = cls(
            "PUT",
            remote.mount.url(remote_dir, "restype=directory"),
            headers={
                "x-ms-file-permission": "inherit",
                "x-ms-file-attributes": "Directory",
                "x-ms-file-creation-time": "now",
                "x-ms-file-last-write-time": "now",
            },
        )
        call.if_error(f"Can't create dir:{remote_dir!s} ")

    @classmethod
    def download_file(cls, remote: Remote, local_path: Path):
        """
        https://docs.microsoft.com/en-us/rest/api/storageservices/get-file
        """
        with cls("GET", remote.url(), stream=True).response as r:
            r.raise_for_status()
            with local_path.open("wb") as f:
                for chunk in r.iter_content(chunk_size=CHUNK_SIZE):
                    f.write(chunk)

    @classmethod
    def delete_directory(cls, remote: Remote, remote_dir: PosixPath):
        """
        https://docs.microsoft.com/en-us/rest/api/storageservices/delete-directory
        """
        call = cls("DELETE", remote.mount.url(remote_dir, "restype=directory"))
        call.if_error()

    @classmethod
    def delete_file(cls, remote: Remote, remote_path: PosixPath):
        """
        https://docs.microsoft.com/en-us/rest/api/storageservices/delete-file2
        """
        call = cls("DELETE", remote.mount.url(remote_path))
        call.if_error()

    @classmethod
    def list_dir(cls, remote: Remote, remote_dir: PosixPath) -> DirContent:
        """
        https://docs.microsoft.com/en-us/rest/api/storageservices/list-directories-and-files
        """
        call = cls(
            "GET",
            remote.mount.url(
                remote_dir,
                "restype=directory&comp=list&include=ETag&include=Timestamps",
            ),
        )
        call.if_error()
        root = ET.fromstring(call.response.text)
        content = DirContent(remote_dir)
        for child in next(root.iter("Entries")):
            DirEntry.from_xml(content, child)
        return content

    def __init__(
        self,
        method: str,
        url: str,
        data: bytes = None,
        headers: Dict[str, str] = None,
        stream=False,
    ):
        if headers is None:
            headers = {}
        headers["x-ms-version"] = API_VERSION
        self.response = requests.request(
            method, url, data=data, headers=headers, stream=stream
        )

    def if_error(self, msg=""):
        if self.response.status_code >= 400:
            raise ValueError(msg + str(self))

    def headers_to_direntry(self, path: PosixPath, ftype: str):
        return DirEntry(
            path.name,
            ftype,
            {clean_header(k): v for k, v in self.response.headers.items()},
            path=path,
        )

    def print_headers(self):
        print(f"status: {self.response.status_code}")
        for k, v in self.response.headers.items():
            print(f"  {k}: {v}")

    def __str__(self):
        return f"status:{self.response.status_code}\n{self.response.text}"


def split_buffer(sz: int, max: int) -> List[Tuple[int, int]]:
    """
    >>> split_buffer(100,4000000)
    [(0, 100)]
    >>> split_buffer(300,100)
    [(0, 100), (100, 200), (200, 300)]
    >>> split_buffer(301,100)
    [(0, 100), (100, 200), (200, 300), (300, 301)]

    """

    starts = list(range(0, sz, max))
    ends = [*starts[1:], sz]
    return list(zip(starts, ends))


class Actions:
    def __init__(self, remote: Remote, api: Type[ApiCall]):
        self.remote = remote
        self.api = api

    def upload(self, local_str):
        local_path = Path(local_str)
        self.remote.set_remote_file(local_path)

        # ensure dirs
        dir = self.remote.remote_file.parent
        assert dir.is_absolute(), dir
        dirs_to_create = []
        while True:
            if len(dir.parts) <= 1:
                break
            if self.api.directory_exists(self.remote, dir):
                break
            dirs_to_create.insert(0, dir)
            dir = dir.parent
        for dir in dirs_to_create:
            self.api.create_directory(self.remote, dir)

        sz = local_path.stat().st_size
        self.api.clear_file(self.remote, sz)
        ranges = split_buffer(sz, 4000000)
        for start, end in ranges:
            self.api.upload_file_range(self.remote, local_path, start, end)

    def download(self, local_path):
        self.api.download_file(self.remote, self.remote.get_local_file(local_path))

    def list(self):
        self.remote.set_remote_file(Path())
        content = self.api.list_dir(self.remote, self.remote.remote_path)
        print(str(self.remote.mount) + str(content.path))
        print(",".join(_DIR_ENTRY_HEADER))
        for e in content.entries.values():
            print(str(e))

    def props(self):
        print(str(self._get_direntry()))

    def _get_direntry(self):
        self.remote.set_remote_file(Path())
        order = [self.api.get_file_properties, self.api.get_dir_properties]
        if self.remote.is_dir:
            order.reverse()
        for c in order:
            e = c(self.remote, self.remote.remote_file)
            if e:
                break
        return e

    def _delete_dir_recursively(self, path: PosixPath):
        assert path.is_absolute(), path
        dir_content = self.api.list_dir(self.remote, path)
        for e in dir_content.entries.values():
            if e.type == "Directory":
                self._delete_dir_recursively(e.path)
            else:
                self.api.delete_file(self.remote, e.path)
        self.api.delete_directory(self.remote, path)

    def delete(self):
        e = self._get_direntry()
        if e is None:
            print(f"Path doesn't exist: {self.remote.remote_file}")
        else:
            if e.type == "Directory":
                if self.remote.proceed(f"Delete directory recursively!!!:{e.path}?"):
                    self._delete_dir_recursively(e.path)
            else:
                if self.remote.proceed(f"Delete file:{e.path}?"):
                    self.api.delete_file(self.remote, self.remote.remote_file)

    def add_mount(self, storage_account, share, sas_token):
        mount = self.remote.mount
        if any(mount.to_dict().values()):
            if not self.remote.proceed(f"Override mount:{self.remote.mount}?"):
                return
        mount.storage_account = storage_account
        mount.share = share
        mount.sas_token = sas_token
        mount.save()

    def delete_mount(self):
        if self.remote.proceed(f"Delete mount:{self.remote.mount}?"):
            self.remote.mount.delete()


def check_the_force(args) -> Tuple[List[str], bool]:
    """
    Check if user wants to force destructive operations without asking
    """
    not_y = lambda s: s != "-y"
    ask = all(map(not_y, args))
    return [v for v in args if not_y(v)], ask


def main(args=sys.argv[1:], api: Type[ApiCall] = ApiCall, config=_CONFIG):
    show_help = False
    if len(args) == 0:
        print("azfiles - interact with Azure file shares\n")
        print(f"Available mounts: \n   {list(config.data.keys())}")
        show_help = True
    else:
        try:
            args, ask = check_the_force(args)
            cli = Actions(Remote(args[0], config, ask), api)
            getattr(cli, args[1])(*args[2:])
        except:
            traceback.print_exc()
            show_help = True
    if show_help:

        print("\nUSAGES:")
        actions = [f for f in dir(Actions) if not f.startswith("_")]
        for a in actions:
            fn = getattr(Actions, a)
            names, _, _, defaults = inspect.getfullargspec(fn)[:4]
            if defaults is None:
                defaults = ()
            def_offset = len(names) - len(defaults)
            optonals = {k: v for k, v in zip(names[def_offset:], defaults)}
            a_args = " ".join(
                f"[{n}]" if n in optonals else f"<{n}>" for n in names[1:]
            )
            print(f" azfiles <remote_path> {a} {a_args}")
        print()
