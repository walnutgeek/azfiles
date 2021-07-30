# azfiles


Allow you interact with Azure fileshares without installing az-cli. 

Main intention to allow move files but keep it minimal. Project has 2 external 
dependencies: requests and python-dateutil and  `pytest -cov` shows 323 
lines of production code at this time.  

Get it:

    pip install azfiles

Get help:

```
    $ azfiles 
    azfiles - interact with Azure file shares
    
    Available mounts: 
       ['mnt01']
    
    USAGES:
     azfiles <remote_path> add_mount <storage_account> <share> <sas_token>
     azfiles <remote_path> delete 
     azfiles <remote_path> delete_mount 
     azfiles <remote_path> download <local_path>
     azfiles <remote_path> list 
     azfiles <remote_path> props 
     azfiles <remote_path> upload <local_str>
     
    $ 
```
## How to

Generate SAS token for particular share and register it with `azfiles` as mount `mnt01` :

    
    end=`date -v +1y '+%Y-%m-%dT%H:%MZ'` #end access in one year
    SAS=`az storage share generate-sas -n $SHARE --account-name $ACCT --https-only --expiry $end --permissions dlrw -o tsv`
    azfiles mnt01: add_mount $ACCT $SHARE "$SAS"    

After that you are ready to interact with storage. Upload file at 
any <remote_path>. Slash at the end of <remote_path> is important to tell 
save this file in remote directory and keep it's name.

    $ azfiles mnt01:/logs/ upload ~/backup.log
    $ azfiles mnt01:/ upload hello.txt
    $

Diretories will be created along. You can change name of the file. Notice 
no slash in next example:  

    $ azfiles mnt01:/backups/logs/20210730.log upload ~/backup.log
    

List remote directory content:

    $ azfiles mnt01:/logs/ list
    mnt01:/logs
    name,type,size,creation_time,last_access_time,last_write_time,etag
    backup.log,File,38070517,2021-07-30T18:13:20+00:00,2021-07-30T18:13:20+00:00,2021-07-30T18:13:20+00:00,"0x8D95385C4B8D2D8"
    $ azfiles mnt01:/ list
    mnt01:/
    name,type,size,creation_time,last_access_time,last_write_time,etag
    abc,Directory,,2021-07-30T06:29:13+00:00,2021-07-30T06:29:13+00:00,2021-07-30T06:29:13+00:00,"0x8D9532359534095"
    backups,Directory,,2021-07-30T18:16:32+00:00,2021-07-30T18:16:32+00:00,2021-07-30T18:16:32+00:00,"0x8D9538628A3B80C"
    hello.txt,File,13,2021-07-30T18:26:54+00:00,2021-07-30T18:26:54+00:00,2021-07-30T18:26:54+00:00,"0x8D953879BD09E17"
    logs,Directory,,2021-07-30T18:13:20+00:00,2021-07-30T18:13:20+00:00,2021-07-30T18:13:20+00:00,"0x8D95385B635435D"
    
You can check on single file too:

    $ azfiles mnt01:/backups/logs/20210730.log props
    20210730.log,File,38070517,2021-07-30T18:16:32+00:00,,2021-07-30T18:16:32+00:00,"0x8D9538638AFD991"


You and of course you can get your files back. You dont have to add slash 
to <local_path> if this directory already exists:
    
    $ azfiles mnt01:/backups/logs/20210730.log download .

    
    

    