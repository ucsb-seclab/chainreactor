Run Azure evaluation:

```shell
parallel --termseq INT,2000 --memfree 30G --shuf -j4 ./bfg9000.py cloud az :::: cloud_providers/az_images_2.txt
```

Delete Azure resource groups:

```shell
az group list | jq -r '.[] | .name | select(contains("chainreactor"))' | xargs -I {} az group delete --name {} --no-wait --yes
```

List vulnerable images:

```shell
sqlite3 stats.sqlite 'select * from runs where state="RunState.SOLUTION_FOUND"'
```
