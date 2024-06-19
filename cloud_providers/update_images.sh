gcloud compute images list --uri --project almalinux-cloud --project fedora-cloud --project freebsd-org-cloud-dev --project opensuse-cloud --project cloud-hpc-image-public | sed 's|^https://www.googleapis.com/compute/v1/||' > gcp_images.txt
doctl compute image list --no-header --public --format Slug > do_images.txt
