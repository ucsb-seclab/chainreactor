Run Azure evaluation (local):

```shell
parallel --termseq INT,2000 --shuf -j3 ./bfg9000.py cloud az :::: ./cloud_providers/az_images.txt
```

Run Azure evaluation (server):

```shell
parallel --termseq INT,2000 --memfree 30G --shuf -j8 ./bfg9000.py cloud az :::: ./cloud_providers/az_images.txt
```

Delete old Azure resources:

```shell
az group list | jq -r '.[] | .name | select(contains("chainreactor"))' | xargs -I {} az group delete --name {} --no-wait --yes
```
