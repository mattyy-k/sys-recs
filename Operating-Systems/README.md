# Ext2 image reader and modifier

This repository contains a small C++17 utility that reads and modifies classic ext2 images directly. It decodes little endian fields by offset instead of overlaying host C structures. The assignment names `Artifacts/disk-backpup.img`; that artifact is not present in this checkout, so the outputs below are from reproducible temporary ext2 images and are not claimed as outputs from the missing assignment image.

## Build and commands

```sh
make
./ext2 info /path/to/image.img
./ext2 groups /path/to/image.img
./ext2 tree /path/to/image.img
./ext2 cat /path/to/image.img /path/to/file
./ext2 overwrite /path/to/copy.img /path/to/file replacement.txt
./ext2 append /path/to/copy.img /path/to/file addition.txt
```

Read commands open the image for reading. `overwrite` and `append` mutate the named image in place; copy the source image first. The final argument is read as a file when it names an existing file, otherwise its literal bytes are used. Pass a file to represent empty or binary payloads.

## Design

The reader checks the ext2 magic and derives the block size from `s_log_block_size`. It reads the superblock at byte 1024 and uses its inode/block totals, per-group counts, revision, inode size, and feature masks. It computes group count from both block and inode geometry, then reads the 32-byte group descriptors after the superblock block. Inodes are located through each descriptor's inode-table pointer and decoded by inode number.

Directory data is read through inode block pointers and parsed from variable-length records. Zero inode entries are skipped; `.` and `..` are omitted in display and never recursed into. Symlinks are displayed but not followed. Path resolution begins at inode 2. File data supports direct, single-indirect, and double-indirect pointers for reading; modifications currently support up to direct plus single-indirect blocks.

Writes retain the inode, allocate blocks by scanning group block bitmaps, update group and superblock free-block counts, update the inode's size, block count and timestamps, and release surplus old data blocks on shrink. A partial final block is read before appended bytes are added, then data is written back with unused tail bytes cleared. Mutations are serialized by a single process and are not crash-atomic; the tool does not implement journaled ext3/ext4, extents, external xattrs, inode allocation, or concurrent writer locking. Unknown incompatible ext2 features are displayed but not rejected, so images using unsupported features need separate validation. Do not use on valuable originals.

## Validation performed

The following commands were run on a fresh 16 MiB ext2 image (the installed `mke2fs` selected 4 KiB blocks). This is synthetic validation, not output from the missing assignment artifact:

```sh
truncate -s 16M /tmp/ext2-demo.img
mke2fs -q -t ext2 -F /tmp/ext2-demo.img
printf hello >/tmp/ext2-hello.txt
debugfs -w -R 'mkdir /nested' /tmp/ext2-demo.img
debugfs -w -R 'write /tmp/ext2-hello.txt /nested/hello.txt' /tmp/ext2-demo.img
./ext2 info /tmp/ext2-demo.img
./ext2 groups /tmp/ext2-demo.img
./ext2 tree /tmp/ext2-demo.img
./ext2 cat /tmp/ext2-demo.img /nested/hello.txt
cp /tmp/ext2-demo.img /tmp/ext2-write.img
./ext2 append /tmp/ext2-write.img /nested/hello.txt ' world'
./ext2 cat /tmp/ext2-write.img /nested/hello.txt
e2fsck -fn /tmp/ext2-write.img
```

Observed outputs included `inodes: 4096`, `blocks: 4096`, `block size: 4096`, group 0 with block bitmap 2, inode bitmap 3 and inode table 4, and `/nested/hello.txt` as inode 13. `cat` returned `hello` before modification and `hello world` after append. On the copied image, shrinking the file to `short`, then overwriting it with a 70,000-byte generated payload, produced a byte-for-byte `cmp` match after reopening through the reader. `e2fsck -fn` reported all five passes successful and `13/4096 files, 286/4096 blocks`; `dumpe2fs` reported 3810 free blocks and 4083 free inodes. The 70,000-byte overwrite exercised additional allocation and single-indirect addressing. Empty files, all double-indirect edge cases, 1 KiB group geometry, and the provided assignment image remain unverified. No concurrency bonus is implemented.

## Assignment image status

`ASSIGNMENT.md` lists one image, `Artifacts/disk-backpup.img`. It is absent here. Therefore image-specific layout/output sections, known-file checks, and image-specific write validation remain unverified; no findings have been fabricated.
