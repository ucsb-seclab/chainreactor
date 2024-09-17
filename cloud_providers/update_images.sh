#!/usr/bin/env bash

# https://cloud.google.com/compute/docs/images#gcloud
gcloud compute images list --uri \
  --project almalinux-cloud \
  --project fedora-cloud \
  --project freebsd-org-cloud-dev \
  --project opensuse-cloud \
  --project cloud-hpc-image-public \
  | sed 's|^https://www.googleapis.com/compute/v1/||' \
  | grep -v "Windows" \
  > gcp_images.txt

# https://docs.digitalocean.com/products/droplets/details/images/
doctl compute image list --no-header --public --format Slug \
  > do_images.txt

# https://learn.microsoft.com/en-us/azure/virtual-machines/windows/cli-ps-findimage
az vm image list --location westus2 --all \
  | jq -r '.[] | select(.architecture == "x64" and (.urn | contains("Windows") | not)) | .urn' \
  > azure_images.txt
