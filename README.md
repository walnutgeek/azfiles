# azfiles


Allow you interact with Azure fileshares without installing az-cli. 

Main intention to allow move files but keep it minimal. Project 2 external 
dependencies: requests and python-dateutil and  `pytest -cov` shows 323 
lines of production code at this time.  

Get it:

    pip install azfiles

Get help:

```
    $azfiles 
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

