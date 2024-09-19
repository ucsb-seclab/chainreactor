#!/usr/bin/env bash

# https://cloud.google.com/compute/docs/images#gcloud
gcloud compute images list \
  --uri \
  --project almalinux-cloud \
  --project fedora-cloud \
  --project freebsd-org-cloud-dev \
  --project opensuse-cloud \
  --project cloud-hpc-image-public \
| sed 's|^https://www.googleapis.com/compute/v1/||' \
| grep -i -v "windows" \
> gcp_images.txt
