#!/usr/bin/env bash

# https://learn.microsoft.com/en-us/azure/virtual-machines/windows/cli-ps-findimage
# azure_images.json was sourced from a non-rate-limited account on 2024-09-16 with:
#   az vm image list --location westus2 --all

# Steps:
# - Group by SKU
# - For each SKU, select the latest version
# - Filter out ARM architectures
# - Output the URN
# - Check if URN is Linux or Windows
# - Filter out Windows URNs using heuristics
# - Filter out Windows URNs using the API
jq -r '
  group_by([.publisher, .offer, .sku])
  | .[]
  | sort_by(.version)
  | .[-1]
  | select(.architecture == "x64")
  | .urn' \
  az_images.json \
| grep -E -i -v "windows" \
| xargs -P16 -I {} /usr/bin/env bash -c "
  os=\$(az vm image show --location westus2 --urn {} | jq -r '.osDiskImage.operatingSystem')
  echo \"{} \$os\"" \
| awk '$2 == "Linux" { print $1 }' \
> az_images.txt
