#!/usr/bin/env bash

# https://docs.digitalocean.com/products/droplets/details/images/
doctl compute image list \
  --no-header \
  --public \
  --format Slug \
| grep -i -v "windows" \
> do_images.txt
