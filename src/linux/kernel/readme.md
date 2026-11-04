# 内核源码

`atk-zynq-linux-xlnx.tar.xz` 保留原厂 Linux 5.4.0 的构建源码、头文件、板级 DTS 和配置系统。只剔除编辑器索引/缓存、版本控制元数据、备份目录与原归档内的旧 image.ub；实际使用的新板端镜像在 `board/linux/artifacts/`。

所有保留的普通文件内容 SHA256 见 `build/kernel_source_manifest.json`。此格式调整已同步到 SPI 内核构建包和旧摄像头内核恢复脚本中。不要用其他厂商内核版本直接替换。
