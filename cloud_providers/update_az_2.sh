#!/usr/bin/env bash

jq -r '
  group_by([.publisher, .offer, .sku])
  | .[]
  | sort_by(.version)
  | .[-1]
  | select(.architecture == "x64")
  | .urn' \
  az_images.json \
| grep -E -i -v "windows" \
| xargs -P32 -I {} /usr/bin/env bash -c "
  info=\$(az vm image show --location westus2 --urn {})
  os=\$(echo \"\$info\" | jq -r '.osDiskImage.operatingSystem')
  has_plan=\$(echo \"\$info\" | jq -r 'if .plan == null then \"yes\" else \"no\" end')
  echo \"{} \$os \$has_plan\"" \
| awk '$2 == "Linux" && $3 == "no" { print $1 }' \
> az_images_2.txt
