# OpenCV shape 库项目内试用补丁

2026-10-18。上一轮板端日志明确在 relocation processing: /usr/lib/libopencv_shape.so.3.4 后崩溃，采集到该对象的 l_info 动态表指针全部为零。当前还不能仅凭这段日志认定磁盘文件损坏。此包先比对系统库文件哈希，再用出厂同版本库的项目内副本测试。

payload/libopencv_shape.so.3.4 来自本地出厂 rootfs 的 usr/lib/libopencv_shape.so.3.4.3，未改动其 ELF 内容，SONAME 为 libopencv_shape.so.3.4。SHA-256 为 311b18ae66685a764d0a36053bf3d39198f1318203f3b806e8019630e5713cda。本机 readelf 检查可见完整 DT_STRTAB、DT_SYMTAB、DT_NEEDED 和动态段，架构为 ARMv7 hard-float。尚未进行实体板执行验证。

## 使用

Windows 解压 ZIP 后，把整个 labmate_opencv_shape_probe_20261018 文件夹放到 SD 卡项目 labmate_lite_image_reader_board_v2 内。板端执行：

```sh
cp -R /media/sd-mmcblk0p1/labmate_lite_image_reader_board_v2/labmate_opencv_shape_probe_20261018 "$HOME/labmate_reader_v2/"
cd "$HOME/labmate_reader_v2/labmate_opencv_shape_probe_20261018"
python3 probe_shape.py --app "$HOME/labmate_reader_v2" --install
```

脚本只对测试子进程设置 LD_LIBRARY_PATH，优先选取 payload 中的库，检查实际内存映射确实选中了这份副本。随后测试 OpenCV 导入、灰度转换、阈值、轮廓、矩形、缩放和 PNG 读写。

只有测试通过才把库安装到应用目录的 libopencv_shape.so.3.4；不会覆盖 /usr/lib 的系统文件。安装前备份应用内已有同名文件，再使用不含 payload 的路径检查安装结果，检查失败则恢复原应用内覆盖文件。系统库始终保持不变。

如果仍然崩溃，脚本不会安装，会调用上一轮补充包的 native_fault.so 收集新的加载日志。请提供末尾 REPORT= 指向的 report.txt，其中还包含原系统库与本副本的哈希是否相同。

## 成功后测试整图

installed=True 只表示本次 OpenCV 基础操作检查通过，不代表 OCR 整图准确率已验收。

```sh
cd "$HOME/labmate_reader_v2"
export LD_LIBRARY_PATH="$PWD${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
python3 -m c_vision_lite.board_reader --image sample.jpg --bundle "$PWD" --detector-size 512 --out runs_measure_512
```

512 是首次流程和内存探测参数，识别结果须另行逐项核对。稳定后再验证默认 960 的结果。

OpenCV 3.4.3 源码与许可：https://github.com/opencv/opencv/tree/3.4.3 。库的原出厂镜像位置：本工作区 tmp/audio_source_review/资源文件/出厂镜像相关/rootfs.tar.gz 。此包使用相同版本二进制，未替换系统 glibc 或加载器。
