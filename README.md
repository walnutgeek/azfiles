# azfiles

Generate SAS for particular share:

    end=`date -v +1y '+%Y-%m-%dT%H:%MZ'`
    SAS=`az storage share generate-sas -n $SHARE --account-name $ACCT --https-only --expiry $end --permissions dlrw -o tsv`


