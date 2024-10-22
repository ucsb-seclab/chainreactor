import subprocess
import json
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed

with open("az_images.json") as f:
    az_images = json.load(f)


def cmp_version(a: str, b: str) -> int:
    a = a.split(".")
    b = b.split(".")
    for i in range(3):
        if int(a[i]) > int(b[i]):
            return 1
        elif int(a[i]) < int(b[i]):
            return -1
    return 0


skus = {}
for image in tqdm(az_images):
    if image["architecture"] != "x64":
        continue
    triple = image["publisher"], image["offer"], image["sku"]
    if triple not in skus:
        skus[triple] = image
    elif cmp_version(image["version"], skus[triple]["version"]) > 0:
        skus[triple] = image


def details_task(image):
    proc = subprocess.run(
        [
            "az",
            "vm",
            "image",
            "show",
            "--location",
            "westus2",
            "--urn",
            image["urn"],
            "--output",
            "json",
        ],
        capture_output=True,
    )
    return None if proc.stdout == b"" else json.loads(proc.stdout)


plans = {}
with ThreadPoolExecutor(128) as executor:
    futures = {executor.submit(details_task, image): image for image in skus.values()}
    for future in tqdm(as_completed(futures), total=len(futures)):
        details = future.result()
        image = futures[future]
        if not details or details["osDiskImage"]["operatingSystem"] != "Linux":
            continue
        plans[image["urn"]] = details["plan"]

# for image in tqdm(skus.values()):
#     details = details_task(image)
#     if not details or details["osDiskImage"]["operatingSystem"] != "Linux":
#         continue
#     plans[image["urn"]] = details["plan"]


with open("az_images_3.json", "w") as f:
    json.dump(plans, f)
