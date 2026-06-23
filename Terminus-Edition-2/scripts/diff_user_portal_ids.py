#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
USER_IDS = """4375ed22-f2cf-457a-8e84-223859fcb2d2
529e2a84-f140-4036-98c2-64f45fa72f31
78816498-a2d8-41ae-acd8-d42d80405961
02ce0a54-ea1c-4339-ab60-f8dcb36411d8
cdefb68f-ab0e-4909-be1d-3fa153b88a4a
57f23c91-035f-4b52-b6a4-bae742212e3d
0122149a-0a15-44c5-8703-ac5cfe6d6b59
5f8ce7c6-9981-4d2a-9194-540fcdfa9e6b
a870f40f-b704-4edd-98fe-77fb6d05f3bf
0377ba70-c90c-4d91-8083-e835bdcffeac
3a6b0228-726b-4d9a-a39a-c31830e2744d
d99e0689-a056-4793-87ff-0f85431d97e1
1e20b807-48d1-4496-aeb9-8b92f62cead9
d0295913-57b4-4d22-ae74-449c845df95e
b00c48ef-6543-45f3-82e9-9d219b93ebab
e3c6b347-3559-4612-abe1-8ebb1776afc0
ae8eea53-f223-4ffc-8b6f-087d670c052f
ce854f97-e916-46b0-b5a7-1f64cac9d49c
add7088e-6a1e-4957-bf56-067f344c3da6
233ad144-29e0-4279-b1ad-46e1817b6bb5
88439038-b3ec-4da8-bbaa-147300fd7612
bfcdb165-8fc5-4d15-8c1d-049d1c09beca
cb3e0a50-d20e-4520-ab74-407729ed4288
60af763d-1e5c-4df4-9a0a-84c313ef7e55
4c5dfbec-ccbc-42d4-9a00-58689b5c2c2b
a8dc31b4-f77c-4eaa-b549-6a485a0b08df
62929cbb-2a32-42e2-90be-47c347296a09
24b7ce75-a875-48c4-8809-844a084b22d4
c03df315-93af-48c5-8bfb-b0698a89a4e3
182bded9-a7c1-4d04-b7ed-5c6c68438086
fe568c5d-0754-41d3-84e8-6b96a833f360
14002f67-d5f4-4a3e-b796-23abeb4ef571
2f7859e8-3f19-41e8-a8ee-ccab57078449
7fb1a57c-eab9-4eca-aa80-2431ba4a189c
6bf2639b-67a5-488b-bb07-b58418183299
c3865f7a-4e9b-4107-9c92-7ff3a75c70c6
e53ff9bd-3058-4ad7-adda-d60f391febba
016a6fe0-145e-47f3-aa17-a60ec540b97b
614060df-358c-4b96-90cc-df886c4b7626
a4606faa-24d7-4862-93b5-c50700980896
2e8e149d-bb9c-445e-bd9b-25c207364268
342c074d-9870-49fc-974b-b5ab8149a3f7
ff495811-7b4a-4021-883f-137894ae6a76
ded8127e-956c-4ff9-bfca-204878d5e85b
a6e6c9e7-43c7-4409-bff2-ddd358bbc492
7224d09b-53e1-4d83-a0ca-d607d8abc3ac
caa647fd-baeb-4bfc-800d-0b4cfa2c562d
c55be376-df97-4f0a-922e-ebf1e17a000d
2811eae7-8385-4d95-a966-17bf444556b8
4e43bc9d-ff68-44d2-bb3d-2957f1e5bbad
35f72f1d-5320-472d-ba7d-db2344524659
19f9997c-f473-434d-956a-4a43e288ad48
0ce68f84-80d0-42d5-8844-b190faed2581
09b9f0cc-1b71-4fca-8791-6e130cf5389f
d78be9f5-2568-4002-b7ac-68fabb7dbe06
c5230168-9ce9-4b65-8fa1-7523adc5307e
d1e88ac6-156b-4394-b5b2-40ae5ea971ab
e3414486-0402-49f9-8f9e-0518d4695cec
aa1e07d3-91bc-4bef-9d31-1a48daf93690
d567814d-307d-48a2-bb01-be833ea1108e
3e856b7d-0d8d-4238-a0d3-8b16fab28146""".strip().split()

manifest_path = ROOT / "Revision-ChatGpt/needs_revision_pulls/portal_ids_manifest.tsv"
manifest = {}
for line in manifest_path.read_text(encoding="utf-8").splitlines():
    if not line.strip() or line.startswith("#"):
        continue
    sid, folder, status = line.split("\t")
    manifest[sid] = (folder, status)

mapped = {}
for line in (ROOT / "needs_revision_mapped.txt").read_text(encoding="utf-8").splitlines():
    if "\t" in line:
        sid, folder = line.split("\t", 1)
        mapped[sid] = folder

print(f"user_ids={len(USER_IDS)} manifest={len(manifest)}")
missing = [sid for sid in USER_IDS if sid not in manifest]
print(f"missing_from_manifest={len(missing)}")
for sid in missing:
    print(f"  {sid}\t{mapped.get(sid, '?')}")

upload = sorted((ROOT / "revision-custom-upload").glob("*.zip"))
upload_names = {p.stem for p in upload}
print(f"revision-custom-upload zips={len(upload_names)}")

local_folders = sorted(
    p.name
    for p in ROOT.iterdir()
    if p.is_dir() and (p / "task.toml").is_file() and not p.name.startswith(".")
)
print(f"local task folders={len(local_folders)}")
