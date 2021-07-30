# azfiles

## How to

Generate SAS for particular share and register it with `azfiles` as mount `mnt01` :

    
    end=`date -v +1y '+%Y-%m-%dT%H:%MZ'` #end access in one year
    SAS=`az storage share generate-sas -n $SHARE --account-name $ACCT --https-only --expiry $end --permissions dlrw -o tsv`
    azfiles mnt01: add_mount $ACCT $SHARE "$SAS"    

